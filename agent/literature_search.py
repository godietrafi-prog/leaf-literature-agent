#!/usr/bin/env python3
"""Scheduled multi-source literature search for the Leaf Literature Agent.

Queries several open scholarly APIs, normalises every hit into one record shape,
de-duplicates by DOI (across sources, the run, and the existing DB), then inserts
conservatively:
  * OA PDF found  -> download, extract text, add numeric rows as unverified.
  * no PDF found  -> add abstract-level paper + access_queue row.

Sources (all keyless / public):
  * openalex        — DOI-centric, good OA-URL coverage.
  * crossref        — broad metadata + publisher PDF links.
  * europepmc       — biomedical/PubMed + Open-Access full-text URLs.
  * semanticscholar — extra coverage + openAccessPdf field (rate-limited w/o key).
  * unpaywall       — NOT a search source; resolves an OA PDF for a DOI that the
                      search sources returned without one.

Only `stdlib` is used (urllib) so the deployed app needs no extra dependency.
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
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB_PATH = ROOT / "db" / "leaf_lit.db"
ARTICLE_DIR = ROOT.parent / "Leaf_Protein_Extraction" / "literature" / "pdfs_provided_by_user"
TODAY = date.today().isoformat()
DEFAULT_FROM_DATE = (date.today() - timedelta(days=30)).isoformat()
# A contact email puts us in the "polite pools" of Crossref/Unpaywall. Set your
# real address via LEAF_CONTACT_EMAIL; the placeholder still works.
CONTACT_EMAIL = os.environ.get("LEAF_CONTACT_EMAIL", "leaf-literature-agent@example.com")
USER_AGENT = f"LeafLiteratureAgent/0.2 (mailto:{CONTACT_EMAIL})"

ALL_SOURCES = ("openalex", "crossref", "europepmc", "semanticscholar")

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


# ── generic helpers ───────────────────────────────────────────────────────────
def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=check)


def request_json(url: str, timeout: int = 30, retries: int = 3, headers: dict | None = None) -> dict:
    """GET JSON, retrying on HTTP 429 with backoff — the proven pattern from the
    poster project's Semantic Scholar client (S2's keyless pool 429s often; the
    fix is to wait and retry, not to drop the source)."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers=hdrs), timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(12 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


# Optional free Semantic Scholar API key (https://www.semanticscholar.org/product/api)
# lifts the keyless-pool 429s on the search endpoint. Set env LEAF_S2_API_KEY.
S2_API_KEY = os.environ.get("LEAF_S2_API_KEY", "").strip()


def doi_clean(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = str(raw).strip()
    raw = re.sub(r"^https?://(dx\.)?doi\.org/", "", raw, flags=re.I)
    return raw.rstrip(".,);]").lower() or None


def clean_id(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return re.sub(r"_+", "_", text)[:70] or "paper"


def strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def year_of(rec: dict) -> int | None:
    return rec.get("year")


# ── normalised record ─────────────────────────────────────────────────────────
# Every source adapter returns dicts with these keys:
#   doi, title, abstract, year, authors, venue, pdf_url, api
def _record(doi, title, abstract, year, authors, venue, pdf_url, api) -> dict:
    return {
        "doi": doi_clean(doi), "title": (title or "Untitled").strip(),
        "abstract": strip_tags(abstract)[:4000], "year": year,
        "authors": authors or None, "venue": venue or None,
        "pdf_url": pdf_url or None, "api": api,
    }


# ── source: OpenAlex ──────────────────────────────────────────────────────────
def _openalex_abstract(index: dict | None) -> str:
    if not index:
        return ""
    words = [(pos, w) for w, poss in index.items() for pos in poss]
    return " ".join(w for _, w in sorted(words))


def _openalex_pdf(work: dict) -> str | None:
    locs = ([work["primary_location"]] if work.get("primary_location") else []) + (work.get("locations") or [])
    for loc in locs:
        url = loc.get("pdf_url")
        if url and url.startswith("http"):
            return url
        lp = str(loc.get("landing_page_url") or "")
        if lp.lower().endswith(".pdf"):
            return lp
    oa = (work.get("open_access") or {}).get("oa_url")
    return oa if oa and str(oa).lower().endswith(".pdf") else None


def openalex_search(query: str, from_date: str, n: int) -> list[dict]:
    url = "https://api.openalex.org/works?" + urlencode({
        "search": query, "filter": f"from_publication_date:{from_date}",
        "per-page": str(n), "sort": "publication_date:desc", "mailto": CONTACT_EMAIL})
    out = []
    for w in request_json(url).get("results", []):
        names = [a["author"]["display_name"] for a in (w.get("authorships") or [])
                 if (a.get("author") or {}).get("display_name")]
        auth = "; ".join(names[:12]) + ("; et al." if len(names) > 12 else "") if names else None
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
        out.append(_record(w.get("doi"), w.get("title"),
                           _openalex_abstract(w.get("abstract_inverted_index")),
                           w.get("publication_year"), auth, venue, _openalex_pdf(w), "openalex"))
    return out


# ── source: Crossref ──────────────────────────────────────────────────────────
def crossref_search(query: str, from_date: str, n: int) -> list[dict]:
    url = "https://api.crossref.org/works?" + urlencode({
        "query": query, "rows": str(n), "sort": "published", "order": "desc",
        "filter": f"from-pub-date:{from_date}", "mailto": CONTACT_EMAIL})
    out = []
    for it in request_json(url).get("message", {}).get("items", []):
        dp = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
        year = dp[0] if dp else None
        names = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in (it.get("author") or [])]
        auth = "; ".join(n2 for n2 in names[:12] if n2) or None
        pdf = None
        for lnk in it.get("link") or []:
            if lnk.get("content-type") == "application/pdf" or str(lnk.get("URL", "")).lower().endswith(".pdf"):
                pdf = lnk.get("URL")
                break
        out.append(_record(it.get("DOI"), " ".join(it.get("title") or []),
                           it.get("abstract", ""), year, auth,
                           " ".join(it.get("container-title") or []), pdf, "crossref"))
    return out


# ── source: Europe PMC ────────────────────────────────────────────────────────
def europepmc_search(query: str, from_date: str, n: int) -> list[dict]:
    q = f'({query}) AND (FIRST_PDATE:[{from_date} TO 3000-01-01])'
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urlencode({
        "query": q, "format": "json", "pageSize": str(n), "resultType": "core",
        "sort": "P_PDATE_D desc"})
    out = []
    for r in request_json(url).get("resultList", {}).get("result", []):
        pdf = None
        for u in ((r.get("fullTextUrlList") or {}).get("fullTextUrl") or []):
            if str(u.get("documentStyle", "")).lower() == "pdf" and str(u.get("availability", "")).lower() in ("open access", "free"):
                pdf = u.get("url")
                break
        year = int(r["pubYear"]) if str(r.get("pubYear", "")).isdigit() else None
        out.append(_record(r.get("doi"), r.get("title"), r.get("abstractText", ""),
                           year, r.get("authorString"), r.get("journalTitle"), pdf, "europepmc"))
    return out


# ── source: Semantic Scholar ──────────────────────────────────────────────────
# Native S2 field-of-study gate — cuts the bulk of the keyword noise (drops
# unrelated botany/pharmacology "leaf extract" hits) using the API's own filter.
_S2_FIELDS_OF_STUDY = ("Agricultural and Food Sciences,Chemistry,Biology,"
                       "Engineering,Environmental Science,Materials Science")


def semanticscholar_search(query: str, from_date: str, n: int) -> list[dict]:
    # /paper/search (relevance-ranked) with the native filters documented in S2AG:
    # fieldsOfStudy + year do the coarse filtering server-side. For a large
    # backfill use /paper/search/bulk (boolean query, up to 1000, continuation token).
    from_year = int(from_date[:4]) if from_date[:4].isdigit() else 0
    params = {
        "query": query,
        "fields": "title,abstract,year,externalIds,openAccessPdf,venue,authors",
        "limit": str(min(n, 100)),
        "fieldsOfStudy": _S2_FIELDS_OF_STUDY,
    }
    if from_year:
        params["year"] = f"{from_year}-"  # native "from this year onward" filter
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urlencode(params)
    hdrs = {"x-api-key": S2_API_KEY} if S2_API_KEY else None
    out = []
    for p in request_json(url, headers=hdrs).get("data", []):
        auth = "; ".join(a.get("name", "") for a in (p.get("authors") or [])[:12]) or None
        out.append(_record((p.get("externalIds") or {}).get("DOI"), p.get("title"),
                           p.get("abstract", ""), p.get("year"), auth, p.get("venue"),
                           (p.get("openAccessPdf") or {}).get("url"), "semanticscholar"))
    return out


SOURCE_FUNCS = {
    "openalex": openalex_search, "crossref": crossref_search,
    "europepmc": europepmc_search, "semanticscholar": semanticscholar_search,
}


# ── Unpaywall OA-PDF resolver (by DOI) ────────────────────────────────────────
def unpaywall_pdf(doi: str | None) -> str | None:
    if not doi:
        return None
    url = f"https://api.unpaywall.org/v2/{quote(doi)}?" + urlencode({"email": CONTACT_EMAIL})
    try:
        loc = request_json(url, timeout=25).get("best_oa_location") or {}
        return loc.get("url_for_pdf") or (loc.get("url") if str(loc.get("url", "")).lower().endswith(".pdf") else None)
    except Exception:  # noqa: BLE001
        return None


# ── merge + relevance ─────────────────────────────────────────────────────────
def merge_records(records: list[dict]) -> list[dict]:
    """Collapse the same paper found in >1 source: keep the richest abstract and
    any PDF url, and record which APIs saw it."""
    by_key: dict[str, dict] = {}
    for r in records:
        key = r["doi"] or "t:" + clean_id(r["title"])
        if key not in by_key:
            by_key[key] = dict(r)
            by_key[key]["apis"] = {r["api"]}
        else:
            ex = by_key[key]
            ex["apis"].add(r["api"])
            if not ex.get("pdf_url") and r.get("pdf_url"):
                ex["pdf_url"] = r["pdf_url"]
            if len(r.get("abstract") or "") > len(ex.get("abstract") or ""):
                ex["abstract"] = r["abstract"]
            ex["doi"] = ex.get("doi") or r.get("doi")
    for r in by_key.values():
        r["api"] = "+".join(sorted(r.pop("apis", {r["api"]})))
    return list(by_key.values())


def relevance(title: str, abstract: str) -> str:
    blob = f"{title} {abstract}".lower()
    n = sum(1 for term in RELEVANCE_TERMS if term in blob)
    return "High" if n >= 4 else "Medium" if n >= 2 else "Low"


def known_dois(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT doi FROM papers WHERE doi IS NOT NULL AND doi != ''").fetchall()
    return {doi_clean(r[0]) for r in rows if doi_clean(r[0])}


# ── DB insert (normalised record) ─────────────────────────────────────────────
def paper_id_for(rec: dict) -> str:
    year = rec.get("year") or ""
    if rec.get("doi"):
        return f"search_{year}_{clean_id(rec['doi'].split('/')[-1])}"[:80]
    return f"search_{year}_{clean_id(rec['title'])}"[:80]


def insert_categories(conn, pid: str, cluster: str, blob: str) -> None:
    cats = {"source:search", f"search_cluster:{cluster}"}
    b = blob.lower()
    if "machine learning" in b or "random forest" in b or re.search(r"\bsvm\b", b):
        cats.add("analysis:ML")
    if "lipoxygenase" in b or re.search(r"\blox\b", b):
        cats.add("mechanism:LOX")
    if "chlorophyll" in b or "colour" in b or "color" in b:
        cats.add("outcome:color")
    if any(w in b for w in ("flavor", "flavour", "odor", "odour", "hexanal")):
        cats.add("outcome:off_flavor")
    if "yield" in b:
        cats.add("outcome:yield")
    if "protein" in b:
        cats.add("outcome:protein_purity")
    for c in sorted(cats):
        conn.execute("INSERT OR IGNORE INTO paper_categories (paper_id, category) VALUES (?,?)", (pid, c))


def insert_search_paper(conn, rec: dict, cluster: str, access: str, pid: str) -> None:
    rel = relevance(rec["title"], rec["abstract"])
    story = f"Discovered automatically by scheduled search via {rec['api']} ({cluster}). Access: {access}."
    conn.execute(
        """INSERT INTO papers (paper_id, doi, title, authors, year, venue,
           source_type, system, extraction_method_family, relevance,
           verification_level, access_status, si_status, discovery,
           scientific_story, key_findings, added_date, last_updated)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, rec["doi"], rec["title"], rec["authors"], rec["year"], rec["venue"],
         "peer-reviewed", "unknown", "unknown", rel,
         "full_text" if access == "open" else "abstract", access, "unknown",
         f"keyword_search:{rec['api']}", story,
         rec["abstract"][:1800] or "Abstract unavailable.", TODAY, TODAY))
    insert_categories(conn, pid, cluster, f"{rec['title']} {rec['abstract']}")


def safe_filename(text: str) -> str:
    name = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9._ -]+", " ", text)).strip()
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


def process_record(conn, rec: dict, cluster: str, seen: set, *, use_unpaywall: bool,
                   dry_run: bool) -> tuple[bool, bool]:
    doi = rec.get("doi")
    key = doi or "t:" + clean_id(rec["title"])
    if key in seen:
        return False, False
    if doi and doi in known_dois(conn):
        seen.add(key)
        return False, False
    rel = relevance(rec["title"], rec["abstract"])
    if rel == "Low":
        if dry_run:
            print(f"[skip-low] {cluster} [{rec['api']}]: {rec['title'][:90]}")
        seen.add(key)
        return False, False

    pdf = rec.get("pdf_url")
    if not pdf and use_unpaywall and doi:
        pdf = unpaywall_pdf(doi)
        if pdf:
            rec["api"] += "+unpaywall"
    has_pdf = bool(pdf)
    if dry_run:
        print(f"[dry] {cluster} [{rec['api']}]: {rec['title'][:80]} | rel={rel} | "
              f"doi={doi or '-'} | pdf={'yes' if has_pdf else 'no'}")
        seen.add(key)
        return True, has_pdf

    seen.add(key)
    pid = paper_id_for(rec)
    base, k = pid, 2
    while conn.execute("SELECT 1 FROM papers WHERE paper_id=?", (pid,)).fetchone():
        pid = f"{base}_{k}"
        k += 1
    access = "open" if has_pdf else "queued"
    insert_search_paper(conn, rec, cluster, access, pid)

    if has_pdf and pdf:
        pdf_path = ARTICLE_DIR / safe_filename(f"{pid} {rec['title']}")
        if download_pdf(pdf, pdf_path):
            text = auto_ingest.extract_text(pdf_path)
            rows = auto_ingest.store_mock_results(conn, pid, text)
            auto_ingest.update_pdf_map(pid, pdf_path)
            print(f"  + {pid} [{rec['api']}]: OA PDF downloaded, {rows} numeric rows flagged")
            return True, True
        conn.execute("UPDATE papers SET verification_level='abstract', access_status='queued' WHERE paper_id=?", (pid,))
        pdf, has_pdf = None, False
    conn.execute(
        """INSERT INTO access_queue (paper_id, doi, missing, link, why_it_matters, requested_date, resolved_date)
           VALUES (?,?,?,?,?,?,NULL)""",
        (pid, doi, "main", pdf or rec.get("doi") or "", f"Search cluster {cluster} via {rec['api']}", TODAY))
    print(f"  + {pid} [{rec['api']}]: metadata queued (no OA PDF)")
    return True, False


def commit_push() -> None:
    run(["git", "add", "db/leaf_lit.db", "db/pdf_sources.json", "agent/literature_search.py",
         "run_search_once.bat", "run_search_watch.bat", "dashboard/README.md"], check=False)
    if not run(["git", "status", "--porcelain"], check=False).stdout.strip():
        print("No Git changes to publish.")
        return
    run(["git", "commit", "-m", "Auto-search literature updates"], check=False)
    run(["git", "push"], check=False)


def search_once(*, sources: list[str], from_date: str, per_page: int, use_unpaywall: bool,
                dry_run: bool, publish: bool) -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    seen: set = set()
    total_new = total_pdf = 0
    for cluster, queries in SEARCH_QUERIES.items():
        for query in queries:
            records: list[dict] = []
            for src in sources:
                try:
                    records += SOURCE_FUNCS[src](query, from_date, per_page)
                except Exception as exc:  # noqa: BLE001 — one source down must not stop the rest
                    print(f"[WARN] {src} failed on {query!r}: {exc}", file=sys.stderr)
                time.sleep(1.0)  # be polite to each API
            merged = merge_records(records)
            n_new = 0
            for rec in merged:
                is_new, got_pdf = process_record(conn, rec, cluster, seen,
                                                 use_unpaywall=use_unpaywall, dry_run=dry_run)
                n_new += int(is_new)
                total_pdf += int(got_pdf)
            total_new += n_new
            if not dry_run:
                conn.execute("INSERT INTO query_log (run_date, cluster, query, n_hits, n_new) VALUES (?,?,?,?,?)",
                             (TODAY, cluster, query, len(merged), n_new))
                conn.commit()
            print(f"{cluster}: {query!r} -> {len(merged)} unique across {len(sources)} sources, {n_new} new")
    if not dry_run:
        conn.execute("INSERT OR REPLACE INTO run_state (key, value) VALUES ('last_literature_search', ?)", (TODAY,))
        conn.commit()
    conn.close()
    print(f"\nSearch complete: {total_new} new records, {total_pdf} with OA PDF. Sources: {', '.join(sources)}.")
    if publish and not dry_run and total_new:
        commit_push()
    return total_new


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sources", default=os.environ.get("LEAF_SEARCH_SOURCES", ",".join(ALL_SOURCES)),
                   help=f"comma list from {ALL_SOURCES}")
    p.add_argument("--no-unpaywall", action="store_true", help="skip Unpaywall OA-PDF lookup")
    p.add_argument("--from-date", default=os.environ.get("LEAF_SEARCH_FROM", DEFAULT_FROM_DATE))
    p.add_argument("--per-page", type=int, default=int(os.environ.get("LEAF_SEARCH_PER_PAGE", "10")))
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval-hours", type=float, default=24.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-push", action="store_true")
    args = p.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip() in SOURCE_FUNCS]
    if not sources:
        print(f"No valid sources in {args.sources!r}; choose from {ALL_SOURCES}", file=sys.stderr)
        return 2

    while True:
        search_once(sources=sources, from_date=args.from_date, per_page=args.per_page,
                    use_unpaywall=not args.no_unpaywall, dry_run=args.dry_run, publish=not args.no_push)
        if not args.watch:
            return 0
        time.sleep(max(1.0, args.interval_hours) * 3600)


if __name__ == "__main__":
    raise SystemExit(main())
