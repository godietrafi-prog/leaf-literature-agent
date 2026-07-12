#!/usr/bin/env python3
"""
ingest_seed.py — Phase-1 bootstrap for the Leaf Literature Agent.

Reads the 31 hand-curated records in seed_data/metadata/*.md (YAML front-matter
+ narrative body) and loads them into db/leaf_lit.db, creating the schema first.

Design rules honoured (see docs/DB_SCHEMA.md):
  * outcomes.* values are NOT clean numbers. We parse a leading numeric token,
    keep the ENTIRE original string in numeric_results.source_location, and set
    needs_human = 1 whenever the value was parsed out of narrative.
  * null / "not measured" / "not addressed" -> no numeric_results row at all.
  * never invent a number the record does not state.

Idempotent: re-running rebuilds each seed paper's rows cleanly (delete+insert
per paper inside one transaction), so it is safe to run repeatedly.

Usage:  python3 agent/ingest_seed.py
"""
from __future__ import annotations

import glob
import os
import re
import sqlite3
import sys
from datetime import date

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.path.join(ROOT, "db", "leaf_lit.db")
SCHEMA_PATH = os.path.join(ROOT, "db", "schema.sql")
SEED_GLOB = os.path.join(ROOT, "seed_data", "metadata", "*.md")
TODAY = date.today().isoformat()

# Old synthetic records that represented several publications in one `papers`
# row. They are removed before ingest so a corrected split cannot leave a stale
# pseudo-paper in the database after its seed file is deleted.
RETIRED_SEED_IDS = ("ptrms_ml_sensory_cluster", "moringa_optim_unknown")

# outcome field -> (quantity name, unit) for the numeric_results table
NUMERIC_OUTCOMES = {
    "protein_purity_pct": ("protein_purity_pct", "%"),
    "yield_pct": ("yield_pct", "%"),
    "chlorophyll_removal_pct": ("chlorophyll_removal_pct", "%"),
    "target_protein_specificity": ("rubisco_specificity_pct", "%"),
}

SPECIES_KEYS = [
    "carrot", "moringa", "duckweed", "alfalfa", "sugar beet", "sugarbeet",
    "spinach", "cassava", "nettle", "clover", "cauliflower", "radish",
    "chaya", "tobacco",
]

# phrases that mean "no number here" -> skip the row entirely
NON_VALUE_RE = re.compile(
    r"^\s*(null|none|n/?a|not\s+(measured|addressed|quantified|reported|applicable|tested|"
    r"determined|available))\b",
    re.IGNORECASE,
)
LEADING_NUM_RE = re.compile(r"^\s*[~<>]?\s*(-?\d+(?:\.\d+)?)")


def split_frontmatter(text: str):
    """Return (yaml_dict, body_str) from an md file with --- front-matter ---."""
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("no YAML front-matter delimiters found")
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return meta, body


def parse_numeric(raw):
    """
    Map a raw outcomes value to (value, needs_human, source_string) or None.

    None                       -> caller writes no row.
    clean int/float            -> (float, 0, str(raw))
    number buried in narrative -> (float, 1, raw)         # parsed, flag for human
    narrative w/o any number   -> None                    # nothing to record
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw), 0, str(raw)
    s = str(raw).strip()
    if not s or NON_VALUE_RE.match(s):
        return None
    m = LEADING_NUM_RE.match(s)
    if not m:
        return None  # narrative with no leading number -> not recordable as numeric
    value = float(m.group(1))
    # clean scalar iff the whole string is just the number (optionally with %)
    is_clean = re.fullmatch(r"\s*[~<>]?\s*-?\d+(?:\.\d+)?\s*%?\s*", s) is not None
    return value, 0 if is_clean else 1, s


def species_of(system: str) -> str:
    """Pick the species mentioned FIRST in the string, not first in our list.

    Guards against e.g. chaya ("tree spinach") being mislabelled spinach: the
    real subject is whichever species name appears earliest in `system`.
    """
    s = (system or "").lower()
    best_pos, best_key = None, None
    for k in SPECIES_KEYS:
        pos = s.find(k)
        if pos != -1 and (best_pos is None or pos < best_pos):
            best_pos, best_key = pos, k
    if best_key is None:
        return "other"
    return best_key.replace(" ", "_").replace("sugarbeet", "sugar_beet")


def categories_for(meta: dict, body: str) -> list[str]:
    cats = set()
    system = (meta.get("system") or "")
    cats.add(f"species:{species_of(system)}")

    emf = (meta.get("extraction_method_family") or "").lower()
    method_map = [
        (("heat", "coagulat"), "extraction_method:heat_coagulation"),
        (("isoelectric", "iep", "ph-shift", "ph shift"), "extraction_method:pH_shift_IEP"),
        (("membrane", "ultrafiltr", " uf", "diafiltr"), "extraction_method:membrane_UF"),
        (("ultrasound", "sonicat"), "extraction_method:ultrasound"),
        (("pef", "pulsed electric"), "extraction_method:PEF"),
        (("enzym",), "extraction_method:enzymatic"),
        (("chromatograph",), "extraction_method:chromatography"),
    ]
    for needles, tag in method_map:
        if any(n in emf for n in needles):
            cats.add(tag)

    blob = (emf + " " + body).lower()
    if "lipoxygenase" in blob or re.search(r"\blox\b", blob):
        cats.add("mechanism:LOX")
    if "chlorophyll" in blob:
        cats.add("mechanism:chlorophyll_binding")
    if "phenol" in blob or "polyphenol" in blob:
        cats.add("mechanism:phenolic_oxidation")

    # analysis / AI-ML detection — run on the fields that describe what the paper
    # DOES (title, key_parameters, method, relevance note) to avoid false hits
    # from body prose that merely mentions ML in passing.
    ai_text = " ".join(
        str(meta.get(k, "") or "")
        for k in ("title", "key_parameters", "extraction_method_family", "one_line_relevance_note")
    ).lower()
    analysis_patterns = [
        (r"deep learning|neural network|neural[- ]ode|\banode\b|\bann\b|convolutional|\bcnn\b|\blstm\b|autoencoder|transformer",
         "analysis:deep_learning"),
        (r"machine learning|random forest|xgboost|gradient boost|pls-?da|\bplsr\b|\blda\b|\bsvm\b|chemometric|artificial intelligence|classifier",
         "analysis:ML"),
        (r"digital[- ]twin", "analysis:digital_twin"),
        (r"response surface|\brsm\b|design of experiments|\bdoe\b|central composite|box-behnken|plackett",
         "analysis:DOE_RSM"),
        (r"proteomic", "analysis:proteomics"),
    ]
    for pat, tag in analysis_patterns:
        if re.search(pat, ai_text):
            cats.add(tag)

    outcomes = meta.get("outcomes") or {}
    if str(outcomes.get("off_flavor_result", "")).strip() not in ("", "None"):
        ofr = str(outcomes.get("off_flavor_result", "")).lower()
        if ofr and not NON_VALUE_RE.match(ofr):
            cats.add("outcome:off_flavor")
    if parse_numeric(outcomes.get("protein_purity_pct")):
        cats.add("outcome:protein_purity")
    if parse_numeric(outcomes.get("yield_pct")):
        cats.add("outcome:yield")
    if parse_numeric(outcomes.get("chlorophyll_removal_pct")):
        cats.add("outcome:color")
    return sorted(cats)


def verification_and_access(source_type: str):
    s = (source_type or "").lower()
    negated = "not full text" in s or "not full-text" in s
    if any(x in s for x in ("abstract", "summary level", "citation-level", "citation level")) or negated:
        # check abstract/negation FIRST: "not full text obtained" must not match "full text"
        vlevel = "abstract"
    elif any(x in s for x in ("supplementary", "+si", " si ", "si)")):
        vlevel = "full_text+SI"
    elif any(x in s for x in ("full text", "full-text", "pdf")):
        vlevel = "full_text"
    else:
        vlevel = "full_text" if s else None

    if any(x in s for x in ("user-provided", "user provided", "owner")):
        access = "owner_supplied"
    elif "open access" in s or "open-access" in s:
        access = "open"
    elif "paywall" in s:
        access = "queued"
    else:
        access = None
    return vlevel, access


def source_kind(source_type: str) -> str:
    s = (source_type or "").lower()
    if "patent" in s:
        return "patent"
    if "preprint" in s or "biorxiv" in s or "chemrxiv" in s:
        return "preprint"
    if "thesis" in s:
        return "thesis"
    if "peer-review" in s or "peer review" in s:
        return "peer-reviewed"
    return None


def ingest():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        conn.executescript(fh.read())
    # migration: add provenance to a pre-existing numeric_results table (CREATE IF
    # NOT EXISTS won't alter an existing one)
    if "provenance" not in [r[1] for r in conn.execute("PRAGMA table_info(numeric_results)")]:
        conn.execute("ALTER TABLE numeric_results ADD COLUMN provenance TEXT DEFAULT 'seed'")

    for retired_id in RETIRED_SEED_IDS:
        conn.execute("DELETE FROM papers WHERE paper_id = ?", (retired_id,))

    files = sorted(glob.glob(SEED_GLOB))
    if not files:
        sys.exit(f"no seed files found at {SEED_GLOB}")

    n_papers = n_numeric = n_flagged = n_cats = 0
    errors = []

    for path in files:
        try:
            meta, body = split_frontmatter(open(path, encoding="utf-8").read())
        except Exception as e:  # noqa: BLE001
            errors.append((os.path.basename(path), str(e)))
            continue

        pid = meta.get("citekey") or os.path.splitext(os.path.basename(path))[0]
        # year fields are often narrative strings ("2025 (review); ...") -> keep the first 4-digit year
        ym = re.search(r"(19|20)\d{2}", str(meta.get("year", "")))
        year = int(ym.group(0)) if ym else None
        vlevel, access = verification_and_access(meta.get("source_type", ""))
        doi = meta.get("doi")
        # only keep a doi that looks like a real DOI (10.xxxx/...) as the unique key
        clean_doi = doi if (doi and re.match(r"^10\.\d", str(doi).strip())) else None

        cur = conn.cursor()
        # rebuild this paper cleanly (idempotent)
        cur.execute("DELETE FROM papers WHERE paper_id = ?", (pid,))

        cur.execute(
            """INSERT INTO papers (paper_id, doi, title, authors, year, venue,
                source_type, system, extraction_method_family, relevance,
                verification_level, access_status, si_status, discovery,
                scientific_story, key_findings, added_date, last_updated)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pid, clean_doi, meta.get("title"), meta.get("authors"),
                year, meta.get("venue"), source_kind(meta.get("source_type", "")),
                meta.get("system"), meta.get("extraction_method_family"),
                meta.get("relevance"), vlevel, access, meta.get("si_status", "none"), "seed",
                meta.get("one_line_relevance_note"), body, TODAY, TODAY,
            ),
        )
        n_papers += 1

        for cat in categories_for(meta, body):
            cur.execute(
                "INSERT OR IGNORE INTO paper_categories (paper_id, category) VALUES (?,?)",
                (pid, cat),
            )
            n_cats += 1

        outcomes = meta.get("outcomes") or {}
        species = species_of(meta.get("system", ""))
        for field, (quantity, unit) in NUMERIC_OUTCOMES.items():
            parsed = parse_numeric(outcomes.get(field))
            if not parsed:
                continue
            value, needs_human, src = parsed
            cur.execute(
                """INSERT INTO numeric_results
                   (paper_id, quantity, value, unit, method, species,
                    source_location, is_from_SI, needs_human, provenance, extracted_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, quantity, value, unit, None, species, src, 0, needs_human, "seed", TODAY),
            )
            n_numeric += 1
            n_flagged += needs_human

        # Optional hand-verified rows for quantities outside the four legacy
        # outcome fields. This keeps table/figure extractions traceable without
        # forcing them into narrative strings.
        for row in meta.get("numeric_results", []) or []:
            if row.get("value") is None or not row.get("quantity"):
                continue
            needs_human = int(row.get("needs_human", 0))
            cur.execute(
                """INSERT INTO numeric_results
                   (paper_id, quantity, value, unit, sd_error, error_type,
                    n_replicates, p_value, method, species, treatment_condition,
                    basis, source_location, is_from_SI, needs_human, provenance,
                    extracted_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid, row["quantity"], row["value"], row.get("unit"),
                    row.get("sd_error"), row.get("error_type"), row.get("n_replicates"),
                    row.get("p_value"), row.get("method"), row.get("species", species),
                    row.get("treatment_condition"), row.get("basis"),
                    row.get("source_location"), int(row.get("is_from_SI", 0)),
                    needs_human, "seed_verified", TODAY,
                ),
            )
            n_numeric += 1
            n_flagged += needs_human

    conn.execute(
        "INSERT OR REPLACE INTO run_state (key, value) VALUES ('last_seed_ingest', ?)",
        (TODAY,),
    )
    conn.commit()
    conn.close()

    # Derived harmonization is rebuilt from raw rows after every seed refresh.
    import harmonize
    harmonize.build()

    print(f"Ingested {n_papers} papers into {DB_PATH}")
    print(f"  numeric_results rows: {n_numeric}  (needs_human flagged: {n_flagged})")
    print(f"  category tags:        {n_cats}")
    if errors:
        print(f"  PARSE ERRORS ({len(errors)}):")
        for name, err in errors:
            print(f"    {name}: {err}")
    else:
        print("  parse errors: 0")


if __name__ == "__main__":
    ingest()
