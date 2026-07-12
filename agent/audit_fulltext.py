#!/usr/bin/env python3
"""Audit physical full-text/SI availability and build the owner's fetch list."""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "leaf_lit.db"
MAP_PATH = ROOT / "db" / "pdf_sources.json"
MD_PATH = ROOT / "inbox" / "MISSING_FULL_TEXT.md"
CSV_PATH = ROOT / "inbox" / "MISSING_FULL_TEXT.csv"
TODAY = date.today().isoformat()
REQUIRES_SPLIT = {
    "wounding_electrochemical_realtime": "Synthetic cluster: identify and split the spinach and Arabidopsis source papers",
    "alfalfa_uf_general": "Conflated classic studies: disambiguate into individual bibliographic records",
    "rubisco_tobacco_patents": "Seven-patent cluster: one partial component is present; split/map each patent separately",
    "digital_twin_food_processing_cluster": "Synthetic cluster: Kannapinn and DigiFoodTwin PDFs are present; split into individual paper records",
    "enose_ml_offflavor_cluster": "Synthetic cluster: Shtepliuk review PDF is present; split it from the catfish experiment and other cited sources",
    "offflavor_mechanism_cluster": "Synthetic cluster: Vatansever review PDF is present; split it from the pea-fermentation studies",
}


def main() -> int:
    mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    physical = {key: (ROOT / rel).resolve().exists() for key, rel in mapping.items() if not key.startswith("_")}
    conn = sqlite3.connect(DB_PATH)
    papers = conn.execute(
        """SELECT paper_id,title,authors,year,doi,relevance,verification_level,si_status
           FROM papers ORDER BY CASE relevance WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
                                year DESC,paper_id""").fetchall()
    missing = []
    needs_split = []
    for paper_id, title, authors, year, doi, relevance, declared, si_status in papers:
        has_main = physical.get(paper_id, False)
        has_si = physical.get(f"{paper_id}__si", False)
        missing_kind = None
        if not has_main:
            missing_kind = "main" if si_status not in ("queued", "fetched") else "both"
        elif si_status == "queued" and not has_si:
            missing_kind = "SI"
        if paper_id in REQUIRES_SPLIT:
            needs_split.append({"paper_id": paper_id, "action": REQUIRES_SPLIT[paper_id],
                                "title": title, "relevance": relevance})
            continue
        if not missing_kind:
            continue
        clean_doi = doi.strip() if doi and re.fullmatch(r"10\.\d{4,9}/\S+", doi.strip()) else None
        link = f"https://doi.org/{clean_doi}" if clean_doi else (
            "https://scholar.google.com/scholar?q=" + quote_plus(title or paper_id))
        reason = ("No physical source PDF is mapped; excluded from Knowledge Engine and DOE"
                  if not has_main else "Main PDF exists, but supplementary material is queued/missing")
        missing.append({
            "paper_id": paper_id, "relevance": relevance, "year": year, "title": title,
            "authors": authors, "doi": doi, "missing": missing_kind, "link": link,
            "declared_verification": declared, "reason": reason,
        })
        conn.execute("DELETE FROM access_queue WHERE paper_id=? AND resolved_date IS NULL", (paper_id,))
        conn.execute(
            """INSERT INTO access_queue
               (paper_id,doi,missing,link,why_it_matters,requested_date,resolved_date)
               VALUES (?,?,?,?,?,?,NULL)""",
            (paper_id, doi, missing_kind, link, reason, TODAY),
        )
    conn.commit()
    conn.close()
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(missing[0]) if missing else ["paper_id"])
        writer.writeheader(); writer.writerows(missing)
    lines = [
        "# Missing full text / supplementary material", "",
        f"Generated: {TODAY}", "",
        "Hard rule: papers without a physically mapped full-text PDF are excluded from the Knowledge Engine, Candidate Matrix and DOE.", "",
        f"Missing items: **{len(missing)}**", "",
    ]
    for row in missing:
        lines.extend([
            f"## {row['paper_id']} — {row['missing']}", "",
            f"- **Priority:** {row['relevance']}",
            f"- **Title:** {row['title']}",
            f"- **Authors/year:** {row['authors'] or 'unknown'} ({row['year'] or 'unknown'})",
            f"- **DOI:** {row['doi'] or 'not recorded'}",
            f"- **Get it:** {row['link']}",
            f"- **Why:** {row['reason']}", "",
        ])
    if needs_split:
        lines.extend(["# Requires bibliographic splitting (not a single PDF request)", ""])
        for row in needs_split:
            lines.extend([f"## {row['paper_id']}", "", f"- **Priority:** {row['relevance']}",
                          f"- **Action:** {row['action']}", f"- **Current title:** {row['title']}", ""])
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Full-text audit: {len(papers) - sum(r['missing'] in ('main','both') for r in missing)}/{len(papers)} main PDFs available")
    print(f"Fetch list: {MD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
