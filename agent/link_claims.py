#!/usr/bin/env python3
"""Bridge the two previously-disconnected knowledge layers.

`evidence_claims` says *that* a treatment changed an outcome (direction + optional
effect_value); `numeric_results` carries the actual measured numbers. Until now
there was no link between them, so "show me the numbers behind this DOE factor"
was unanswerable. This module populates `claim_number_link` (and sets
`evidence_claims.numeric_result_id`) using a deterministic matcher, per paper:

  1. value_outcome — same paper, the numeric row's quantity maps to the claim's
     ontology outcome_id (via ontology_match), AND the values agree within tol.
  2. outcome_only  — same paper + same outcome_id, unambiguous single candidate,
     when the claim reports a direction but no numeric effect_value.

It never links across papers and prefers the closest value; ties are broken by
source_location overlap. Fully deterministic and incremental.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import date
from pathlib import Path

import migrations
import ontology_match

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "leaf_lit.db"
VERSION = "claimlink-v1"
TODAY = date.today().isoformat()


def _value_tol(a: float, b: float) -> bool:
    """Values agree within 1.0 absolute (percent-scale) or 2% relative."""
    if a is None or b is None:
        return False
    if abs(a - b) <= 1.0:
        return True
    scale = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / scale <= 0.02


def _overlap(a: str | None, b: str | None) -> int:
    ta = set(re.sub(r"[^a-z0-9 ]", " ", (a or "").lower()).split())
    tb = set(re.sub(r"[^a-z0-9 ]", " ", (b or "").lower()).split())
    return len(ta & tb)


def link_for_paper(conn: sqlite3.Connection, paper_id: str) -> int:
    numeric = conn.execute(
        "SELECT result_id, quantity, value, source_location FROM numeric_results WHERE paper_id=?",
        (paper_id,)).fetchall()
    if not numeric:
        return 0
    # precompute outcome_id for each numeric row
    num = []
    for result_id, quantity, value, src in numeric:
        oid = ontology_match.match_quantity(quantity)["outcome_id"]
        num.append((result_id, oid, value, src))

    claims = conn.execute(
        """SELECT claim_id, outcome_id, effect_value, source_location, source_quote
           FROM evidence_claims WHERE paper_id=? AND outcome_id IS NOT NULL""",
        (paper_id,)).fetchall()
    linked = 0
    for claim_id, outcome_id, effect_value, csrc, cquote in claims:
        same_outcome = [r for r in num if r[1] == outcome_id]
        if not same_outcome:
            continue
        best = None  # (score, result_id, method)
        if effect_value is not None:
            candidates = [r for r in same_outcome if _value_tol(r[2], effect_value)]
            for result_id, _oid, value, src in candidates:
                score = 1.0 - min(abs((value or 0) - effect_value) / max(abs(effect_value), 1e-9), 1.0)
                score += 0.01 * _overlap(src, csrc or cquote)
                if best is None or score > best[0]:
                    best = (round(min(score, 1.0), 4), result_id, "value_outcome")
        if best is None and len(same_outcome) == 1:
            # unambiguous outcome match with no numeric effect to compare
            best = (0.5, same_outcome[0][0], "outcome_only")
        if best is None:
            continue
        score, result_id, method = best
        conn.execute(
            """INSERT INTO claim_number_link
               (claim_id, result_id, match_method, match_score, mapping_version, created_date)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(claim_id, result_id) DO UPDATE SET
                 match_method=excluded.match_method, match_score=excluded.match_score,
                 mapping_version=excluded.mapping_version""",
            (claim_id, result_id, method, score, VERSION, TODAY))
        conn.execute("UPDATE evidence_claims SET numeric_result_id=? WHERE claim_id=?",
                     (result_id, claim_id))
        linked += 1
    conn.commit()
    return linked


def rebuild_all(conn: sqlite3.Connection) -> dict:
    migrations.ensure(conn)
    conn.execute("DELETE FROM claim_number_link")
    conn.execute("UPDATE evidence_claims SET numeric_result_id=NULL")
    papers = [r[0] for r in conn.execute(
        "SELECT DISTINCT paper_id FROM evidence_claims")]
    total = sum(link_for_paper(conn, pid) for pid in papers)
    n_claims = conn.execute("SELECT COUNT(*) FROM evidence_claims WHERE outcome_id IS NOT NULL").fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO run_state(key,value) VALUES('last_claim_link',?)", (TODAY,))
    conn.commit()
    return {"linked": total, "linkable_claims": n_claims}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paper-id")
    args = ap.parse_args()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    migrations.ensure(conn)
    if args.paper_id:
        n = link_for_paper(conn, args.paper_id)
        print(f"Linked {n} claims in {args.paper_id}")
    else:
        print(f"Claim-number link: {rebuild_all(conn)}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
