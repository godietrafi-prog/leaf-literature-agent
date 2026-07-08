#!/usr/bin/env python3
"""
eval_extract.py — the extraction guardrail (SYSTEM_ARCHITECTURE §2a).

Scores an extractor against the 31 hand-curated seed records (the gold standard)
BEFORE its output on new papers is trusted. Reports recall, precision, and
value-accuracy, writes an eval_runs row, and enforces a release gate.

  recall         = matched gold rows / all gold rows          (did it find them?)
  precision      = matched pred rows / all pred rows          (did it invent any?)
  value_accuracy = value-correct matches / matched rows       (are the numbers right?)

Matching is per (paper_id, quantity); a value is "correct" if within tolerance
(default 1.0 absolute for %-quantities). This is the operational form of the
project's core rule — the extractor must never fabricate a number the paper does
not report — measured instead of hoped for.

Usage:
    python3 agent/eval_extract.py               # mock extractor (runs anywhere)
    py_work agent/eval_extract.py --real        # Claude on Bedrock (boto3 Converse;
                                                #   run with the metaflow venv that
                                                #   already has boto3 + AWS creds)

Source-text note: with no seed PDFs on disk yet, --mock scores the extractor
against each paper's own narrative body (papers.key_findings) as a stand-in for
the source text — enough to validate the harness and scoring. When PDFs + SI
arrive, point `paper_source_text()` at them and the same harness scores the real
LLM extractor unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "db", "leaf_lit.db")
PDF_MAP_PATH = os.path.join(ROOT, "db", "pdf_sources.json")
PDF_TXT_CACHE = os.path.join(ROOT, "db", "pdf_text_cache")
MAX_PDF_CHARS = 80000  # bound Bedrock input cost; papers rarely exceed this
TODAY = date.today().isoformat()


def _load_pdf_map():
    if not os.path.exists(PDF_MAP_PATH):
        return {}
    raw = json.load(open(PDF_MAP_PATH, encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def pdf_text(rel_path: str) -> str:
    """Extract (and cache) text from a source PDF. Cached as a .txt so re-runs
    don't re-parse. Returns '' if the PDF or parser is unavailable."""
    abspath = os.path.normpath(os.path.join(ROOT, rel_path))
    os.makedirs(PDF_TXT_CACHE, exist_ok=True)
    cache = os.path.join(PDF_TXT_CACHE, os.path.basename(abspath) + ".txt")
    if os.path.exists(cache):
        return open(cache, encoding="utf-8").read()
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    if not os.path.exists(abspath):
        return ""
    reader = PdfReader(abspath)
    text = "\n".join((p.extract_text() or "") for p in reader.pages)[:MAX_PDF_CHARS]
    open(cache, "w", encoding="utf-8").write(text)
    return text

# release gate — no new-paper extraction is auto-trusted until these clear.
# NB: precision is NOT gated. The seed gold records one "headline" value per
# quantity, while a good extractor reports *every* value in the paper (all
# conditions/treatments), so extra predictions are thoroughness, not false
# positives — precision-vs-sparse-gold is not meaningful. Recall and value
# accuracy are the two metrics sparse gold can measure fairly.
GATE = {"recall": 0.70, "value_accuracy": 0.75}
VALUE_TOL = 1.0  # absolute tolerance for a "correct" %-value match


def paper_source_text(conn, paper_id: str, pdf_map: dict) -> tuple[str, str]:
    """Return (text, source_kind) for the extractor. Prefer the real PDF; fall
    back to the curated narrative body (a weaker, semi-circular proxy)."""
    if paper_id in pdf_map:
        txt = pdf_text(pdf_map[paper_id])
        if txt.strip():
            return txt, "pdf"
    row = conn.execute(
        "SELECT COALESCE(scientific_story,'') || ' ' || COALESCE(key_findings,'') "
        "FROM papers WHERE paper_id = ?", (paper_id,)
    ).fetchone()
    return (row[0] if row else ""), "narrative_proxy"


def gold_results(conn, paper_id: str):
    """Gold numeric rows for a paper: {quantity: value}."""
    rows = conn.execute(
        "SELECT quantity, value FROM numeric_results WHERE paper_id = ? AND value IS NOT NULL",
        (paper_id,),
    ).fetchall()
    return {q: v for q, v in rows}


def run_eval(use_real: bool = False, pdf_only: bool = False):
    conn = sqlite3.connect(DB_PATH)
    pdf_map = _load_pdf_map()
    client = None
    if use_real:
        from bedrock_client import BedrockClient  # lazy
        client = BedrockClient()
        print(f"  model: {client.model}  |  PDFs mapped: {len(pdf_map)}"
              f"{'  (--pdf-only)' if pdf_only else ''}\n")

    paper_ids = [r[0] for r in conn.execute("SELECT paper_id FROM papers ORDER BY paper_id")]

    tot_gold = tot_pred = matched = value_ok = 0
    papers_with_gold = 0
    n_pdf = 0
    per_paper = []

    for pid in paper_ids:
        gold = gold_results(conn, pid)
        if not gold:
            continue
        if pdf_only and pid not in pdf_map:
            continue
        text, kind = paper_source_text(conn, pid, pdf_map)
        if kind == "pdf":
            n_pdf += 1
        papers_with_gold += 1
        try:
            out = extract.extract_paper(text, client=client, mock=not use_real)
        except Exception as e:  # noqa: BLE001 — one bad paper must not abort the eval
            print(f"  [warn] extraction failed for {pid}: {str(e)[:90]} — counted as 0 predictions")
            out = {"numeric_results": []}
        # keep ALL predicted values per quantity — a good extractor reports every
        # reported value; match gold against any of them.
        pred = {}
        for r in out.get("numeric_results", []):
            if r.get("value") is not None:
                pred.setdefault(r["quantity"], []).append(r["value"])

        tot_gold += len(gold)
        tot_pred += sum(len(v) for v in pred.values())  # breadth (all rows)
        p_match = p_ok = 0
        for q, gval in gold.items():
            if q in pred:
                matched += 1
                p_match += 1
                if any(abs(v - gval) <= VALUE_TOL for v in pred[q]):
                    value_ok += 1
                    p_ok += 1
        per_paper.append((pid, len(gold), sum(len(v) for v in pred.values()), p_match, p_ok))

    recall = matched / tot_gold if tot_gold else 0.0
    value_accuracy = value_ok / matched if matched else 0.0

    model = client.model if client else "mock-regex-baseline"
    # "precision" column repurposed to store extraction breadth (pred rows / gold rows)
    breadth = round(tot_pred / tot_gold, 2) if tot_gold else 0.0
    notes = (f"papers={papers_with_gold}; pdf_sourced={n_pdf}; "
             f"proxy_sourced={papers_with_gold - n_pdf}; breadth_pred_per_gold={breadth}"
             + ("; pdf_only" if pdf_only else ""))
    conn.execute(
        """INSERT INTO eval_runs
           (run_date, model, prompt_version, recall, precision, value_accuracy, notes)
           VALUES (?,?,?,?,?,?,?)""",
        (TODAY, model, "v1", round(recall, 4), breadth, round(value_accuracy, 4), notes),
    )
    conn.commit()
    conn.close()

    # report
    print(f"Extraction eval — model: {model}  ({TODAY})")
    print(f"  papers with gold numeric rows : {papers_with_gold}  "
          f"(real PDF: {n_pdf}, narrative proxy: {papers_with_gold - n_pdf})")
    print(f"  gold rows / predicted rows    : {tot_gold} / {tot_pred}   matched: {matched}")
    print(f"  recall         : {recall:6.1%}   (gate {GATE['recall']:.0%})   — found the gold quantities")
    print(f"  value_accuracy : {value_accuracy:6.1%}   (gate {GATE['value_accuracy']:.0%})   — matched value within ±{VALUE_TOL}")
    print(f"  breadth        : {breadth:>5}x    (diagnostic) — pred rows per gold row; >1 = thorough, not wrong")
    passed = recall >= GATE["recall"] and value_accuracy >= GATE["value_accuracy"]
    print(f"  RELEASE GATE   : {'PASS ✅' if passed else 'FAIL ❌ (extraction stays needs_human)'}")

    worst = sorted(per_paper, key=lambda r: (r[3] - r[1], -r[2]))[:5]
    print("\n  weakest papers (gold, pred, matched, value_ok):")
    for pid, ng, npd, nm, nok in worst:
        print(f"    {pid:<32} {ng}  {npd}  {nm}  {nok}")
    return passed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="use Claude on Bedrock (run with py_work)")
    ap.add_argument("--pdf-only", action="store_true",
                    help="score only papers backed by a real PDF (the genuine, non-circular eval)")
    args = ap.parse_args()
    ok = run_eval(use_real=args.real, pdf_only=args.pdf_only)
    sys.exit(0 if ok else 1)
