"""Export the Leaf Literature Agent corpus to citation-manager formats.

Reads the `papers` table of leaf_lit.db and writes:
  - <out>/coeficient_library.ris  (RIS 1.0 -- imports into Mendeley and EndNote)
  - <out>/coeficient_library.bib  (BibTeX -- for Pandoc / citation-key workflows)

Design choices:
  - The BibTeX/RIS citekey IS the DB paper_id, so every in-text citation
    remains traceable back to the agent's evidence records.
  - Aggregate "cluster" pseudo-records and patent clusters are still exported
    but tagged in a note field so they can be reviewed/merged inside Mendeley.
  - Re-run any time the corpus grows; it is deterministic and overwrites.

Usage:
  python build_citation_library.py [--db PATH] [--out DIR]
"""
from __future__ import annotations
import argparse
import html
import re
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DB = HERE.parent / "db" / "leaf_lit.db"
DEFAULT_OUT = (
    HERE.parent.parent
    / "Leaf_Protein_Extraction"
    / "Research_Proposals"
    / "COEFICIENT"
    / "references"
)


def valid_doi(raw: str | None) -> str:
    """Return a bare DOI only if the field actually holds one. Some records
    (notably aggregate clusters) carry prose in the doi column; emitting that
    as DOI would break a Mendeley/EndNote import, so those are dropped."""
    raw = (raw or "").strip()
    m = re.match(r"^(10\.\d{4,9}/\S+)$", raw)
    return m.group(1) if m else ""


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)          # strip stray HTML tags
    return re.sub(r"\s+", " ", text).strip()


def split_authors(raw: str) -> list[str]:
    """Return a list of author strings. Records use ';' between authors when
    available; some use ', ' (initial style). Prefer ';' to avoid splitting
    'Last, First' pairs."""
    raw = clean(raw)
    if not raw:
        return []
    if ";" in raw:
        parts = [a.strip() for a in raw.split(";")]
    else:
        # comma-separated initial style, e.g. "Fang Q, Ke L, Bian L"
        parts = [a.strip() for a in raw.split(",")]
    return [p for p in parts if p]


def entry_kind(paper_id: str, venue: str, doi: str | None = "") -> str:
    pid = paper_id.lower()
    if "patent" in pid:
        return "patent"
    # A "cluster" id that has since been resolved to a single primary paper
    # (it now carries a real DOI) is treated as a normal article.
    if "cluster" in pid and not valid_doi(doi):
        return "cluster"
    if "rxiv" in (venue or "").lower() or pid.endswith("_v1"):
        return "preprint"
    return "article"


RIS_TY = {
    "patent": "PAT",
    "cluster": "GEN",
    "preprint": "JOUR",
    "article": "JOUR",
}
BIB_TYPE = {
    "patent": "patent",
    "cluster": "misc",
    "preprint": "article",
    "article": "article",
}


def to_ris(rows) -> str:
    out = []
    for r in rows:
        kind = entry_kind(r["paper_id"], r["venue"], r["doi"])
        out.append(f"TY  - {RIS_TY[kind]}")
        out.append(f"ID  - {r['paper_id']}")
        for au in split_authors(r["authors"]):
            out.append(f"AU  - {au}")
        if r["year"]:
            out.append(f"PY  - {r['year']}")
        title = clean(r["title"])
        if title:
            out.append(f"TI  - {title}")
        venue = clean(r["venue"])
        if venue:
            out.append(f"JO  - {venue}")
        doi = valid_doi(r["doi"])
        if doi:
            out.append(f"DO  - {doi}")
            out.append(f"UR  - https://doi.org/{doi}")
        note = []
        if kind == "cluster":
            note.append("AGGREGATE cluster record - review/split in Mendeley")
        if r["relevance"]:
            note.append(f"relevance={r['relevance']}")
        if r["verification_level"]:
            note.append(f"verification={r['verification_level']}")
        if note:
            out.append(f"N1  - {'; '.join(note)}")
        out.append("ER  - ")
        out.append("")
    return "\n".join(out)


def bib_escape(text: str) -> str:
    return text.replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")


def to_bib(rows) -> str:
    out = []
    for r in rows:
        kind = entry_kind(r["paper_id"], r["venue"], r["doi"])
        fields = []
        authors = split_authors(r["authors"])
        if authors:
            fields.append(("author", " and ".join(authors)))
        title = clean(r["title"])
        if title:
            fields.append(("title", bib_escape(title)))
        if r["year"]:
            fields.append(("year", str(r["year"])))
        venue = clean(r["venue"])
        if venue:
            fields.append(("journal", bib_escape(venue)))
        doi = valid_doi(r["doi"])
        if doi:
            fields.append(("doi", doi))
        notes = []
        if kind == "cluster":
            notes.append("aggregate cluster record - review/split before citing")
        if r["relevance"]:
            notes.append(f"relevance={r['relevance']}")
        if notes:
            fields.append(("note", bib_escape("; ".join(notes))))
        body = ",\n  ".join(f"{k} = {{{v}}}" for k, v in fields)
        out.append(f"@{BIB_TYPE[kind]}{{{r['paper_id']},\n  {body}\n}}")
        out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT paper_id, doi, title, authors, year, venue, relevance, "
        "verification_level FROM papers ORDER BY paper_id"
    ).fetchall()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coeficient_library.ris").write_text(to_ris(rows), encoding="utf-8")
    (out_dir / "coeficient_library.bib").write_text(to_bib(rows), encoding="utf-8")

    n_doi = sum(1 for r in rows if valid_doi(r["doi"]))
    n_cluster = sum(1 for r in rows if entry_kind(r["paper_id"], r["venue"], r["doi"]) == "cluster")
    print(f"Exported {len(rows)} records -> {out_dir}")
    print(f"  with DOI: {n_doi}/{len(rows)}   aggregate-cluster records flagged: {n_cluster}")
    print("  files: coeficient_library.ris, coeficient_library.bib")


if __name__ == "__main__":
    main()
