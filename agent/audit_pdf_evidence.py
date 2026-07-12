#!/usr/bin/env python3
"""Inventory figure/table evidence candidates across all mapped corpus PDFs.

This is a triage pass, not graph digitisation. It records caption locations and
scores pages likely to contain project-relevant numeric evidence. Any values
later read from plotted marks must retain figure/page provenance and human QA.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF_MAP = ROOT / "db" / "pdf_sources.json"
OUTPUT = ROOT / "db" / "evidence_candidate_audit.csv"
CACHE_DIR = ROOT / "db" / "pdf_text_cache"

TARGET_TERMS = {
    "protein": r"protein|rubisco|purity|recovery|yield",
    "colour": r"colou?r|chlorophyll|pigment|whiteness|\bL\*|\ba\*|\bb\*",
    "flavour": r"flavou?r|odou?r|aroma|sensory|volatile|\bVOC\b|hexanal|lipoxygenase|\bLOX\b",
    "model": r"machine learning|neural|PLS|PCA|classification|prediction|confusion|accuracy|R\s*[\u00b2^2]",
    "process": r"temperature|\bpH\b|time|concentration|treatment|extraction|filtration|ultrasound|enzyme",
}
CAPTION_RE = re.compile(r"^\s*(Figure|Fig\.?|Table)\s+(S?\d+[A-Za-z]?)\b[\s.:\-]*(.*)", re.I)


def pdf_text(path: Path) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    cache = CACHE_DIR / f"audit_{key}.txt"
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return cache.read_text(encoding="utf-8", errors="ignore")
    proc = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        text=True,
        capture_output=True,
        check=False,
    )
    text = proc.stdout if proc.returncode == 0 else ""
    if text:
        cache.write_text(text, encoding="utf-8")
    return text


def captions_on_page(page_text: str) -> list[tuple[str, str, str]]:
    lines = page_text.splitlines()
    found = []
    for i, line in enumerate(lines):
        match = CAPTION_RE.match(line)
        if not match:
            continue
        kind = "table" if match.group(1).lower().startswith("table") else "figure"
        tail = match.group(3).strip()
        # Captions often wrap; two following non-empty lines are enough for
        # keyword triage while avoiding accidental capture of whole tables.
        continuation = []
        for nxt in lines[i + 1:i + 4]:
            nxt = nxt.strip()
            if nxt and not CAPTION_RE.match(nxt):
                continuation.append(nxt)
            if len(continuation) == 2:
                break
        caption = re.sub(r"\s+", " ", " ".join([tail, *continuation])).strip()
        found.append((kind, match.group(2), caption))
    return found


def score_candidate(kind: str, caption: str, page_text: str) -> tuple[int, str]:
    # Topic assignment comes from the caption, avoiding the common false
    # positive where an unrelated caption shares a page with relevant prose.
    hits = [name for name, pattern in TARGET_TERMS.items() if re.search(pattern, caption, re.I)]
    score = 3 if kind == "table" else 1
    score += 2 * len(hits)
    if re.search(r"\b(mean|SD|SEM|CI|p\s*[<=>]|n\s*=|%)\b|\u00b1", f"{caption} {page_text}", re.I):
        score += 2
    if kind == "figure" and re.search(r"axis|plot|curve|correlation|loading|score", caption, re.I):
        score += 1
    return score, ";".join(hits)


def main() -> int:
    if not shutil.which("pdftotext"):
        raise SystemExit("pdftotext is required")
    mapping = json.loads(PDF_MAP.read_text(encoding="utf-8"))
    jobs = []
    missing = 0
    for paper_id, relpath in mapping.items():
        if paper_id.startswith("_"):
            continue
        path = (ROOT / relpath).resolve()
        if not path.exists():
            missing += 1
            continue
        jobs.append((paper_id, relpath, path))

    def inspect(job):
        paper_id, relpath, path = job
        local_rows = []
        text = pdf_text(path)
        for page_no, page_text in enumerate(text.split("\f"), start=1):
            for kind, label, caption in captions_on_page(page_text):
                score, topics = score_candidate(kind, caption, page_text)
                local_rows.append({
                    "paper_id": paper_id.removesuffix("__si"),
                    "source": "SI" if paper_id.endswith("__si") else "main",
                    "pdf_path": relpath,
                    "page": page_no,
                    "kind": kind,
                    "label": label,
                    "priority_score": score,
                    "topics": topics,
                    "caption": caption,
                    "status": "candidate_not_extracted",
                })
        return local_rows

    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for local_rows in pool.map(inspect, jobs):
            rows.extend(local_rows)
    rows.sort(key=lambda r: (-r["priority_score"], r["paper_id"], r["page"], r["kind"]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["paper_id"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Audited {len(jobs)} mapped files; {missing} missing; {len(rows)} caption candidates")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
