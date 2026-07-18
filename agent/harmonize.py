#!/usr/bin/env python3
"""Build auditable harmonized and analysis-ready layers from immutable raw rows."""
from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import date
from pathlib import Path

import migrations
import ontology_match

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "leaf_lit.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
VERSION = "harmonization-v1"
TODAY = date.today().isoformat()

QUANTITY_ONTOLOGY = {
    "protein_purity_pct": ("protein_purity_pct", "%", "outcome:protein_purity"),
    "yield_pct": ("yield_pct", "%", "outcome:protein_recovery"),
    "chlorophyll_removal_pct": ("chlorophyll_removal_pct", "%", "outcome:chlorophyll_removal"),
    "rubisco_specificity_pct": ("rubisco_specificity_pct", "%", "outcome:rubisco_specificity"),
    "hexanal_conc": ("hexanal_conc", None, "chemical:hexanal"),
    "LOX_activity": ("LOX_activity", None, "enzyme:lipoxygenase_activity"),
    "chlorophyll_content": ("chlorophyll_content", None, "chemical:chlorophyll_content"),
    "sensory_offodor_score": ("sensory_offodor_score", None, "sensory:off_odor"),
    "sensory_offflavor_score": ("sensory_offflavor_score", None, "sensory:off_flavor"),
    "color_L": ("color_L", None, "colour:CIE_L_star"),
    "color_a": ("color_a", None, "colour:CIE_a_star"),
    "color_b": ("color_b", None, "colour:CIE_b_star"),
    "sensory_classification_accuracy": ("sensory_classification_accuracy", "%", "model:classification_accuracy"),
}


def ensure_schema(conn: sqlite3.Connection) -> None:
    migrations.ensure(conn)  # v2 tables + columns (also runs schema.sql)
    have = {row[1] for row in conn.execute("PRAGMA table_info(numeric_results)")}
    for name, ddl in (("verified_by", "TEXT"), ("confidence", "TEXT")):
        if name not in have:
            conn.execute(f"ALTER TABLE numeric_results ADD COLUMN {name} {ddl}")


def write_canonical_columns(conn: sqlite3.Connection) -> None:
    """Populate numeric_results.quantity_canonical / outcome_id / unit_canonical
    from the deterministic ontology matcher. These columns are what let the
    dashboard and any downstream analysis group the 1,000+ raw quantity strings
    by the controlled outcome vocabulary."""
    rows = conn.execute("SELECT result_id, quantity, unit FROM numeric_results").fetchall()
    for result_id, quantity, unit in rows:
        m = ontology_match.match_quantity(quantity)
        conn.execute(
            "UPDATE numeric_results SET quantity_canonical=?, outcome_id=?, unit_canonical=? WHERE result_id=?",
            (m["quantity_canonical"], m["outcome_id"], ontology_match.canonical_unit(unit), result_id))


def clean_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    unit = re.sub(r"\s+", "", unit).replace("µ", "u").lower()
    aliases = {"percent": "%", "pct": "%", "ppbv": "ppbv", "ppb": "ppb",
               "mg/g": "mg/g", "g/kg": "g/kg", "ug/kg": "ug/kg", "mg/kg": "mg/kg"}
    return aliases.get(unit, unit)


def harmonize_value(quantity: str, value: float | None, unit: str | None, basis: str | None):
    mapping = QUANTITY_ONTOLOGY.get(quantity)
    if not mapping:
        # v2: fall back to the deterministic ontology matcher instead of a crude
        # "*:unmapped" bucket. This connects the long tail of LLM-invented quantity
        # names to the 28-node outcome tree, so cross-study grouping by outcome_id
        # works even where no cross-unit conversion is claimed.
        m = ontology_match.match_quantity(quantity)
        q_std = m["quantity_canonical"] or re.sub(r"[^a-z0-9]+", "_", quantity.lower()).strip("_")
        c_unit = ontology_match.canonical_unit(unit) or clean_unit(unit)
        if m["outcome_id"]:
            ontology = f"outcome:{m['outcome_id']}"
            notes = f"ontology outcome mapped ({m['match_type']}); no cross-unit conversion claimed"
        else:
            ontology = ("sensory:unmapped" if re.search(r"sensory|odor|odour|flavou?r|aroma", quantity, re.I)
                        else "chemical:unmapped" if re.search(r"volatile|aldehyde|hexanal|content|concentration", quantity, re.I)
                        else "process:unmapped" if re.search(r"yield|recovery|extraction|treatment", quantity, re.I)
                        else "measurement:unmapped")
            notes = "ontology mapping pending"
        status = "identity_only" if value is not None else "not_harmonizable"
        return q_std, value, c_unit, ontology, status, "value_std = value; unit retained", notes
    quantity_std, canonical, ontology = mapping
    source_unit = clean_unit(unit)
    if value is None:
        return quantity_std, None, canonical or source_unit, ontology, "not_harmonizable", None, "missing value"
    if canonical == "%":
        if source_unit == "%":
            return quantity_std, value, "%", ontology, "exact", "value_std = value", None
        return quantity_std, value, source_unit, ontology, "identity_only", "value_std = value; unit retained", f"cannot infer percent denominator from {unit!r}"
    # Concentrations may only be converted inside a compatible mass basis.
    if source_unit in ("mg/g", "g/kg"):
        return quantity_std, value, "mg/g", ontology, (
            "exact" if source_unit == "mg/g" else "converted"), "1 g/kg = 1 mg/g", basis
    if source_unit == "mg/kg":
        return quantity_std, value * 1000, "ug/kg", ontology, "converted", "value_std = value * 1000", basis
    if source_unit in ("ug/kg", "ppbv", "ppb") or source_unit is None:
        return quantity_std, value, source_unit, ontology, "exact", "value_std = value", basis
    return quantity_std, value, source_unit, ontology, "identity_only", "value_std = value; unit retained", f"unsupported unit {unit!r}"


def first_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.I)
    return float(match.group(1)) if match else None


def treatment_features(text: str):
    text = text or ""
    ph = first_float(r"\bpH\s*[:=]?\s*(\d+(?:\.\d+)?)", text)
    temp = first_float(r"(-?\d+(?:\.\d+)?)\s*°?\s*C\b", text)
    time = first_float(r"(\d+(?:\.\d+)?)\s*(?:min|minutes?)\b", text)
    oxygen = 1 if re.search(r"\b(?:N2|nitrogen|anaerobic|oxygen[- ]control|inert)\b", text, re.I) else None
    sonication = 1 if re.search(r"ultrasound|sonicat", text, re.I) else None
    heat = 1 if re.search(r"heat|thermal|\d+\s*°?\s*C", text, re.I) else None
    found = any(value is not None for value in (ph, temp, time, oxygen, sonication, heat))
    return ph, temp, time, oxygen, sonication, heat, "parsed_needs_review" if found else "not_reported"


def build(db_path: Path = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    conn.execute("DELETE FROM numeric_results_harmonized")
    conn.execute("DELETE FROM treatment_features")
    rows = conn.execute(
        """SELECT result_id, quantity, value, unit, basis, treatment_condition,
                  verified, verified_value
           FROM numeric_results"""
    ).fetchall()
    counts = {"exact": 0, "converted": 0, "identity_only": 0, "not_harmonizable": 0, "needs_mapping": 0}
    for result_id, quantity, raw_value, unit, basis, treatment, verified, verified_value in rows:
        effective = verified_value if verified and verified_value is not None else raw_value
        q_std, value_std, unit_std, ontology, status, formula, notes = harmonize_value(
            quantity, effective, unit, basis)
        counts[status] += 1
        conn.execute(
            """INSERT INTO numeric_results_harmonized
               (result_id, quantity_std, value_std, unit_std, ontology_term,
                harmonization_status, conversion_formula, mapping_version,
                harmonization_notes, created_date)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (result_id, q_std, value_std, unit_std, ontology, status, formula, VERSION, notes, TODAY),
        )
        ph, temp, time, oxygen, sonication, heat, feature_status = treatment_features(treatment)
        conn.execute(
            """INSERT INTO treatment_features
               (result_id, ph, temperature_c, time_min, oxygen_control, sonication,
                heat_treatment, feature_status, mapping_version, mapping_notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (result_id, ph, temp, time, oxygen, sonication, heat, feature_status, VERSION,
             "Rule-based extraction from treatment_condition; review before ML"),
        )
    write_canonical_columns(conn)
    conn.execute("INSERT OR REPLACE INTO run_state(key,value) VALUES('last_harmonization',?)", (TODAY,))
    conn.commit()
    conn.close()
    print(f"Harmonized {len(rows)} rows with {VERSION}: {counts}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    build(args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
