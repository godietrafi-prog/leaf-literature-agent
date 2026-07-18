#!/usr/bin/env python3
"""Canonical entity normalization for the Leaf Literature Agent.

Problem this solves (from both technical reviews): the same real-world entity is
stored as many different strings. In the current DB the `species` column holds
"Pisum sativum", "Pisum sativum L.", "Glycine max", "Glycine max (NOR)" and
"soybean" as *separate* values, so cross-study grouping is wrong and the corpus
looks more fragmented than it is.

This module builds two tables (see db/schema.sql):
  * canonical_entities  — one node per real entity (species / method / quantity),
  * entity_mentions     — every raw string resolved to a node, keeping the raw
                          string for provenance (raw layer stays immutable).

Resolution is deterministic (normalise → alias table → fuzzy fallback via
difflib) and never invents an external id it cannot justify. It is incremental:
`resolve_new(conn, ids)` resolves only the rows a freshly added paper created,
reusing existing entities wherever the normalised name already exists.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import migrations
import ontology_match

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "leaf_lit.db"
VERSION = "entities-v1"
TODAY = date.today().isoformat()

# Common-name -> canonical binomial, so "soybean" and "Glycine max" unify. Only
# well-established mappings for species seen in the leaf-protein corpus.
_SPECIES_ALIASES = {
    "soybean": "Glycine max", "soy": "Glycine max", "soya": "Glycine max",
    "pea": "Pisum sativum", "yellow pea": "Pisum sativum", "field pea": "Pisum sativum",
    "cowpea": "Vigna unguiculata", "chickpea": "Cicer arietinum",
    "moringa": "Moringa oleifera", "duckweed": "Lemna minor",
    "carrot": "Daucus carota", "black carrot": "Daucus carota",
    "cauliflower": "Brassica oleracea var. botrytis", "broccoli": "Brassica oleracea var. italica",
    "alfalfa": "Medicago sativa", "lucerne": "Medicago sativa",
    "spinach": "Spinacia oleracea", "sugar beet": "Beta vulgaris", "sugarbeet": "Beta vulgaris",
    "beetroot": "Beta vulgaris", "cassava": "Manihot esculenta",
    "nettle": "Urtica dioica", "stinging nettle": "Urtica dioica",
    "clover grass": "Trifolium repens", "clover": "Trifolium repens",
    "radish": "Raphanus sativus", "mulberry": "Morus alba", "tobacco": "Nicotiana tabacum",
    "avocado": "Persea americana", "lupin": "Lupinus albus", "lupine": "Lupinus albus",
    "chaya": "Cnidoscolus aconitifolius", "camelina": "Camelina sativa",
}

# Strip trailing botanical authority / cultivar noise so "Pisum sativum L." and
# "Pisum sativum" collapse. Order matters: remove parentheticals, then authority.
_AUTHORITY_RE = re.compile(
    r"\s*(\(.*?\)|\bL\.?$|\bL\.\s|var\.\s+\w+|subsp\.\s+\w+|cv\.?\s.*|"
    r"\bssp\.?\s+\w+|\bspp?\.?$|\bsp\.?$)", re.I)


def _norm_name(raw: str) -> str:
    s = re.sub(r"\s+", " ", (raw or "").strip())
    s = s.strip(" .,;")
    return s


def canonical_species(raw: str) -> tuple[str, str]:
    """Return (canonical_name, resolver) for a species string."""
    s = _norm_name(raw)
    if not s:
        return "", "unmapped"
    low = s.lower()
    if low in _SPECIES_ALIASES:
        return _SPECIES_ALIASES[low], "alias"
    # progressively strip botanical authority/cultivar noise
    prev = None
    stripped = s
    while stripped != prev:
        prev = stripped
        stripped = _AUTHORITY_RE.sub("", stripped).strip(" .,;")
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped.lower() in _SPECIES_ALIASES:
        return _SPECIES_ALIASES[stripped.lower()], "alias"
    # keep a two-token binomial if that is what remains
    if stripped:
        return stripped, ("exact" if stripped == s else "normalized")
    return s, "exact"


def _get_or_create(conn, entity_type, canonical_name, *, ontology_ref=None,
                   external_ref=None, alias=None):
    row = conn.execute(
        "SELECT entity_id, aliases FROM canonical_entities WHERE entity_type=? AND canonical_name=?",
        (entity_type, canonical_name)).fetchone()
    if row:
        entity_id, aliases_json = row
        created = False
    else:
        conn.execute(
            """INSERT INTO canonical_entities
               (entity_type, canonical_name, external_ref, ontology_ref, aliases,
                mention_count, mapping_version, created_date, last_updated)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (entity_type, canonical_name, external_ref, ontology_ref, json.dumps([]),
             0, VERSION, TODAY, TODAY))
        entity_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        aliases_json = "[]"
        created = True
    if alias:
        aliases = set(json.loads(aliases_json or "[]"))
        if alias not in aliases and alias != canonical_name:
            aliases.add(alias)
            conn.execute("UPDATE canonical_entities SET aliases=?, last_updated=? WHERE entity_id=?",
                         (json.dumps(sorted(aliases)), TODAY, entity_id))
    return entity_id, created


def _record_mention(conn, entity_id, source_table, source_id, field, raw, resolver, score):
    conn.execute(
        """INSERT INTO entity_mentions
           (entity_id, source_table, source_id, field, raw_string, resolver,
            match_score, mapping_version, created_date)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source_table, source_id, field) DO UPDATE SET
             entity_id=excluded.entity_id, raw_string=excluded.raw_string,
             resolver=excluded.resolver, match_score=excluded.match_score,
             mapping_version=excluded.mapping_version""",
        (entity_id, source_table, str(source_id), field, raw, resolver, score, VERSION, TODAY))


def _resolve_species_rows(conn, rows, created_counter, reused_counter):
    """rows = [(result_id, species_raw)] from numeric_results."""
    # cache existing canonical species names for the fuzzy fallback
    known = [r[0] for r in conn.execute(
        "SELECT canonical_name FROM canonical_entities WHERE entity_type='species'")]
    for result_id, raw in rows:
        if not raw or not raw.strip():
            continue
        canonical, resolver = canonical_species(raw)
        if not canonical:
            continue
        score = 1.0 if resolver in ("alias", "exact") else 0.9
        # fuzzy tie to an existing canonical name to avoid near-duplicate nodes
        if resolver == "normalized" and canonical not in known:
            close = difflib.get_close_matches(canonical, known, n=1, cutoff=0.92)
            if close:
                canonical, resolver, score = close[0], "fuzzy", 0.85
        entity_id, created = _get_or_create(
            conn, "species", canonical, alias=_norm_name(raw))
        created_counter[0] += int(created)
        reused_counter[0] += int(not created)
        if canonical not in known:
            known.append(canonical)
        _record_mention(conn, entity_id, "numeric_results", result_id, "species", raw, resolver, score)
        conn.execute("UPDATE numeric_results SET species_entity_id=? WHERE result_id=?",
                     (entity_id, result_id))


def _resolve_quantity_rows(conn, rows):
    """Attach every numeric row to a canonical quantity entity + ontology outcome.
    rows = [(result_id, quantity_raw)]."""
    for result_id, raw in rows:
        m = ontology_match.match_quantity(raw)
        qname = m["quantity_canonical"] or (raw or "").strip()
        if not qname:
            continue
        entity_id, _ = _get_or_create(conn, "quantity", qname,
                                      ontology_ref=m["outcome_id"], alias=raw)
        _record_mention(conn, entity_id, "numeric_results", result_id, "quantity", raw,
                        m["match_type"], 1.0 if m["outcome_id"] else 0.5)


def _refresh_mention_counts(conn):
    conn.execute(
        """UPDATE canonical_entities SET mention_count = (
               SELECT COUNT(*) FROM entity_mentions m WHERE m.entity_id = canonical_entities.entity_id)""")


def resolve_new(conn: sqlite3.Connection, result_ids: list[int]) -> dict:
    """Incrementally resolve species + quantity for a specific set of numeric rows
    (the rows a new paper created). Reuses existing entities automatically."""
    migrations.ensure(conn)
    if not result_ids:
        return {"created": 0, "reused": 0}
    qmarks = ",".join("?" * len(result_ids))
    srows = conn.execute(
        f"SELECT result_id, species FROM numeric_results WHERE result_id IN ({qmarks})",
        result_ids).fetchall()
    qrows = conn.execute(
        f"SELECT result_id, quantity FROM numeric_results WHERE result_id IN ({qmarks})",
        result_ids).fetchall()
    created, reused = [0], [0]
    _resolve_species_rows(conn, srows, created, reused)
    _resolve_quantity_rows(conn, qrows)
    _refresh_mention_counts(conn)
    conn.commit()
    return {"created": created[0], "reused": reused[0]}


def rebuild_all(conn: sqlite3.Connection) -> dict:
    """Full deterministic rebuild of entities from every numeric_results row.
    Idempotent: clears mentions/entities and re-resolves."""
    migrations.ensure(conn)
    conn.execute("DELETE FROM entity_mentions")
    conn.execute("DELETE FROM canonical_entities")
    conn.execute("UPDATE numeric_results SET species_entity_id=NULL")
    ids = [r[0] for r in conn.execute("SELECT result_id FROM numeric_results")]
    stats = resolve_new(conn, ids)
    n_species = conn.execute("SELECT COUNT(*) FROM canonical_entities WHERE entity_type='species'").fetchone()[0]
    n_quantity = conn.execute("SELECT COUNT(*) FROM canonical_entities WHERE entity_type='quantity'").fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO run_state(key,value) VALUES('last_entity_rebuild',?)", (TODAY,))
    conn.commit()
    return {"species_entities": n_species, "quantity_entities": n_quantity, **stats}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebuild", action="store_true",
                    help="(default) full deterministic rebuild of entities from all rows")
    ap.parse_args()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    stats = rebuild_all(conn)  # rebuild is the only whole-corpus mode; incremental use is via resolve_new()
    conn.close()
    print(f"Entities: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
