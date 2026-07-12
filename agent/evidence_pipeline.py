#!/usr/bin/env python3
"""Conservative table / figure evidence extraction pipeline.

Stages:
  tables   Extract detected PDF tables to CSV and a review manifest.
  figures  Render/crop candidate figures and write calibration manifests.
  propose  Parse explicit numeric cells into an UNAPPROVED review queue.
  validate Validate a review queue without writing the scientific DB.
  promote  Insert only rows explicitly marked status=approved.

The pipeline never treats OCR or plot pixels as verified reported values.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = ROOT / "db" / "evidence_candidate_audit.csv"
DB_PATH = ROOT / "db" / "leaf_lit.db"
STAGING = ROOT / "db" / "evidence_staging"
TABLE_DIR = STAGING / "tables"
FIGURE_DIR = STAGING / "figures"
TABLE_MANIFEST = STAGING / "table_manifest.jsonl"
FIGURE_MANIFEST = STAGING / "figure_manifest.jsonl"
REVIEW_QUEUE = STAGING / "numeric_review.jsonl"
TODAY = date.today().isoformat()

MEAN_SD_RE = re.compile(
    r"(?<![\w.])(?P<mean>[<>~]?-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*"
    r"(?:\u00b1|\+/-)\s*(?P<error>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
)
PLAIN_NUMBER_RE = re.compile(r"^[<>~]?-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?:\s*%)?$", re.I)
P_VALUE_RE = re.compile(r"\bp\s*(?:=|<|>)\s*(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", re.I)
UNIT_RE = re.compile(
    r"(%|ppbv|ppm|ppb|mg\s*/\s*(?:g|kg|100\s*g|mL)|\u00b5g\s*/\s*(?:g|kg|mL)|"
    r"g\s*/\s*(?:g|kg|100\s*mL)|U\s*/\s*(?:g|mL)|AU|nmol\s*/\s*min)", re.I
)
QUANTITY_CUES = [
    (re.compile(r"hexanal", re.I), "hexanal_conc"),
    (re.compile(r"lipoxygenase|\bLOX\b", re.I), "LOX_activity"),
    (re.compile(r"chlorophyll", re.I), "chlorophyll_content"),
    (re.compile(r"protein\s+(?:content|purity)|purity", re.I), "protein_purity_pct"),
    (re.compile(r"protein\s+(?:yield|recovery)|\byield\b|\brecovery\b", re.I), "yield_pct"),
    (re.compile(r"\bL\*", re.I), "color_L"),
    (re.compile(r"\ba\*", re.I), "color_a"),
    (re.compile(r"\bb\*", re.I), "color_b"),
    (re.compile(r"classification.*accuracy|accuracy", re.I), "sensory_classification_accuracy"),
]


@dataclass(frozen=True)
class Candidate:
    paper_id: str
    source: str
    pdf_path: str
    page: int
    kind: str
    label: str
    score: int
    topics: str
    caption: str

    @property
    def path(self) -> Path:
        return (ROOT / self.pdf_path).resolve()

    @property
    def key(self) -> str:
        raw = f"{self.paper_id}|{self.source}|{self.page}|{self.kind}|{self.label}"
        return hashlib.sha1(raw.encode()).hexdigest()[:12]


def load_candidates(kind: str, paper_ids: set[str] | None, min_score: int) -> list[Candidate]:
    with AUDIT_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    out = []
    seen = set()
    for row in rows:
        if row["kind"] != kind or int(row["priority_score"]) < min_score:
            continue
        if paper_ids and row["paper_id"] not in paper_ids:
            continue
        candidate = Candidate(
            row["paper_id"], row["source"], row["pdf_path"], int(row["page"]),
            row["kind"], row["label"], int(row["priority_score"]), row["topics"], row["caption"],
        )
        # Caption extraction can produce duplicates on complex two-column pages.
        identity = (candidate.paper_id, candidate.source, candidate.page, candidate.kind, candidate.label)
        if identity not in seen:
            out.append(candidate)
            seen.add(identity)
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def clean_cell(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def table_clip(page: fitz.Page, candidate: Candidate) -> fitz.Rect | None:
    """Bound a table between its caption and the next table caption."""
    current = caption_rect(page, candidate)
    if not current:
        return None
    later = []
    for number in range(1, 40):
        for rect in page.search_for(f"Table {number}"):
            if rect.y0 > current.y0 + 8:
                later.append(rect.y0)
    bottom = min(later) - 3 if later else page.rect.y1
    return fitz.Rect(page.rect.x0 + 20, max(page.rect.y0, current.y0 - 2),
                     page.rect.x1 - 20, max(current.y1 + 20, bottom))


def extract_tables(candidates: list[Candidate]) -> int:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    docs: dict[Path, fitz.Document] = {}
    for candidate in candidates:
        if not candidate.path.exists():
            continue
        doc = docs.setdefault(candidate.path, fitz.open(candidate.path))
        page = doc[candidate.page - 1]
        clip = table_clip(page, candidate)
        try:
            # Line-based tables are cleanest; text strategy rescues scientific
            # tables that use whitespace instead of ruled borders.
            tables = []
            for strategy in ("lines", "text"):
                tables.extend(page.find_tables(strategy=strategy, clip=clip).tables)
        except Exception as exc:  # noqa: BLE001
            tables = []
            error = f"{type(exc).__name__}: {exc}"
        else:
            error = None
        if not tables:
            manifest.append({
                "candidate_id": candidate.key, "paper_id": candidate.paper_id,
                "source": candidate.source, "page": candidate.page, "label": candidate.label,
                "caption": candidate.caption, "status": "not_detected",
                "backend": "pymupdf", "error": error, "csv_path": None,
            })
            continue
        # Prefer the candidate with the most non-empty cells. This avoids a
        # large whitespace grid beating the actual table.
        table = max(tables, key=lambda t: sum(bool(clean_cell(cell)) for row in t.extract() for cell in row))
        matrix = [[clean_cell(cell) for cell in row] for row in table.extract()]
        out = TABLE_DIR / f"{candidate.paper_id}__{candidate.source}__p{candidate.page}__table_{candidate.label}.csv"
        with out.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(matrix)
        manifest.append({
            "candidate_id": candidate.key, "paper_id": candidate.paper_id,
            "source": candidate.source, "page": candidate.page, "label": candidate.label,
            "caption": candidate.caption, "status": "extracted_unreviewed", "backend": "pymupdf",
            "bbox": list(table.bbox), "rows": len(matrix),
            "columns": max((len(row) for row in matrix), default=0),
            "clip": list(clip) if clip else None,
            "csv_path": str(out.relative_to(ROOT)), "error": None,
        })
    for doc in docs.values():
        doc.close()
    write_jsonl(TABLE_MANIFEST, manifest)
    print(f"Table manifest: {len(manifest)} candidates; "
          f"{sum(r['status'] == 'extracted_unreviewed' for r in manifest)} extracted")
    return 0


def caption_rect(page: fitz.Page, candidate: Candidate) -> fitz.Rect | None:
    needles = [f"Figure {candidate.label}", f"Fig. {candidate.label}", f"Table {candidate.label}"]
    rects = []
    for needle in needles:
        rects.extend(page.search_for(needle))
    return min(rects, key=lambda r: r.y0) if rects else None


def crop_figures(candidates: list[Candidate], dpi: int) -> int:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    docs: dict[Path, fitz.Document] = {}
    for candidate in candidates:
        if not candidate.path.exists():
            continue
        doc = docs.setdefault(candidate.path, fitz.open(candidate.path))
        page = doc[candidate.page - 1]
        cap = caption_rect(page, candidate)
        page_rect = page.rect
        # Scientific figures are commonly above their caption. When caption
        # localization fails, retain the full page rather than risk truncation.
        if cap:
            top = max(page_rect.y0, cap.y0 - page_rect.height * 0.68)
            clip = fitz.Rect(page_rect.x0, top, page_rect.x1, min(page_rect.y1, cap.y1 + 36))
            crop_mode = "above_caption_heuristic"
        else:
            clip = page_rect
            crop_mode = "full_page_fallback"
        pix = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
        out = FIGURE_DIR / f"{candidate.paper_id}__{candidate.source}__p{candidate.page}__figure_{candidate.label}.png"
        pix.save(out)
        manifest.append({
            "candidate_id": candidate.key, "paper_id": candidate.paper_id,
            "source": candidate.source, "page": candidate.page, "label": candidate.label,
            "caption": candidate.caption, "image_path": str(out.relative_to(ROOT)),
            "dpi": dpi, "crop_mode": crop_mode, "clip_pdf_points": list(clip),
            "plot_type": None, "x_axis": None, "y_axis": None,
            "calibration": None, "status": "needs_calibration",
        })
    for doc in docs.values():
        doc.close()
    write_jsonl(FIGURE_MANIFEST, manifest)
    print(f"Figure manifest: rendered {len(manifest)} candidate images at {dpi} DPI")
    return 0


def infer_quantity(blob: str) -> str | None:
    quantities = {quantity for pattern, quantity in QUANTITY_CUES if pattern.search(blob)}
    return next(iter(quantities)) if len(quantities) == 1 else None


def infer_unit(blob: str) -> str | None:
    match = UNIT_RE.search(blob)
    return re.sub(r"\s+", "", match.group(0)) if match else None


def propose_numbers() -> int:
    proposals = []
    for item in read_jsonl(TABLE_MANIFEST):
        if item.get("status") != "extracted_unreviewed" or not item.get("csv_path"):
            continue
        path = ROOT / item["csv_path"]
        rows = list(csv.reader(path.open(encoding="utf-8", newline="")))
        headers = " | ".join(" ".join(row) for row in rows[:3])
        for row_no, row in enumerate(rows, start=1):
            row_blob = " | ".join(clean_cell(cell) for cell in row)
            # A PDF extractor may split "1.84 ± 0.48" over three cells.
            # Remove cell separators only around the dispersion operator while
            # retaining the original row for auditability.
            parse_blob = re.sub(r"(?<=\d\.)\s*\|\s*(?=\d)", "", row_blob)
            parse_blob = re.sub(r"\s*\|\s*(±|\+/-)\s*\|?\s*", r" \1 ", parse_blob)
            parse_blob = re.sub(r"(±|\+/-)\s*\|\s*", r"\1 ", parse_blob)
            context = f"{item.get('caption', '')} | {headers} | {row_blob}"
            # Quantity must be identifiable on the same extracted row. Using a
            # table-level caption for every cell silently mislabels multi-endpoint
            # tables (e.g. purity, yield and colour side by side).
            quantity = infer_quantity(row_blob)
            if not quantity:
                continue
            p_match = P_VALUE_RE.search(context)
            p_value = float(p_match.group(1)) if p_match else None
            unit = infer_unit(context)
            for match_no, match in enumerate(MEAN_SD_RE.finditer(parse_blob), start=1):
                value = float(match.group("mean").lstrip("<>~"))
                sd_error = float(match.group("error"))
                error_type = "reported_dispersion_unknown"
                proposals.append({
                    "proposal_id": hashlib.sha1(
                        f"{item['candidate_id']}|{row_no}|{match_no}|{match.group(0)}".encode()
                    ).hexdigest()[:14],
                    "paper_id": item["paper_id"], "quantity": quantity,
                    "value": value, "unit": unit, "sd_error": sd_error,
                    "error_type": error_type, "n_replicates": None, "p_value": p_value,
                    "method": None, "species": None, "treatment_condition": None,
                    "basis": None,
                    "source_location": f"Table {item['label']}, PDF page {item['page']}, row {row_no}; extracted sequence: {match.group(0)}",
                    "is_from_SI": int(item["source"] == "SI"),
                    "extraction_mode": "table_native", "status": "needs_review",
                    "needs_human": 1,
                    "review_note": "Confirm column/header mapping, treatment, unit and whether dispersion is SD or SEM",
                })
    write_jsonl(REVIEW_QUEUE, proposals)
    print(f"Numeric review queue: {len(proposals)} unapproved proposals")
    return 0


def validation_errors(row: dict, conn: sqlite3.Connection | None = None) -> list[str]:
    errors = []
    required = ("paper_id", "quantity", "value", "source_location", "extraction_mode", "status")
    errors.extend(f"missing {key}" for key in required if row.get(key) in (None, ""))
    try:
        value = float(row.get("value"))
        if not math.isfinite(value):
            errors.append("value is not finite")
    except (TypeError, ValueError):
        errors.append("value is not numeric")
        value = None
    if value is not None and (row.get("unit") == "%" or row.get("quantity", "").endswith("_pct")):
        if not 0 <= value <= 100:
            errors.append("percentage outside 0..100")
    if row.get("error_type") in ("SD", "SEM", "CI95") and row.get("sd_error") is None:
        errors.append("error_type requires sd_error")
    if row.get("status") == "approved":
        if not row.get("unit"):
            errors.append("approved row requires unit")
        if not row.get("treatment_condition"):
            errors.append("approved row requires treatment_condition")
        if row.get("sd_error") is not None and row.get("error_type") not in ("SD", "SEM", "CI95", "range"):
            errors.append("approved row requires resolved error_type")
    if row.get("extraction_mode") == "graph_digitized":
        for key in ("figure_label", "digitization_resolution", "estimated_error"):
            if row.get(key) in (None, ""):
                errors.append(f"graph-derived row missing {key}")
    if conn and row.get("paper_id") and not conn.execute(
        "SELECT 1 FROM papers WHERE paper_id=?", (row["paper_id"],)
    ).fetchone():
        errors.append("paper_id absent from papers table")
    return errors


def validate_queue(path: Path) -> int:
    rows = read_jsonl(path)
    conn = sqlite3.connect(DB_PATH)
    invalid = 0
    for row in rows:
        errors = validation_errors(row, conn)
        if errors:
            invalid += 1
            print(f"{row.get('proposal_id', '?')}: {'; '.join(errors)}")
    conn.close()
    print(f"Validated {len(rows)} rows: {len(rows) - invalid} structurally valid, {invalid} invalid")
    return 1 if invalid else 0


def promote(path: Path, dry_run: bool) -> int:
    rows = read_jsonl(path)
    approved = [row for row in rows if row.get("status") == "approved"]
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    invalid = [(row, validation_errors(row, conn)) for row in approved]
    invalid = [(row, errs) for row, errs in invalid if errs]
    if invalid:
        for row, errs in invalid:
            print(f"REJECT {row.get('proposal_id', '?')}: {'; '.join(errs)}")
        conn.close()
        return 1
    inserted = 0
    for row in approved:
        source = row["source_location"]
        duplicate = conn.execute(
            """SELECT 1 FROM numeric_results
               WHERE paper_id=? AND quantity=? AND value=? AND source_location=?
                 AND provenance LIKE 'evidence:%'""",
            (row["paper_id"], row["quantity"], row["value"], source),
        ).fetchone()
        if duplicate:
            continue
        if not dry_run:
            conn.execute(
                """INSERT INTO numeric_results
                   (paper_id, quantity, value, unit, sd_error, error_type, n_replicates,
                    p_value, method, species, treatment_condition, basis, source_location,
                    is_from_SI, needs_human, provenance, verified, verified_note,
                    verified_date, extracted_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["paper_id"], row["quantity"], row["value"], row.get("unit"),
                    row.get("sd_error"), row.get("error_type"), row.get("n_replicates"),
                    row.get("p_value"), row.get("method"), row.get("species"),
                    row.get("treatment_condition"), row.get("basis"), source,
                    int(row.get("is_from_SI", 0)), int(row.get("needs_human", 0)),
                    f"evidence:{row['extraction_mode']}", 1,
                    row.get("review_note") or "Approved in evidence review queue", TODAY, TODAY,
                ),
            )
        inserted += 1
    if not dry_run:
        conn.commit()
    conn.close()
    if not dry_run and inserted:
        import harmonize
        harmonize.build()
    print(f"{'Would promote' if dry_run else 'Promoted'} {inserted} approved rows; "
          f"{len(rows) - len(approved)} unapproved rows ignored")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("tables", "figures"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--paper-id", action="append")
        cmd.add_argument("--min-score", type=int, default=5)
        if name == "figures":
            cmd.add_argument("--dpi", type=int, default=400)
    sub.add_parser("propose")
    validate = sub.add_parser("validate")
    validate.add_argument("--queue", type=Path, default=REVIEW_QUEUE)
    promote_cmd = sub.add_parser("promote")
    promote_cmd.add_argument("--queue", type=Path, default=REVIEW_QUEUE)
    promote_cmd.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command in ("tables", "figures"):
        candidates = load_candidates(args.command[:-1] if args.command.endswith("s") else args.command,
                                     set(args.paper_id) if args.paper_id else None, args.min_score)
        return extract_tables(candidates) if args.command == "tables" else crop_figures(candidates, args.dpi)
    if args.command == "propose":
        return propose_numbers()
    if args.command == "validate":
        return validate_queue(args.queue)
    return promote(args.queue, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
