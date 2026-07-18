#!/usr/bin/env python3
"""Auto-ingest PDFs dropped into inbox/pdfs.

This is intentionally conservative: it never invents metadata that is not in the
PDF. Missing/uncertain values are marked for human verification in the dashboard.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INBOX = ROOT / "inbox" / "pdfs"
ARTICLE_DIR = ROOT.parent / "Leaf_Protein_Extraction" / "literature" / "pdfs_provided_by_user"
DB_PATH = ROOT / "db" / "leaf_lit.db"
PDF_MAP_PATH = ROOT / "db" / "pdf_sources.json"
PDF_TXT_CACHE = ROOT / "db" / "pdf_text_cache"
TODAY = date.today().isoformat()
MAX_TEXT_CHARS = 80000

sys.path.insert(0, str(HERE))
import extract  # noqa: E402


def clean_id(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return re.sub(r"_+", "_", text)[:70] or "paper"


def run(cmd: list[str], *, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=check)


def extract_text(pdf_path: Path) -> str:
    PDF_TXT_CACHE.mkdir(parents=True, exist_ok=True)
    cache = PDF_TXT_CACHE / f"{pdf_path.name}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="ignore")[:MAX_TEXT_CHARS]

    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        tmp = cache.with_suffix(".tmp.txt")
        proc = run([pdftotext, "-layout", str(pdf_path), str(tmp)], check=False)
        if proc.returncode == 0 and tmp.exists():
            text = tmp.read_text(encoding="utf-8", errors="ignore")
            cache.write_text(text, encoding="utf-8")
            tmp.unlink(missing_ok=True)
            return text[:MAX_TEXT_CHARS]

    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    reader = PdfReader(str(pdf_path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    cache.write_text(text, encoding="utf-8")
    return text[:MAX_TEXT_CHARS]


def first_nonempty(lines: list[str], start: int = 0) -> str:
    for line in lines[start:]:
        s = line.strip()
        if s:
            return re.sub(r"\s+", " ", s)
    return ""


def infer_metadata(pdf_path: Path, text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines()]
    title = ""
    for i, line in enumerate(lines[:80]):
        if re.search(r"\b(RESEARCH ARTICLE|OPEN ACCESS|ARTICLE|ABSTRACT)\b", line, re.I):
            cand = first_nonempty(lines, i + 1)
            if cand and len(cand) > 20:
                title = cand
                break
    if not title:
        title = first_nonempty(lines) or pdf_path.stem
    title = re.sub(r"\s+", " ", title).strip()

    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, re.I)
    doi = doi_match.group(0).rstrip(".,);]") if doi_match else None

    years = [int(y) for y in re.findall(r"\b(20[0-3]\d|19\d{2})\b", text[:6000])]
    year = max(years) if years else None

    authors = ""
    if title:
        try:
            idx = next(i for i, ln in enumerate(lines[:120]) if title[:40] in re.sub(r"\s+", " ", ln))
            authors = first_nonempty(lines, idx + 1)
        except StopIteration:
            authors = ""
    if len(authors) > 240 or re.search(r"abstract|keywords|correspondence", authors, re.I):
        authors = ""

    pid_base = clean_id(((authors.split()[0] + "_") if authors else "") + (str(year) if year else "") + "_" + title)
    if not re.search(r"\d{4}", pid_base) and year:
        pid_base = f"{pid_base}_{year}"
    if not pid_base.startswith("auto_"):
        pid_base = f"auto_{pid_base}"

    return {
        "paper_id": pid_base,
        "doi": doi,
        "title": title,
        "authors": authors or None,
        "year": year,
        "venue": None,
    }


def unique_paper_id(conn: sqlite3.Connection, wanted: str, pdf_path: Path) -> str:
    if not conn.execute("SELECT 1 FROM papers WHERE paper_id=?", (wanted,)).fetchone():
        return wanted
    suffix = hashlib.sha1(str(pdf_path).encode()).hexdigest()[:8]
    candidate = f"{wanted}_{suffix}"
    n = 2
    while conn.execute("SELECT 1 FROM papers WHERE paper_id=?", (candidate,)).fetchone():
        candidate = f"{wanted}_{suffix}_{n}"
        n += 1
    return candidate


def update_pdf_map(paper_id: str, pdf_path: Path) -> None:
    data = {}
    if PDF_MAP_PATH.exists():
        data = json.loads(PDF_MAP_PATH.read_text(encoding="utf-8"))
    rel = os.path.relpath(pdf_path, ROOT).replace(os.sep, "/")
    data[paper_id] = rel
    PDF_MAP_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def insert_paper(conn: sqlite3.Connection, meta: dict, text: str) -> None:
    pid = meta["paper_id"]
    story = (
        "Auto-ingested from a user-supplied PDF. Metadata and extracted numbers "
        "should be reviewed in the dashboard verification workflow."
    )
    abstract = ""
    m = re.search(r"\bABSTRACT\b(.{300,1800})", text, re.I | re.S)
    if m:
        abstract = re.sub(r"\s+", " ", m.group(1)).strip()[:1200]
    findings = abstract or "Awaiting human summary."

    conn.execute("DELETE FROM papers WHERE paper_id=?", (pid,))
    conn.execute(
        """INSERT INTO papers (paper_id, doi, title, authors, year, venue,
           source_type, system, extraction_method_family, relevance,
           verification_level, access_status, si_status, discovery,
           scientific_story, key_findings, added_date, last_updated)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            pid, meta.get("doi"), meta.get("title"), meta.get("authors"), meta.get("year"),
            meta.get("venue"), "peer-reviewed" if meta.get("doi") else None,
            "unknown", "unknown", "Medium", "full_text", "owner_supplied", "unknown",
            "owner_pdf_drop", story, findings, TODAY, TODAY,
        ),
    )
    for cat in ("source:owner_pdf_drop", "status:auto_ingested"):
        conn.execute("INSERT OR IGNORE INTO paper_categories (paper_id, category) VALUES (?,?)", (pid, cat))


def store_mock_results(conn: sqlite3.Connection, paper_id: str, text: str) -> int:
    out = extract.extract_paper(text, mock=True)
    conn.execute("DELETE FROM numeric_results WHERE paper_id=? AND provenance='auto_mock'", (paper_id,))
    n = 0
    for row in out.get("numeric_results", []):
        if row.get("value") is None:
            continue
        conn.execute(
            """INSERT INTO numeric_results
               (paper_id, quantity, value, unit, sd_error, error_type, n_replicates,
                p_value, method, species, treatment_condition, basis, source_location,
                is_from_SI, needs_human, provenance, extracted_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                paper_id, row.get("quantity"), row.get("value"), row.get("unit"),
                row.get("sd_error"), row.get("error_type"), row.get("n_replicates"),
                row.get("p_value"), row.get("method"), row.get("species"),
                row.get("treatment_condition"), row.get("basis"), row.get("source_location"),
                int(row.get("is_from_SI") or 0), 1, "auto_mock", TODAY,
            ),
        )
        n += 1
    return n


def ingest_one(pdf_path: Path) -> tuple[str, int]:
    ARTICLE_DIR.mkdir(parents=True, exist_ok=True)
    target = ARTICLE_DIR / pdf_path.name
    if pdf_path.resolve() != target.resolve():
        if target.exists():
            stem, suffix = target.stem, target.suffix
            target = ARTICLE_DIR / f"{stem}_{int(time.time())}{suffix}"
        shutil.move(str(pdf_path), str(target))

    text = extract_text(target)
    meta = infer_metadata(target, text)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    # v2: dedupe by DOI/normalised title so re-dropping a paper UPDATES it instead
    # of creating a near-duplicate row.
    import integrate_paper
    dup = integrate_paper.find_duplicate(conn, meta.get("doi"), meta.get("title"))
    if dup:
        meta["paper_id"] = dup
        conn.execute("UPDATE papers SET last_updated=? WHERE paper_id=?", (TODAY, dup))
    else:
        meta["paper_id"] = unique_paper_id(conn, meta["paper_id"], target)
        insert_paper(conn, meta, text)
    conn.execute("INSERT OR REPLACE INTO run_state (key, value) VALUES ('last_auto_ingest', ?)", (TODAY,))
    conn.commit()
    conn.close()
    update_pdf_map(meta["paper_id"], target)
    # v2: run the FULL incremental knowledge pipeline (extract -> validate -> reuse
    # entities -> harmonize -> link -> rebuild candidate matrix), not just a mock
    # numeric dump. Deterministic (mock) so the inbox watcher needs no Bedrock;
    # switch to real extraction with `integrate_paper.py --pdf ... --real`.
    import integrate_paper
    result = integrate_paper.integrate_paper(meta["paper_id"], text=text, si_text=None,
                                             mock=True, real=False)
    return meta["paper_id"], result["numeric_rows"]


def git_commit_push(message: str) -> None:
    run(["git", "add", "db/leaf_lit.db", "db/pdf_sources.json", "inbox/pdfs/README.md", "agent/auto_ingest.py", "run_ingest_once.bat", "run_ingest_watch.bat"])
    status = run(["git", "status", "--porcelain"]).stdout.strip()
    if not status:
        print("No Git changes to publish.")
        return
    run(["git", "commit", "-m", message])
    run(["git", "push"])


def ingest_pending(*, publish: bool) -> int:
    INBOX.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(p for p in INBOX.glob("*.pdf") if p.is_file())
    if not pdfs:
        print(f"No PDFs waiting in {INBOX}")
        return 0
    ingested = []
    for pdf in pdfs:
        try:
            pid, rows = ingest_one(pdf)
            ingested.append(pid)
            print(f"Ingested {pdf.name} -> {pid} ({rows} numeric rows, flagged for review)")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] {pdf.name}: {exc}", file=sys.stderr)
    if publish and ingested:
        git_commit_push("Auto-ingest new literature PDFs")
    return len(ingested)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true", help="keep checking inbox/pdfs")
    parser.add_argument("--interval", type=int, default=300, help="watch interval in seconds")
    parser.add_argument("--no-push", action="store_true", help="update local DB only")
    args = parser.parse_args()

    while True:
        ingest_pending(publish=not args.no_push)
        if not args.watch:
            return 0
        time.sleep(max(30, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
