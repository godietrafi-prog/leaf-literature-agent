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


def _ensure_provenance_col(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(numeric_results)")]
    if "provenance" not in cols:
        conn.execute("ALTER TABLE numeric_results ADD COLUMN provenance TEXT DEFAULT 'seed'")
        conn.execute("UPDATE numeric_results SET provenance='seed' WHERE provenance IS NULL")


def store():
    conn = sqlite3.connect(DB_PATH)
    _ensure_provenance_col(conn)
    pdf_map = eval_extract._load_pdf_map()

    from bedrock_client import BedrockClient
    client = BedrockClient()
    tag = f"llm:{client.model.split('.')[-1]}"  # e.g. llm:claude-sonnet-4-6

    n_papers = n_rows = n_flagged = 0
    for pid in sorted(pdf_map):
        if not conn.execute("SELECT 1 FROM papers WHERE paper_id=?", (pid,)).fetchone():
            continue
        text, kind = eval_extract.paper_source_text(conn, pid, pdf_map)
        if kind != "pdf" or not text.strip():
            continue
        try:
            out = extract.extract_paper(text, client=client, mock=False)
        except Exception as e:  # noqa: BLE001 — truncated/failed paper: skip, don't abort
            print(f"  [skip] {pid}: {str(e)[:80]}")
            continue

        cur = conn.cursor()
        cur.execute("DELETE FROM numeric_results WHERE paper_id=? AND provenance LIKE 'llm:%'", (pid,))
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
        print(f"  {pid:<32} +{rows} rows")

    conn.execute("INSERT OR REPLACE INTO run_state (key, value) VALUES ('last_extract_store', ?)", (TODAY,))
    conn.commit()
    print(f"\nStored {n_rows} extracted rows across {n_papers} papers "
          f"(provenance={tag}, needs_human flagged: {n_flagged}).")
    seed = conn.execute("SELECT COUNT(*) FROM numeric_results WHERE provenance='seed'").fetchone()[0]
    llm = conn.execute("SELECT COUNT(*) FROM numeric_results WHERE provenance LIKE 'llm:%'").fetchone()[0]
    print(f"DB numeric_results now: {seed} seed + {llm} llm-extracted = {seed + llm}")
    conn.close()


if __name__ == "__main__":
    store()
