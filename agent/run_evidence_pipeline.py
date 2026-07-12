#!/usr/bin/env python3
"""Run audit + table extraction + figure preparation + numeric proposal."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(args: list[str]) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-id", action="append")
    parser.add_argument("--min-score", type=int, default=5)
    parser.add_argument("--dpi", type=int, default=400)
    args = parser.parse_args()
    py = sys.executable
    run([py, str(HERE / "audit_pdf_evidence.py")])
    scope = [part for pid in (args.paper_id or []) for part in ("--paper-id", pid)]
    run([py, str(HERE / "evidence_pipeline.py"), "tables", "--min-score", str(args.min_score), *scope])
    run([py, str(HERE / "evidence_pipeline.py"), "figures", "--min-score", str(args.min_score),
         "--dpi", str(args.dpi), *scope])
    run([py, str(HERE / "evidence_pipeline.py"), "propose"])
    print("Review db/evidence_staging/numeric_review.jsonl, set accepted rows to status=approved, then run:")
    print(f"  {py} agent/evidence_pipeline.py validate")
    print(f"  {py} agent/evidence_pipeline.py promote --dry-run")
    print(f"  {py} agent/evidence_pipeline.py promote")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
