#!/usr/bin/env python3
"""
store_extractions.py — promote LLM extractions into the DB (Phase 2 → production).

For each paper with a mapped source PDF, run the extractor (cache hit → free) and
write its numeric_results into db/leaf_lit.db tagged provenance='llm:<model>', so
they sit alongside — but clearly distinct from — the human-review 'seed' rows.

These rows are UNVERIFIED (the gold itself is AI-built and not yet human-checked,
see the sample-verification discussion). The dashboard labels them as such. When
Rafi verifies values later, flip needs_human / correct the value in place.

Idempotent: deletes prior llm rows for a paper before re-inserting.

Run with the metaflow venv (cache hits need no boto3; a cache miss will call
Bedrock, so use py_work to be safe):
    py_work agent/store_extractions.py
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract  # noqa: E402
import eval_extract  # noqa: E402  (reuses its PDF map + text loader)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "db", "leaf_lit.db")
TODAY = date.today().isoformat()
TARGET_KW = (
    "odor", "odour", "off-flavor", "off-flavour", "flavor", "flavour", "aroma",
    "sensory", "hexanal", "aldehyde", "volatile", "chlorophyll", "colour",
    "color", "green", "browning", "lox", "lipoxygenase", "phenolic", "oxidation",
    "enzyme", "pigment",
)


def _ensure_provenance_col(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(numeric_results)")]
    if "provenance" not in cols:
        conn.execute("ALTER TABLE numeric_results ADD COLUMN provenance TEXT DEFAULT 'seed'")
        conn.execute("UPDATE numeric_results SET provenance='seed' WHERE provenance IS NULL")
    for name, ddl in [("verified", "INTEGER DEFAULT 0"), ("verified_value", "REAL"),
                      ("verified_note", "TEXT"), ("verified_date", "TEXT")]:
        if name not in cols:
            conn.execute(f"ALTER TABLE numeric_results ADD COLUMN {name} {ddl}")


def _paper_blob(conn, paper_id: str) -> str:
    row = conn.execute(
        """SELECT COALESCE(p.paper_id,''), COALESCE(p.title,''), COALESCE(p.system,''),
                  COALESCE(p.extraction_method_family,''), COALESCE(p.scientific_story,''),
                  COALESCE(p.key_findings,'')
           FROM papers p WHERE p.paper_id=?""",
        (paper_id,),
    ).fetchone()
    cats = " ".join(r[0] for r in conn.execute(
        "SELECT category FROM paper_categories WHERE paper_id=?", (paper_id,)
    ))
    return " ".join(row or []) + " " + cats


def _is_target_paper(conn, paper_id: str) -> bool:
    return any(k in _paper_blob(conn, paper_id).lower() for k in TARGET_KW)


def _select_papers(conn, pdf_map: dict, paper_ids: list[str] | None,
                   search_only: bool, target_only: bool, skip_llm_existing: bool) -> list[str]:
    selected = sorted(pdf_map)
    if paper_ids:
        wanted = set(paper_ids)
        selected = [pid for pid in selected if pid in wanted]
    if search_only:
        selected = [pid for pid in selected if pid.startswith("search_")]
    selected = [
        pid for pid in selected
        if conn.execute("SELECT 1 FROM papers WHERE paper_id=?", (pid,)).fetchone()
    ]
    if target_only:
        selected = [pid for pid in selected if _is_target_paper(conn, pid)]
    if skip_llm_existing:
        selected = [
            pid for pid in selected
            if not conn.execute(
                "SELECT 1 FROM numeric_results WHERE paper_id=? AND provenance LIKE 'llm:%' LIMIT 1",
                (pid,),
            ).fetchone()
        ]
    return selected


def store(*, paper_ids: list[str] | None = None, search_only: bool = False,
          target_only: bool = False, mock: bool = False, skip_llm_existing: bool = False):
    conn = sqlite3.connect(DB_PATH)
    _ensure_provenance_col(conn)
    pdf_map = eval_extract._load_pdf_map()

    client = None
    if mock:
        tag = "auto_mock"
    else:
        from bedrock_client import BedrockClient
        client = BedrockClient()
        tag = f"llm:{client.model.split('.')[-1]}"  # e.g. llm:claude-sonnet-4-6

    selected = _select_papers(conn, pdf_map, paper_ids, search_only, target_only, skip_llm_existing)
    if not selected:
        print("No mapped PDF papers matched the requested filters.")
        conn.close()
        return

    n_papers = n_rows = n_flagged = 0
    for i, pid in enumerate(selected, start=1):
        print(f"  [{i}/{len(selected)}] extracting {pid} ...", flush=True)
        text, kind = eval_extract.paper_source_text(conn, pid, pdf_map)
        if kind != "pdf" or not text.strip():
            print(f"  [skip] {pid}: no readable PDF text", flush=True)
            continue
        try:
            out = extract.extract_paper(text, client=client, mock=mock)
        except Exception as e:  # noqa: BLE001 — truncated/failed paper: skip, don't abort
            print(f"  [skip] {pid}: {str(e)[:120]}", flush=True)
            continue

        cur = conn.cursor()
        if mock:
            cur.execute("DELETE FROM numeric_results WHERE paper_id=? AND provenance='auto_mock'", (pid,))
        else:
            cur.execute(
                """DELETE FROM numeric_results
                   WHERE paper_id=? AND provenance!='seed' AND COALESCE(verified,0)=0""",
                (pid,),
            )
        rows = 0
        for r in out.get("numeric_results", []):
            if r.get("value") is None:
                continue
            cur.execute(
                """INSERT INTO numeric_results
                   (paper_id, quantity, value, unit, sd_error, error_type, n_replicates,
                    p_value, method, species, treatment_condition, basis, source_location,
                    is_from_SI, needs_human, provenance, extracted_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, r.get("quantity"), r.get("value"), r.get("unit"), r.get("sd_error"),
                 r.get("error_type"), r.get("n_replicates"), r.get("p_value"), r.get("method"),
                 r.get("species"), r.get("treatment_condition"), r.get("basis"),
                 r.get("source_location"), int(r.get("is_from_SI") or 0),
                 int(r.get("needs_human") or 0), tag, TODAY),
            )
            rows += 1
            n_flagged += int(r.get("needs_human") or 0)
        conn.commit()
        n_papers += 1
        n_rows += rows
        print(f"  {pid:<32} +{rows} rows", flush=True)

    if n_papers:
        conn.execute("INSERT OR REPLACE INTO run_state (key, value) VALUES ('last_extract_store', ?)", (TODAY,))
        conn.commit()
    print(f"\nStored {n_rows} extracted rows across {n_papers} papers "
          f"(provenance={tag}, needs_human flagged: {n_flagged}).")
    seed = conn.execute("SELECT COUNT(*) FROM numeric_results WHERE provenance='seed'").fetchone()[0]
    llm = conn.execute("SELECT COUNT(*) FROM numeric_results WHERE provenance LIKE 'llm:%'").fetchone()[0]
    print(f"DB numeric_results now: {seed} seed + {llm} llm-extracted = {seed + llm}")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper-id", action="append",
                    help="process only this paper_id; repeat for multiple papers")
    ap.add_argument("--search-only", action="store_true",
                    help="process only paper_ids created by the literature search agent")
    ap.add_argument("--target-only", action="store_true",
                    help="process only papers whose metadata touches sensory/color/oxidation targets")
    ap.add_argument("--mock", action="store_true",
                    help="use the local regex extractor instead of Bedrock")
    ap.add_argument("--skip-llm-existing", action="store_true",
                    help="skip papers that already have llm:* numeric rows")
    args = ap.parse_args()
    store(paper_ids=args.paper_id, search_only=args.search_only,
          target_only=args.target_only, mock=args.mock, skip_llm_existing=args.skip_llm_existing)
