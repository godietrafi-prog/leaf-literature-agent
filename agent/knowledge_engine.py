#!/usr/bin/env python3
"""Extract evidence claims, build knowledge queries and experiment candidates."""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "leaf_lit.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
ONTOLOGY_PATH = ROOT / "db" / "ontology_v1.json"
PDF_MAP_PATH = ROOT / "db" / "pdf_sources.json"
PILOT_PATH = ROOT / "db" / "knowledge_pilot.json"
TODAY = date.today().isoformat()
MAX_TEXT_CHARS = 90000
MATRIX_VERSION = "candidate-matrix-v1"
ROLE_VERSION = "paper-role-v1"

REVIEW_PAPERS = {
    "furia2025", "offflavor_mechanism_cluster", "enose_ml_offflavor_cluster",
    "search_2025_1541_4337_70264", "search_2026_1750_3841_71031",
    "search_2026_sfp2_70048", "search_2026_sfp2_70053", "tenorio2016",
}
METHOD_TRANSFER_PAPERS = {
    "digital_twin_food_processing_cluster", "deuscher2019_chocolate_ptrms",
    "corvino2025_plant_milk_ptrms", "mandal2026_ml_functional_performance",
}

PILOT = [
    {"paper_id": "radish_fh2025", "role": "direct leaf-protein enzymatic extraction analogue"},
    {"paper_id": "search_2025_s11947_025_04156_2", "role": "LOX/VOC response to extraction treatments"},
    {"paper_id": "duckweed_fbt2025", "role": "combined process and optimization"},
    {"paper_id": "cloverbiorefinery2025", "role": "chlorophyll/colour removal and biorefinery trade-offs"},
    {"paper_id": "moringa_gels2025", "role": "DOE ranges and purity/yield trade-off"},
]

CLAIM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "claims": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "material": {"type": "object", "properties": {
                    "species": {"type": ["string", "null"]}, "cultivar": {"type": ["string", "null"]},
                    "plant_part": {"type": ["string", "null"]}, "material_form": {"type": ["string", "null"]},
                    "processing_state": {"type": ["string", "null"]}, "material_raw": {"type": ["string", "null"]}}},
                "treatment_family": {"type": "string"}, "treatment_description": {"type": "string"},
                "atmosphere": {"type": ["string", "null"]},
                "steps": {"type": "array", "items": {"type": "object", "properties": {
                    "step_order": {"type": "integer"}, "operation": {"type": "string"},
                    "temperature_c": {"type": ["number", "null"]}, "time_min": {"type": ["number", "null"]},
                    "ph": {"type": ["number", "null"]}, "pressure": {"type": ["string", "null"]},
                    "power": {"type": ["string", "null"]}, "frequency": {"type": ["string", "null"]},
                    "concentration": {"type": ["string", "null"]}, "atmosphere": {"type": ["string", "null"]},
                    "solvent": {"type": ["string", "null"]}, "solid_liquid_ratio": {"type": ["string", "null"]},
                    "source_text": {"type": "string"}}, "required": ["step_order", "operation", "source_text"]}},
                "outcome_id": {"type": "string"}, "comparator_type": {"type": "string"},
                "comparator_raw": {"type": ["string", "null"]}, "direction": {"type": "string"},
                "effect_type": {"type": "string"}, "effect_value": {"type": ["number", "null"]},
                "effect_unit": {"type": ["string", "null"]}, "uncertainty": {"type": ["string", "null"]},
                "p_value": {"type": ["number", "null"]}, "qualitative_result": {"type": ["string", "null"]},
                "source_location": {"type": "string"}, "source_quote": {"type": "string"},
                "confidence": {"type": "string"}
            },
            "required": ["material", "treatment_family", "treatment_description", "steps", "outcome_id",
                         "comparator_type", "direction", "effect_type", "effect_value", "source_location",
                         "source_quote", "confidence"]
        }}
    }, "required": ["claims"]
}


def ontology() -> dict:
    return json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    for table, name, ddl in (("knowledge_treatments", "treatment_signature", "TEXT"),
                             ("experiment_candidates", "treatment_signature", "TEXT"),
                             ("evidence_claims", "quote_match", "INTEGER")):
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    return conn


def init_ontology(conn: sqlite3.Connection, ont: dict) -> None:
    pending = list(ont["outcomes"])
    while pending:
        progressed = False
        for item in pending[:]:
            if item["parent"] is None or conn.execute(
                "SELECT 1 FROM knowledge_outcomes WHERE outcome_id=?", (item["parent"],)
            ).fetchone():
                conn.execute(
                    """INSERT INTO knowledge_outcomes VALUES (?,?,?,?)
                       ON CONFLICT(outcome_id) DO UPDATE SET
                         parent_outcome_id=excluded.parent_outcome_id,
                         label=excluded.label, ontology_version=excluded.ontology_version""",
                    (item["id"], item["parent"], item["label"], ont["version"]))
                pending.remove(item)
                progressed = True
        if not progressed:
            raise ValueError("ontology contains unresolved parent cycle")
    conn.commit()


def init_paper_roles(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT paper_id,source_type,system FROM papers").fetchall()
    for paper_id, source_type, system in rows:
        source_scope = "patent" if (source_type or "").lower() == "patent" else "scientific"
        if source_scope == "patent":
            role = "primary_experiment"
        elif paper_id in REVIEW_PAPERS:
            role = "review_synthesis"
        elif paper_id in METHOD_TRANSFER_PAPERS:
            role = "method_transfer"
        else:
            role = "primary_experiment"
        blob = f"{paper_id} {system or ''}".lower()
        domain = ("core_leaf_process" if any(x in blob for x in (
            "leaf", "leaves", "duckweed", "clover", "moringa", "radish", "nettle",
            "cassava", "spinach", "sugar beet", "sugarbeet", "cauliflower", "chaya", "alfalfa"))
                  else "transfer")
        conn.execute(
            """INSERT INTO knowledge_paper_roles VALUES (?,?,?,?,?,?)
               ON CONFLICT(paper_id) DO UPDATE SET source_scope=excluded.source_scope,
               study_role=excluded.study_role,evidence_domain=excluded.evidence_domain,
               role_basis=excluded.role_basis,mapping_version=excluded.mapping_version""",
            (paper_id, source_scope, role, domain, "manual v1 overrides + material-domain rules", ROLE_VERSION))
    conn.commit()


def write_pilot() -> None:
    payload = {"selection_version": "pilot-v1", "selection_logic":
               "Maximum coverage of direct carrot, oxidation/sensory, combined processing, colour removal and DOE trade-offs",
               "papers": PILOT,
               "priority_missing_source": [{"paper_id": "carrot_greenleaves_pmc",
                 "reason": "most direct carrot evidence, but no source PDF is mapped; must join the full-corpus run when acquired"}]}
    PILOT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {PILOT_PATH}")


def pdf_map() -> dict:
    raw = json.loads(PDF_MAP_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_") and not k.endswith("__si")}


def pdf_text(relpath: str) -> str:
    path = (ROOT / relpath).resolve()
    proc = subprocess.run(["pdftotext", "-layout", str(path), "-"], text=True,
                          capture_output=True, check=False)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or f"pdftotext failed for {path}")
    return proc.stdout[:MAX_TEXT_CHARS]


def system_prompt(ont: dict) -> str:
    return f"""You extract auditable experimental evidence claims from food/plant-protein papers.
Return JSON only. Never infer a numeric effect not explicitly stated. Every claim requires a verbatim
source_quote and a source_location. A direction requires an explicit comparator; otherwise use
not_determined and comparator none_reported. Preserve treatment step order. Null any unreported
parameter. Do not collapse sensory scores and chemical markers into one outcome.
Record the material species as its Latin binomial when stated (e.g. "Pisum sativum", not "pea"),
with cultivar in the cultivar field. When a paper reports the same treatment across several doses,
times or temperatures, emit a claim per condition rather than one summary claim, so dose/order
dependence is preserved rather than hidden as a contradiction.

Allowed treatment_family values: {list(ont['treatment_families'])}
Allowed outcome_id values: {[x['id'] for x in ont['outcomes']]}
Allowed comparator_type values: {ont['comparators']}
Allowed direction values: {ont['directions']}
Allowed effect_type values: {ont['effect_types']}

Extract claims relevant to extraction performance, purity, colour/chlorophyll, VOC/off-flavour,
LOX/oxidation, functional protein quality, safety and antinutrients. Ignore background numbers and
literature-review citations that are not results of this paper. Confidence must be High, Medium or Low."""


def validate_claim(claim: dict, ont: dict) -> list[str]:
    errors = []
    if claim.get("treatment_family") not in ont["treatment_families"]:
        errors.append("invalid treatment_family")
    if claim.get("outcome_id") not in {x["id"] for x in ont["outcomes"]}:
        errors.append("invalid outcome_id")
    if claim.get("comparator_type") not in ont["comparators"]:
        errors.append("invalid comparator_type")
    if claim.get("direction") not in ont["directions"]:
        errors.append("invalid direction")
    if claim.get("effect_type") not in ont["effect_types"]:
        errors.append("invalid effect_type")
    if claim.get("direction") in ("increase", "decrease", "no_effect") and claim.get("comparator_type") == "none_reported":
        errors.append("direction requires comparator")
    if len(claim.get("source_quote", "").split()) < 4:
        errors.append("source_quote too short")
    orders = [s.get("step_order") for s in claim.get("steps", [])]
    if orders and orders != sorted(set(orders)):
        errors.append("step order invalid")
    return errors


def store_claims(conn: sqlite3.Connection, paper_id: str, output: dict, model: str, ont: dict) -> tuple[int, int]:
    conn.execute("DELETE FROM evidence_claims WHERE paper_id=? AND validation_status!='human_verified'", (paper_id,))
    good = rejected = 0
    cache_key = output.get("cache_key")
    for claim in output.get("claims", []):
        errors = validate_claim(claim, ont)
        if errors:
            rejected += 1
            continue
        material = claim.get("material") or {}
        cur = conn.execute(
            """INSERT INTO knowledge_materials
               (species,cultivar,plant_part,material_form,processing_state,material_raw)
               VALUES (?,?,?,?,?,?)""",
            tuple(material.get(k) for k in ("species", "cultivar", "plant_part", "material_form", "processing_state", "material_raw")))
        material_id = cur.lastrowid
        cur = conn.execute(
            """INSERT INTO knowledge_treatments
               (treatment_family,description_raw,atmosphere,treatment_signature,ontology_version)
               VALUES (?,?,?,?,?)""",
            (claim["treatment_family"], claim["treatment_description"], claim.get("atmosphere"),
             None, ont["version"]))
        treatment_id = cur.lastrowid
        for step in claim.get("steps", []):
            conn.execute(
                """INSERT INTO knowledge_treatment_steps
                   (treatment_id,step_order,operation,temperature_c,time_min,ph,pressure,power,
                    frequency,concentration,atmosphere,solvent,solid_liquid_ratio,source_text)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (treatment_id, step["step_order"], step["operation"], step.get("temperature_c"),
                 step.get("time_min"), step.get("ph"), step.get("pressure"), step.get("power"),
                 step.get("frequency"), step.get("concentration"), step.get("atmosphere"),
                 step.get("solvent"), step.get("solid_liquid_ratio"), step["source_text"]))
        operations = [re.sub(r"[^a-z0-9]+", "_", s["operation"].lower()).strip("_")
                      for s in sorted(claim.get("steps", []), key=lambda x: x["step_order"])]
        signature_ops = ">".join(dict.fromkeys(operations)) or re.sub(
            r"[^a-z0-9]+", "_", claim["treatment_description"].lower()).strip("_")[:80]
        signature = f"{claim['treatment_family']}[{signature_ops}]"
        conn.execute("UPDATE knowledge_treatments SET treatment_signature=? WHERE treatment_id=?",
                     (signature, treatment_id))
        conn.execute(
            """INSERT INTO evidence_claims
               (paper_id,material_id,treatment_id,outcome_id,comparator_type,comparator_raw,
                direction,effect_type,effect_value,effect_unit,uncertainty,p_value,qualitative_result,
                source_location,source_quote,quote_match,extraction_model,extraction_cache_key,validation_status,
                confidence,ontology_version,created_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (paper_id, material_id, treatment_id, claim["outcome_id"], claim["comparator_type"],
             claim.get("comparator_raw"), claim["direction"], claim["effect_type"],
             claim.get("effect_value"), claim.get("effect_unit"), claim.get("uncertainty"),
             claim.get("p_value"), claim.get("qualitative_result"), claim["source_location"],
             claim["source_quote"], None, model, cache_key, "assumed_validated_pending_audit",
             claim.get("confidence"), ont["version"], TODAY))
        good += 1
    conn.commit()
    return good, rejected


def extract_papers(paper_ids: list[str], mock: bool = False) -> None:
    ont = ontology()
    conn = connect()
    init_ontology(conn, ont)
    init_paper_roles(conn)
    mapping = pdf_map()
    if mock:
        model = "mock-no-claims"
        client = None
    else:
        from bedrock_client import BedrockClient
        client = BedrockClient()
        model = client.model
    for index, paper_id in enumerate(paper_ids, start=1):
        if paper_id not in mapping:
            print(f"[{index}/{len(paper_ids)}] EXCLUDED {paper_id}: no physically mapped full-text PDF")
            continue
        print(f"[{index}/{len(paper_ids)}] {paper_id}", flush=True)
        text = pdf_text(mapping[paper_id])
        if mock:
            output = {"claims": []}
        else:
            output = client.complete_json(system_prompt(ont), "PAPER TEXT:\n" + text, CLAIM_SCHEMA)
        good, rejected = store_claims(conn, paper_id, output, model, ont)
        print(f"  stored {good} claims; rejected {rejected}; cached={output.get('cached', False)}")
    conn.close()


def build_matrix() -> None:
    conn = connect()
    init_paper_roles(conn)
    # Fully derived table: recreate so schema migrations (e.g. signature-level
    # uniqueness) cannot leave an obsolete constraint from an earlier build.
    conn.execute("DROP TABLE IF EXISTS experiment_candidates")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    def fetch_groups(signature_expr: str):
        return conn.execute(
        f"""SELECT r.source_scope,r.evidence_domain,t.treatment_family, {signature_expr}, c.outcome_id,
                  COUNT(DISTINCT c.paper_id), COUNT(DISTINCT COALESCE(m.species,m.material_raw)),
                  SUM(c.direction='increase'), SUM(c.direction='no_effect'),
                  SUM(c.direction='decrease'), SUM(c.direction='mixed'),
                  GROUP_CONCAT(DISTINCT c.paper_id)
           FROM evidence_claims c
           JOIN knowledge_treatments t USING(treatment_id)
           JOIN knowledge_paper_roles r USING(paper_id)
           LEFT JOIN knowledge_materials m USING(material_id)
           WHERE c.validation_status IN ('human_verified','assumed_validated_pending_audit')
             AND c.quote_match=1
             AND r.study_role='primary_experiment'
           GROUP BY r.source_scope,r.evidence_domain,t.treatment_family,{signature_expr},c.outcome_id""").fetchall()

    signature_groups = fetch_groups("COALESCE(t.treatment_signature,t.treatment_family)")
    family_groups = fetch_groups("t.treatment_family")

    def insert_group(group, aggregation_level):
        source_scope, evidence_domain, family, signature, outcome, papers, species, inc, neutral, dec, mixed, refs = group
        positive_direction = "decrease" if outcome in (
            "off_odor", "off_flavor", "green_aroma", "beany_aroma", "chlorophyll_content",
            "hexanal", "total_c6_aldehydes", "lox_activity", "lipid_oxidation", "protein_damage") else "increase"
        positive = dec if positive_direction == "decrease" else inc
        negative = inc if positive_direction == "decrease" else dec
        directional = (inc or 0) + (dec or 0)
        contradiction = min(inc or 0, dec or 0) / directional if directional else 0
        score = 2 * math.log1p(papers) + math.log1p(species) + math.log1p(positive or 0) - contradiction
        confidence = "High" if papers >= 4 and contradiction < .25 else "Medium" if papers >= 2 else "Low"
        where_expr = ("t.treatment_family" if aggregation_level == "family"
                      else "COALESCE(t.treatment_signature,t.treatment_family)")
        step_rows = conn.execute(
            """SELECT s.operation,s.temperature_c,s.time_min,s.ph
               FROM knowledge_treatment_steps s JOIN knowledge_treatments t USING(treatment_id)
               JOIN evidence_claims c USING(treatment_id)
               JOIN knowledge_paper_roles r USING(paper_id)
               WHERE """ + where_expr + "=? AND c.outcome_id=? AND r.source_scope=? AND r.evidence_domain=?",
            (signature, outcome, source_scope, evidence_domain)).fetchall()
        params = []
        for operation, temp, time, ph in step_rows:
            parts = [operation]
            if temp is not None: parts.append(f"{temp:g}C")
            if time is not None: parts.append(f"{time:g}min")
            if ph is not None: parts.append(f"pH{ph:g}")
            params.append("/".join(parts))
        contradictions = "opposing increase/decrease claims" if contradiction else None
        doe_role = "factor" if score >= 3 else "screening_candidate"
        conn.execute(
            """INSERT INTO experiment_candidates
               (treatment_family,treatment_signature,aggregation_level,source_scope,evidence_domain,outcome_id,paper_count,species_count,positive_claims,neutral_claims,
                negative_claims,mixed_claims,contradiction_rate,evidence_score,confidence,
                parameter_ranges,representative_papers,contradictions,doe_role,matrix_version,created_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (family,signature,aggregation_level,source_scope,evidence_domain,outcome,papers,species,positive,neutral,negative,mixed,contradiction,round(score,3),
             confidence,"; ".join(sorted(set(params))[:20]),refs,contradictions,doe_role,MATRIX_VERSION,TODAY))
    for group in signature_groups:
        insert_group(group, "signature")
    for group in family_groups:
        insert_group(group, "family")
    conn.commit()
    print(f"Built {len(signature_groups)} signature + {len(family_groups)} family candidates")
    conn.close()


def audit_quotes() -> None:
    conn = connect()
    mapping = pdf_map()
    totals = [0, 0]
    for paper_id, relpath in mapping.items():
        claims = conn.execute("SELECT claim_id,source_quote FROM evidence_claims WHERE paper_id=?",
                              (paper_id,)).fetchall()
        if not claims:
            continue
        text = re.sub(r"[^a-z0-9]+", " ", pdf_text(relpath).lower())
        for claim_id, quote in claims:
            normalized = re.sub(r"[^a-z0-9]+", " ", (quote or "").lower()).strip()
            tokens = normalized.split()
            # Layout extraction may wrap/hyphenate a long sentence. Require at
            # least one contiguous 8-token quote window in the source.
            windows = [" ".join(tokens[i:i + 8]) for i in range(max(1, len(tokens) - 7))]
            matched = bool(tokens and any(window in text for window in windows if len(window) > 20))
            conn.execute("UPDATE evidence_claims SET quote_match=? WHERE claim_id=?",
                         (int(matched), claim_id))
            totals[0] += 1; totals[1] += int(matched)
    conn.commit(); conn.close()
    print(f"Quote audit: {totals[1]}/{totals[0]} claims matched source PDF text")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("select-pilot")
    extract = sub.add_parser("extract")
    extract.add_argument("--pilot", action="store_true")
    extract.add_argument("--all", action="store_true")
    extract.add_argument("--paper-id", action="append")
    extract.add_argument("--skip-paper", action="append", default=[])
    extract.add_argument("--mock", action="store_true")
    sub.add_parser("build-matrix")
    sub.add_parser("audit-quotes")
    args = parser.parse_args()
    if args.command == "init":
        conn = connect(); init_ontology(conn, ontology()); init_paper_roles(conn); conn.close(); print("Knowledge schema initialized")
    elif args.command == "select-pilot":
        write_pilot()
    elif args.command == "extract":
        if sum(bool(x) for x in (args.pilot, args.all, args.paper_id)) != 1:
            raise SystemExit("choose exactly one of --pilot, --all, or --paper-id")
        ids = ([x["paper_id"] for x in PILOT] if args.pilot else sorted(pdf_map()) if args.all else args.paper_id)
        ids = [paper_id for paper_id in ids if paper_id not in set(args.skip_paper)]
        extract_papers(ids, mock=args.mock)
    elif args.command == "build-matrix":
        build_matrix()
    else:
        audit_quotes()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
