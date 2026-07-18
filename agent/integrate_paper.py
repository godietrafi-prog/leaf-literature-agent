#!/usr/bin/env python3
"""Incremental single-paper knowledge integration — the v2 pipeline entry point.

Goal (from both technical reviews): dropping ONE new paper should run the whole
pipeline, validate the new evidence, REUSE existing entities, and UPDATE the body
of knowledge (counts, confidence, contradictions, candidates) rather than just
appending rows — while preserving complete provenance and never rebuilding the
expensive extraction for papers already in the corpus.

Pipeline for one paper:
  1. register     — text + metadata + pdf map, with DOI/title duplicate detection
  2. extract      — numeric_results (extract.py) + evidence_claims (knowledge_engine)
  3. validate     — quote audit (physical PDF re-match) + validation_state
  4. normalize    — canonical entities (reuse-or-create) + ontology harmonization
  5. link         — claim <-> number bridge
  6. integrate    — rebuild derived knowledge (harmonized, candidate matrix) from
                    the immutable raw layer, so the new paper updates everything
  7. audit        — write an integration_runs row describing what changed

Only step 2 is per-paper and (for --real) billed; steps 4/6 are deterministic
rebuilds of DERIVED tables from immutable raw rows and are fast at this scale, so
"adding one paper" never re-extracts the corpus. Runs with --mock anywhere;
--real uses Claude on Bedrock (needs boto3 + AWS creds, e.g. the py_work venv).

Usage:
  python3 agent/integrate_paper.py --pdf inbox/pdfs/new_paper.pdf --mock
  python3 agent/integrate_paper.py --paper-id duckweed_pmc2023 --mock   # reprocess
  python3 agent/integrate_paper.py --inbox --mock                        # all inbox PDFs
  python3 agent/integrate_paper.py --reindex                             # backfill derived layers
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import auto_ingest
import entities
import extract
import harmonize
import knowledge_engine
import link_claims
import migrations
import ontology_match  # noqa: F401 (ensures module import health)

DB_PATH = ROOT / "db" / "leaf_lit.db"
PDF_MAP_PATH = ROOT / "db" / "pdf_sources.json"
TODAY = date.today().isoformat()


# ── validation_state (deterministic reduction) ────────────────────────────────
def compute_validation_state(provenance: str | None, verified) -> str:
    if verified:
        return "human_verified"
    p = (provenance or "").lower()
    if p.startswith("seed") or p.startswith("evidence:") or p == "manual_pdf_ingest":
        return "machine_verified"   # curated/approved origin
    return "extracted"              # raw LLM/regex output, awaiting verification


def set_validation_states(conn: sqlite3.Connection, paper_id: str | None = None) -> None:
    where, params = ("WHERE paper_id=?", (paper_id,)) if paper_id else ("", ())
    rows = conn.execute(
        f"SELECT result_id, provenance, verified FROM numeric_results {where}", params).fetchall()
    for result_id, provenance, verified in rows:
        conn.execute("UPDATE numeric_results SET validation_state=? WHERE result_id=?",
                     (compute_validation_state(provenance, verified), result_id))
    conn.commit()


# ── duplicate detection ───────────────────────────────────────────────────────
def _norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def find_duplicate(conn: sqlite3.Connection, doi: str | None, title: str | None) -> str | None:
    if doi:
        d = re.sub(r"^https?://(dx\.)?doi\.org/", "", str(doi).strip(), flags=re.I).rstrip(".,);]").lower()
        row = conn.execute("SELECT paper_id FROM papers WHERE lower(doi)=?", (d,)).fetchone()
        if row:
            return row[0]
    nt = _norm_title(title)
    if len(nt) >= 20:
        for pid, t in conn.execute("SELECT paper_id, title FROM papers WHERE title IS NOT NULL"):
            if _norm_title(t) == nt:
                return pid
    return None


# ── numeric extraction + store (captures new result_ids for incremental steps) ─
def store_numeric(conn, pid, text, si_text, client, mock, tag) -> list[int]:
    out = extract.extract_paper(text, si_text, client=client, mock=mock)
    conn.execute(
        "DELETE FROM numeric_results WHERE paper_id=? AND provenance!='seed' AND COALESCE(verified,0)=0",
        (pid,))
    new_ids = []
    for r in out.get("numeric_results", []):
        if r.get("value") is None:
            continue
        cur = conn.execute(
            """INSERT INTO numeric_results
               (paper_id, quantity, value, unit, sd_error, error_type, n_replicates, p_value,
                method, species, treatment_condition, basis, source_location, is_from_SI,
                needs_human, provenance, extracted_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, r.get("quantity"), r.get("value"), r.get("unit"), r.get("sd_error"),
             r.get("error_type"), r.get("n_replicates"), r.get("p_value"), r.get("method"),
             r.get("species"), r.get("treatment_condition"), r.get("basis"),
             r.get("source_location"), int(r.get("is_from_SI") or 0),
             int(r.get("needs_human") or 1), tag, TODAY))
        new_ids.append(cur.lastrowid)
    conn.commit()
    return new_ids


def _counts(conn) -> dict:
    def one(sql):
        return conn.execute(sql).fetchone()[0]
    return {
        "papers": one("SELECT COUNT(*) FROM papers"),
        "numeric": one("SELECT COUNT(*) FROM numeric_results"),
        "claims": one("SELECT COUNT(*) FROM evidence_claims"),
        "candidates": one("SELECT COUNT(*) FROM experiment_candidates"),
        "contradictions": one("SELECT COUNT(*) FROM experiment_candidates WHERE contradiction_rate>0"),
        "entities": one("SELECT COUNT(*) FROM canonical_entities"),
    }


# ── the orchestrator ──────────────────────────────────────────────────────────
def integrate_paper(pid: str, *, text: str, si_text: str | None, mock: bool,
                    real: bool) -> dict:
    """Run the full incremental pipeline for a single already-registered paper."""
    client = None
    tag = "auto_mock" if mock else "manual_pdf_ingest"
    if real:
        from bedrock_client import BedrockClient  # lazy; needs boto3
        client = BedrockClient()
        tag = f"llm:{client.model.split('.')[-1]}"

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA foreign_keys = ON")
    migrations.ensure(conn)
    before = _counts(conn)

    # 2a. numeric
    new_ids = store_numeric(conn, pid, text, si_text, client, mock, tag)
    # 4a. entities (reuse-or-create) — incremental over just the new rows
    ent_stats = entities.resolve_new(conn, new_ids)
    # 3. validation_state for this paper
    set_validation_states(conn, pid)
    conn.close()

    # 2b. claims (ontology-constrained). mock => no claims; real => Bedrock.
    claim_rows = 0
    if real:
        knowledge_engine.extract_papers([pid], mock=False)
        knowledge_engine.audit_quotes()
        c2 = sqlite3.connect(DB_PATH)
        claim_rows = c2.execute("SELECT COUNT(*) FROM evidence_claims WHERE paper_id=?", (pid,)).fetchone()[0]
        c2.close()

    # 4b. harmonization (rebuild derived: canonical cols + harmonized + features)
    harmonize.build()

    # 5. claim <-> number link for this paper
    c3 = sqlite3.connect(DB_PATH); c3.execute("PRAGMA foreign_keys = ON")
    migrations.ensure(c3)
    linked = link_claims.link_for_paper(c3, pid)
    c3.close()

    # 6. rebuild candidate matrix from immutable raw (updates counts/contradictions/confidence)
    knowledge_engine.build_matrix()

    # 7. audit row + summary
    conn = sqlite3.connect(DB_PATH); conn.execute("PRAGMA foreign_keys = ON")
    after = _counts(conn)
    conn.execute(
        """INSERT INTO integration_runs
           (paper_id, mode, numeric_rows, claim_rows, entities_reused, entities_created,
            claims_linked, candidates_after, contradictions_after, status, notes, created_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, "real" if real else "mock", len(new_ids), claim_rows,
         ent_stats["reused"], ent_stats["created"], linked, after["candidates"],
         after["contradictions"], "ok",
         f"candidates {before['candidates']}->{after['candidates']}; "
         f"entities {before['entities']}->{after['entities']}", TODAY))
    conn.commit()
    conn.close()
    return {"paper_id": pid, "numeric_rows": len(new_ids), "claim_rows": claim_rows,
            "entities_reused": ent_stats["reused"], "entities_created": ent_stats["created"],
            "claims_linked": linked, "before": before, "after": after}


def _permanent_pdf(pdf_path: Path) -> Path:
    """Move a dropped PDF into the durable article store (ARTICLE_DIR), mirroring
    auto_ingest, so the pdf_sources map never points at a transient inbox file."""
    import shutil
    import time
    article_dir = auto_ingest.ARTICLE_DIR
    article_dir.mkdir(parents=True, exist_ok=True)
    target = article_dir / pdf_path.name
    if pdf_path.resolve() == target.resolve():
        return target
    if target.exists():
        target = article_dir / f"{target.stem}_{int(time.time())}{target.suffix}"
    shutil.copy2(str(pdf_path), str(target))
    return target


def register_pdf(pdf_path: Path) -> tuple[str, str, str | None, bool]:
    """Register a dropped PDF: text + metadata + pdf map, dedupe-aware.
    Returns (paper_id, text, si_text, is_update)."""
    text = auto_ingest.extract_text(pdf_path)
    meta = auto_ingest.infer_metadata(pdf_path, text)
    permanent = _permanent_pdf(pdf_path)
    conn = sqlite3.connect(DB_PATH); conn.execute("PRAGMA foreign_keys = ON")
    migrations.ensure(conn)
    dup = find_duplicate(conn, meta.get("doi"), meta.get("title"))
    if dup:
        pid, is_update = dup, True
        conn.execute("UPDATE papers SET last_updated=? WHERE paper_id=?", (TODAY, pid))
        conn.commit()
    else:
        meta["paper_id"] = auto_ingest.unique_paper_id(conn, meta["paper_id"], permanent)
        auto_ingest.insert_paper(conn, meta, text)
        conn.commit()
        pid, is_update = meta["paper_id"], False
    conn.close()
    # Never clobber an existing, on-disk mapping when updating a known paper.
    import json
    existing = {}
    if PDF_MAP_PATH.exists():
        existing = json.loads(PDF_MAP_PATH.read_text(encoding="utf-8"))
    current = existing.get(pid)
    if not (is_update and current and (ROOT / current).exists()):
        auto_ingest.update_pdf_map(pid, permanent)
    return pid, text, None, is_update


def reindex() -> dict:
    """Deterministic backfill: rebuild every derived layer from immutable raw.
    Use once after installing v2, or after bulk edits. Does NOT re-extract."""
    c = sqlite3.connect(DB_PATH); c.execute("PRAGMA foreign_keys = ON")
    migrations.ensure(c)
    entities.rebuild_all(c)
    set_validation_states(c)
    c.close()
    harmonize.build()
    c = sqlite3.connect(DB_PATH); c.execute("PRAGMA foreign_keys = ON")
    link_stats = link_claims.rebuild_all(c)
    c.close()
    knowledge_engine.build_matrix()
    c = sqlite3.connect(DB_PATH)
    summary = _counts(c); summary["claims_linked"] = link_stats["linked"]
    c.close()
    return summary


def print_summary(result: dict) -> None:
    b, a = result["before"], result["after"]
    print(f"\n=== integrated {result['paper_id']} ===")
    print(f"  numeric rows added   : {result['numeric_rows']}")
    print(f"  claims added         : {result['claim_rows']}  (linked to numbers: {result['claims_linked']})")
    print(f"  entities reused      : {result['entities_reused']}   created: {result['entities_created']}")
    print(f"  candidates   {b['candidates']:4d} -> {a['candidates']:4d}")
    print(f"  contradictions {b['contradictions']:3d} -> {a['contradictions']:3d}")
    print(f"  corpus: {a['papers']} papers, {a['numeric']} numeric rows, {a['entities']} canonical entities")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", type=Path, help="path to a new PDF to integrate")
    src.add_argument("--paper-id", help="reprocess an existing paper (must be in pdf_sources.json)")
    src.add_argument("--inbox", action="store_true", help="integrate every PDF in inbox/pdfs")
    src.add_argument("--reindex", action="store_true", help="rebuild derived layers only (no extraction)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="regex extractor (no Bedrock; runs anywhere)")
    mode.add_argument("--real", action="store_true", help="Claude on Bedrock (needs boto3 + AWS creds)")
    ap.add_argument("--watch", action="store_true", help="with --inbox: keep watching for new PDFs")
    ap.add_argument("--interval", type=int, default=300, help="watch poll interval (seconds)")
    args = ap.parse_args()
    mock = not args.real  # default to mock unless --real

    if args.reindex:
        print(f"Reindex (derived layers rebuilt from raw): {reindex()}")
        return 0

    if args.inbox and args.watch:
        import time
        inbox = ROOT / "inbox" / "pdfs"
        print(f"Watching {inbox} every {args.interval}s (Ctrl-C to stop)...")
        while True:
            for pdf in sorted(inbox.glob("*.pdf")):
                pid, text, si, upd = register_pdf(pdf)
                print(f"{'UPDATING' if upd else 'NEW'} {pdf.name} -> {pid}")
                if text.strip():
                    print_summary(integrate_paper(pid, text=text, si_text=si, mock=mock, real=args.real))
                pdf.unlink(missing_ok=True)  # copied to the durable store; avoid reprocessing
            time.sleep(max(30, args.interval))

    targets: list[tuple[str, str, str | None]] = []
    if args.pdf:
        pid, text, si, upd = register_pdf(args.pdf)
        print(f"{'UPDATING existing' if upd else 'NEW'} paper: {pid}")
        targets.append((pid, text, si))
    elif args.inbox:
        inbox = ROOT / "inbox" / "pdfs"
        processed = []
        for pdf in sorted(inbox.glob("*.pdf")):
            pid, text, si, upd = register_pdf(pdf)
            print(f"{'UPDATING' if upd else 'NEW'} {pdf.name} -> {pid}")
            targets.append((pid, text, si))
            processed.append(pdf)
        if not targets:
            print(f"No PDFs in {inbox}")
            return 0
    else:  # --paper-id: pull cached text from the mapped PDF
        import json
        pmap = json.loads(PDF_MAP_PATH.read_text(encoding="utf-8"))
        rel = pmap.get(args.paper_id)
        if not rel:
            print(f"{args.paper_id} not in pdf_sources.json", file=sys.stderr)
            return 2
        text = auto_ingest.extract_text((ROOT / rel).resolve())
        targets.append((args.paper_id, text, None))

    for pid, text, si in targets:
        if not text.strip():
            print(f"[skip] {pid}: no readable text")
            continue
        result = integrate_paper(pid, text=text, si_text=si, mock=mock, real=args.real)
        print_summary(result)
    if args.inbox:
        for pdf in processed:
            pdf.unlink(missing_ok=True)  # copied to the durable store; clear the inbox
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
