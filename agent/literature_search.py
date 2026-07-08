#!/usr/bin/env python3
"""Scheduled literature search for the Leaf Literature Agent.

Uses OpenAlex because it is open, DOI-centric, and usually exposes an OA PDF URL
when one is known. New records are inserted conservatively:
  * OA PDF found  -> download, extract text, add numeric rows as unverified.
  * no PDF found  -> add abstract-level paper + access_queue row.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB_PATH = ROOT / "db" / "leaf_lit.db"
ARTICLE_DIR = ROOT.parent / "Leaf_Protein_Extraction" / "literature" / "pdfs_provided_by_user"
TODAY = date.today().isoformat()
DEFAULT_FROM_DATE = (date.today() - timedelta(days=30)).isoformat()
USER_AGENT = "LeafLiteratureAgent/0.1 (mailto:rafi.steckler@example.invalid)"

sys.path.insert(0, str(HERE))
import auto_ingest  # noqa: E402

SEARCH_QUERIES = {
    "lox_sensory": [
        "leaf protein extraction lipoxygenase off flavor",
        "leaf protein extraction off odor chlorophyll",
        "green leaf protein deodorization lipoxygenase",
        "RuBisCO extraction off flavor chlorophyll",
    ],
    "leaf_protein_process": [
        "leaf protein concentrate extraction chlorophyll removal",
        "green biomass protein extraction sensory quality",
        "alfalfa leaf protein concentrate off flavor",
        "duckweed protein isolate off flavor chlorophyll",
    ],
    "ai_screening": [
        "plant protein functionality machine learning structural properties",
        "plant protein off flavor machine learning sensory",
        "electronic nose plant protein off flavor machine learning",
    ],
}

RELEVANCE_TERMS = (
    "leaf", "green biomass", "rubisco", "chlorophyll", "lipoxygenase", "lox",
    "off-flavor", "off flavour", "off-odor", "off odour", "hexanal", "sensory",
    "plant protein", "protein extraction", "protein isolate", "duckweed", "alfalfa",
)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=check)


def request_json(url: str, timeout: int = 30) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def openalex_search(query: str, *, from_date: str, per_page: int) -> list[dict]:
    params = {
        "search": query,
        "filter": f"from_publication_date:{from_date}",
        "per-page": str(per_page),
        "sort": "publication_date:desc",
    }
    url = "https://api.openalex.org/works?" + urlencode(params)
    return request_json(url).get("results", [])


def abstract_from_inverted(index: dict | None) -> str:
    if not index:
        return ""
    words = []
    for word, positions in index.items():
        for pos in positions:
            words.append((pos, word))
    return " ".join(word for _, word in sorted(words))


def doi_clean(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    raw = re.sub(r"^https?://(dx\.)?doi\.org/", "", raw, flags=re.I)
    return raw.rstrip(".,);]").lower()


def clean_id(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return re.sub(r"_+", "_", text)[:70] or "paper"


def source_name(work: dict) -> str | None:
    loc = work.get("primary_location") or {}
    src = loc.get("source") or {}
    return src.get("display_name")


def authors(work: dict) -> str | None:
    names = []
    for a in work.get("authorships") or []:
        author = a.get("author") or {}
        name = author.get("display_name")
        if name:
            names.append(name)
    if not names:
        return None
    return "; ".join(names[:12]) + ("; et al." if len(names) > 12 else "")


def pdf_url(work: dict) -> str | None:
    locs = []
    if work.get("primary_location"):
        locs.append(work["primary_location"])
    locs.extend(work.get("locations") or [])
    for loc in locs:
        url = loc.get("pdf_url") or (loc.get("landing_page_url") if str(loc.get("landing_page_url", "")).lower().endswith(".pdf") else None)
        if url and url.startswith("http"):
            return url
    oa = work.get("open_access") or {}
    url = oa.get("oa_url")
    if url and str(url).lower().endswith(".pdf"):
        return url
    return None


def relevance(title: str, abstract: str) -> str:
    blob = f"{title} {abstract}".lower()
    n = sum(1 for term in RELEVANCE_TERMS if term in blob)
    if n >= 4:
        return "High"
    if n >= 2:
        return "Medium"
    return "Low"


def known_dois(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT doi FROM papers WHERE doi IS NOT NULL AND doi != ''").fetchall()
    return {doi_clean(r[0]) for r in rows if doi_clean(r[0])}


def paper_id_for(work: dict, doi: str | None) -> str:
    year = work.get("publication_year") or ""
    title = work.get("title") or "untitled"
    if doi:
        suffix = clean_id(doi.split("/")[-1])
        return f"search_{year}_{suffix}"[:80]
    return f"search_{year}_{clean_id(title)}"[:80]


def insert_categories(conn: sqlite3.Connection, paper_id: str, cluster: str, title: str, abstract: str) -> None:
    cats = {f"source:search", f"search_cluster:{cluster}"}
    blob = f"{title} {abstract}".lower()
    if "machine learning" in blob or "random forest" in blob or "svm" in blob:
        cats.add("analysis:ML")
    if "lipoxygenase" in blob or re.search(r"\blox\b", blob):
        cats.add("mechanism:LOX")
    if "chlorophyll" in blob or "color" in blob or "colour" in blob:
        cats.add("outcome:color")
    if "flavor" in blob or "flavour" in blob or "odor" in blob or "odour" in blob or "hexanal" in blob:
        cats.add("outcome:off_flavor")
    if "yield" in blob:
        cats.add("outcome:yield")
    if "protein" in blob:
        cats.add("outcome:protein_purity")
    for cat in sorted(cats):
        conn.execute("INSERT OR IGNORE INTO paper_categories (paper_id, category) VALUES (?,?)", (paper_id, cat))


def insert_search_paper(conn: sqlite3.Connection, work: dict, cluster: str, access: str, pdf: str | None) -> str:
    doi = doi_clean(work.get("doi"))
    title = work.get("title") or "Untitled"
    abstract = abstract_from_inverted(work.get("abstract_inverted_index"))
    pid = paper_id_for(work, doi)
    base = pid
    n = 2
    while conn.execute("SELECT 1 FROM papers WHERE paper_id=?", (pid,)).fetchone():
        pid = f"{base}_{n}"
        n += 1

    rel = relevance(title, abstract)
    story = (
        f"Discovered automatically by scheduled OpenAlex search ({cluster}). "
        f"Access status: {access}."
    )
    conn.execute(
        """INSERT INTO papers (paper_id, doi, title, authors, year, venue,
           source_type, system, extraction_method_family, relevance,
           verification_level, access_status, si_status, discovery,
           scientific_story, key_findings, added_date, last_updated)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            pid, doi, title, authors(work), work.get("publication_year"), source_name(work),
            "peer-reviewed", "unknown", "unknown", rel,
            "full_text" if access == "open" else "abstract",
            access, "unknown", "keyword_search", story,
            abstract[:1800] if abstract else "Abstract unavailable from OpenAlex.",
            TODAY, TODAY,
        ),
    )
    insert_categories(conn, pid, cluster, title, abstract)
    if access != "open":
        conn.execute(
            """INSERT INTO access_queue
               (paper_id, doi, missing, link, why_it_matters, requested_date, resolved_date)
               VALUES (?,?,?,?,?,?,NULL)""",
            (pid, doi, "main", work.get("id") or work.get("doi"), f"Matched search cluster: {cluster}", TODAY),
        )
    elif pdf:
        conn.execute(
            """INSERT INTO access_queue
               (paper_id, doi, missing, link, why_it_matters, requested_date, resolved_date)
               VALUES (?,?,?,?,?,?,?)""",
            (pid, doi, "SI", pdf, "OA main PDF found automatically; supplementary material not checked.", TODAY, TODAY),
        )
    return pid


def safe_filename(text: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._ -]+", " ", text).strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:140] or "paper") + ".pdf"


def download_pdf(url: str, target: Path) -> bool:
    ARTICLE_DIR.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"})
    try:
        with urlopen(req, timeout=45) as resp:
            ctype = resp.headers.get("content-type", "").lower()
            data = resp.read(30_000_000)
        if len(data) < 1000 or (not data.startswith(b"%PDF") and "pdf" not in ctype):
            return False
        target.write_bytes(data)
        return True
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def process_work(conn: sqlite3.Connection, work: dict, cluster: str, *, dry_run: bool) -> tuple[bool, bool]:
    doi = doi_clean(work.get("doi"))
    if doi and doi in known_dois(conn):
        return False, False
    title = work.get("title") or "Untitled"
    abstract = abstract_from_inverted(work.get("abstract_inverted_index"))
    rel = relevance(title, abstract)
    if rel == "Low":
        if dry_run:
            print(f"[skip-low] {cluster}: {title[:100]} | doi={doi or '-'}")
        return False, False
    pdf = pdf_url(work)
    has_pdf = bool(pdf)
    if dry_run:
        print(f"[dry] {cluster}: {title[:100]} | relevance={rel} | doi={doi or '-'} | pdf={'yes' if has_pdf else 'no'}")
        return True, has_pdf

    access = "open" if has_pdf else "queued"
    pid = insert_search_paper(conn, work, cluster, access, pdf)
    if has_pdf and pdf:
        pdf_path = ARTICLE_DIR / safe_filename(f"{pid} {title}")
        if download_pdf(pdf, pdf_path):
            text = auto_ingest.extract_text(pdf_path)
            rows = auto_ingest.store_mock_results(conn, pid, text)
            auto_ingest.update_pdf_map(pid, pdf_path)
            print(f"  + {pid}: OA PDF downloaded, {rows} numeric rows flagged")
        else:
            conn.execute("UPDATE papers SET verification_level='abstract', access_status='queued' WHERE paper_id=?", (pid,))
            conn.execute(
                """INSERT INTO access_queue
                   (paper_id, doi, missing, link, why_it_matters, requested_date, resolved_date)
                   VALUES (?,?,?,?,?,?,NULL)""",
                (pid, doi, "main", pdf, "OA PDF URL failed to download; manual access needed.", TODAY),
            )
            has_pdf = False
            print(f"  + {pid}: metadata queued; PDF URL failed")
    else:
        print(f"  + {pid}: metadata queued; no OA PDF")
    return True, has_pdf


def commit_push() -> None:
    run(["git", "add", "db/leaf_lit.db", "db/pdf_sources.json", "agent/literature_search.py", "run_search_once.bat", "run_search_watch.bat", "dashboard/README.md"])
    if not run(["git", "status", "--porcelain"]).stdout.strip():
        print("No Git changes to publish.")
        return
    run(["git", "commit", "-m", "Auto-search literature updates"])
    run(["git", "push"])


def search_once(*, from_date: str, per_page: int, dry_run: bool, publish: bool) -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    total_new = 0
    total_pdf = 0
    for cluster, queries in SEARCH_QUERIES.items():
        for query in queries:
            try:
                works = openalex_search(query, from_date=from_date, per_page=per_page)
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] query failed: {query}: {exc}", file=sys.stderr)
                continue
            n_new = 0
            for work in works:
                is_new, got_pdf = process_work(conn, work, cluster, dry_run=dry_run)
                n_new += int(is_new)
                total_pdf += int(got_pdf)
            total_new += n_new
            if not dry_run:
                conn.execute(
                    "INSERT INTO query_log (run_date, cluster, query, n_hits, n_new) VALUES (?,?,?,?,?)",
                    (TODAY, cluster, query, len(works), n_new),
                )
                conn.commit()
            print(f"{cluster}: {query!r} -> {len(works)} hits, {n_new} new")
            time.sleep(1.0)
    if not dry_run:
        conn.execute("INSERT OR REPLACE INTO run_state (key, value) VALUES ('last_literature_search', ?)", (TODAY,))
        conn.commit()
    conn.close()
    print(f"\nSearch complete: {total_new} new records, {total_pdf} with OA PDF.")
    if publish and not dry_run and total_new:
        commit_push()
    return total_new


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", default=os.environ.get("LEAF_SEARCH_FROM", DEFAULT_FROM_DATE))
    parser.add_argument("--per-page", type=int, default=int(os.environ.get("LEAF_SEARCH_PER_PAGE", "10")))
    parser.add_argument("--watch", action="store_true", help="run repeatedly")
    parser.add_argument("--interval-hours", type=float, default=24.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()

    while True:
        search_once(from_date=args.from_date, per_page=args.per_page, dry_run=args.dry_run, publish=not args.no_push)
        if not args.watch:
            return 0
        time.sleep(max(1.0, args.interval_hours) * 3600)


if __name__ == "__main__":
    raise SystemExit(main())
