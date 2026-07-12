#!/usr/bin/env python3
"""List, edit, approve, or reject staged evidence proposals."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE = ROOT / "db" / "evidence_staging" / "numeric_review.jsonl"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def save(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_value(raw: str):
    if raw.lower() in ("none", "null"):
        return None
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--status")
    listing.add_argument("--paper-id")
    listing.add_argument("--limit", type=int, default=30)
    show = sub.add_parser("show")
    show.add_argument("proposal_id")
    for command in ("approve", "reject"):
        cmd = sub.add_parser(command)
        cmd.add_argument("proposal_id")
        cmd.add_argument("--note")
        cmd.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
    args = parser.parse_args()
    rows = load(args.queue)
    if args.command == "list":
        selected = [r for r in rows if (not args.status or r.get("status") == args.status)
                    and (not args.paper_id or r.get("paper_id") == args.paper_id)]
        for row in selected[:args.limit]:
            print(f"{row['proposal_id']}  {row['status']:<12} {row['paper_id']}  "
                  f"{row['quantity']}={row['value']} {row.get('unit') or ''}  "
                  f"{row['source_location']}")
        print(f"Shown {min(len(selected), args.limit)} of {len(selected)} matching proposals")
        return 0
    matches = [r for r in rows if r.get("proposal_id") == args.proposal_id]
    if len(matches) != 1:
        raise SystemExit(f"proposal_id matched {len(matches)} rows")
    row = matches[0]
    if args.command == "show":
        print(json.dumps(row, ensure_ascii=False, indent=2))
        return 0
    for assignment in args.set:
        if "=" not in assignment:
            raise SystemExit(f"invalid --set {assignment!r}; expected FIELD=VALUE")
        field, value = assignment.split("=", 1)
        row[field] = parse_value(value)
    row["status"] = "approved" if args.command == "approve" else "rejected"
    if args.note:
        row["review_note"] = args.note
    if row["status"] == "approved":
        row["needs_human"] = 0
    save(args.queue, rows)
    print(f"{row['proposal_id']} -> {row['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
