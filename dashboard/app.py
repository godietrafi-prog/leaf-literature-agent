#!/usr/bin/env python3
"""
Leaf Literature Agent — live Streamlit dashboard.

Reads db/leaf_lit.db directly (never a stale snapshot). Run with:

    streamlit run dashboard/app.py

Tabs: Overview · Corpus · AI / ML methods · Topic coverage.
The "AI / ML methods" tab surfaces papers whose reported method is a machine-
learning / deep-learning / digital-twin / DOE-RSM / proteomics approach — in leaf
protein OR in analogous food systems whose method transfers to leaf-protein
purification (each card states the transfer logic).

NOTE (OneDrive sync): .py files do not sync via OneDrive — zip this for transport
(see /pack). The DB it reads (db/leaf_lit.db) does sync natively.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date
from urllib.parse import quote_plus

import altair as alt
import pandas as pd
import streamlit as st

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "db", "leaf_lit.db")
# Temporary project decision: include every extracted row in downstream
# harmonized/analysis exports while the formal human audit is pending. This
# labels the assumption; it does not falsify numeric_results.verified.
ASSUME_ALL_VALIDATED = True

# ── palette: quiet work-focused light UI ──────────────────────────────────────
ACCENT = "#167a55"
CYAN = "#2563eb"
AMBER = "#b7791f"
INK = "#17231d"
INK2 = "#5f6f66"
SURFACE = "#ffffff"
CANVAS = "#f7faf7"
RING = "#d9e3dc"

st.set_page_config(page_title="Leaf Literature Agent", page_icon="🌿", layout="wide")

# ── copy ──────────────────────────────────────────────────────────────────────
T = {'title': 'Leaf Literature Agent',
 'tagline': 'A live, queryable knowledge base on leaf-protein extraction and the removal of '
            'off-odor, off-flavor and green color — LOX mechanism at its core.',
 'phase': 'Phase 1 · seed corpus · SQLite live',
 'refresh': '↻ Refresh from DB',
 'k_papers': 'Papers',
 'k_numeric': 'Numeric results',
 'k_flag': 'Need verification',
 'k_species': 'Species',
 'k_full': 'Full-text / +SI',
 'k_ai': 'AI / ML papers',
 'k_extracted': 'Extracted (unverified)',
 'k_extracted_help': 'Numeric values auto-extracted from PDFs by Claude (Bedrock). Every value '
                     'carries a verbatim source quote; NOT yet human-verified.',
 'tab_overview': 'Overview',
 'tab_corpus': 'Corpus',
 'tab_sensory': 'Target matrix',
 'tab_evidence': 'Evidence map',
 'tab_hypothesis': 'Hypothesis',
 'tab_ai': 'AI / ML methods',
 'tab_extracted': 'Extracted data',
 'tab_cats': 'Topic coverage',
 'ex_h': 'LLM-extracted numeric results',
 'ex_warn': '⚠ UNVERIFIED — auto-extracted by Claude from the source PDFs and awaiting human '
            'spot-check. The curated seed values (Overview tab) are the reference; these are the '
            'full harvest, every value traceable to a verbatim quote.',
 'ex_n': 'Each row is one numeric value the model found in a paper, with its verbatim source '
         'location. Filter, then verify against the PDF using the quote.',
 'ex_search': 'Search quantity / paper / quote',
 'ex_paper': 'Paper',
 'ex_only_flag': 'only ⚠ needs-verify',
 'note_purity': "⚑ What 'purity %' means here: it is the protein CONTENT of the powder — one axis "
                "only. The project's real target is a CLEAN POWDER — minimum off-odor, off-flavor, "
                'and green color. Those sensory & color goals matter more than protein % alone; '
                'track their (sparse) coverage in the Gaps & target tab.',
 'tab_normalize': 'Cross-study',
 'tab_exports': 'Harmonized exports',
 'tab_knowledge': 'Knowledge / DOE',
 'tab_verify': 'Verify',
 'tab_gaps': 'Gaps & target',
 'tab_compare': 'Compare / query',
 'norm_h': 'Cross-study comparison (normalization)',
 'norm_n': 'Pick a measured quantity → every value for it across all studies, aligned to one unit '
           "so they are comparable — the 'learnable matrix'. Seed = curated; extracted = auto "
           '(unverified).',
 'norm_pick': 'Quantity',
 'norm_unit': 'Units seen',
 'norm_learnable': 'studies covering this quantity',
 'ver_h': 'Verification workbench',
 'ver_n': 'The action path for flagged values. Edit a value in place, tick ✓ verified, add a note '
          '— then Save writes back to db/leaf_lit.db. This is how the AI-built numbers become '
          'human-verified gold.',
 'ver_scope': 'Show',
 'ver_flagged': 'only needs-verify / unverified',
 'ver_all': 'all',
 'ver_save': '💾 Save changes to DB',
 'ver_saved': 'Saved. Reloading…',
 'ver_none': 'Nothing to verify with the current filter.',
 'gaps_h': 'Coverage & gaps — including the real (sensory) target',
 'gaps_n': 'Where is the corpus thin? Rows = species, columns = outcome. Empty / low cells are '
           'gaps to fill. The sensory/color columns (off_odor, off_flavor, color) are the '
           "project's actual goal — and are visibly the least covered.",
 'gaps_sensory': 'Sensory & color target coverage (the real goal, not protein %)',
 'cmp_h': 'Compare studies',
 'cmp_pick': 'Pick 2–4 papers to compare',
 'cmp_n': 'Line up methods and numbers side by side.',
 'qry_h': 'Query the numeric matrix',
 'qry_n': 'Build a filtered, analysable table across all studies — then download it.',
 'qry_prov': 'Source',
 'qry_dl': '⬇ Download CSV',
 'exports_h': 'Download auditable data layers',
 'exports_n': 'Raw is immutable. Validated adds human/curator decisions. Harmonized adds ontology, '
              'canonical units and explicit conversion formulas. Analysis-ready contains only '
              'validated, successfully harmonized rows.',
 'knowledge_h': 'Evidence claims to experiment candidates',
 'knowledge_n': 'Family-level rows identify DOE factors; signature-level rows preserve exact process order. '
                'Every candidate traces back to claims, papers and source quotations.',
 'ver_how': '**How to verify — you are confirming numbers the AI already extracted, not hunting '
            'for missing data:** ① note the **paper**; ② read the **source (verbatim)** column — '
            "it quotes the exact table / section the number came from; ③ open that paper's PDF and "
            'find it; ④ if correct, tick **✓ verified**; if wrong, type the **corrected value** + '
            'a note; ⑤ press **Save**.',
 'ver_pdf': 'PDF to open',
 'norm_sensory_only': '🎯 only sensory / colour parameters (the real target)',
 'norm_none': 'No parameter matches. Uncheck the sensory filter.',
 'norm_is_sensory': "sensory / colour — the project's real target",
 'norm_thin': '⚠ Only one study reports this — too thin for a cross-study comparison yet (this is '
              'exactly the kind of gap the Gaps tab surfaces).',
 'ro_banner': '🔒 Read-only shared view. Browsing, charts, and CSV export work; editing & '
              'verification happen on the local instance (to protect the data).',
 'purity_h': 'Protein purity across the corpus',
 'purity_n': "Each bar is one study's best reported purity. Amber = parsed from a narrative note, "
             'flagged for human verification (never trusted blindly).',
 'yield_h': 'Extraction yield across the corpus',
 'yield_n': 'The purity–yield trade-off is visible: the purest routes rarely give the highest '
            'yield.',
 'filters': 'Filters',
 'f_species': 'Species',
 'f_rel': 'Relevance',
 'f_source_type': 'Scientific / patent',
 'f_flag': 'Only papers with a needs-verify value',
 'f_search': 'Search title / species / method',
 'showing': 'Showing',
 'of': 'of',
 'papers': 'papers',
 'story': 'Scientific story',
 'findings': 'Findings',
 'tags': 'Topic tags',
 'open': 'open details',
 'ai_intro': 'Papers whose **reported method is a machine-learning, deep-learning, digital-twin, '
             'or statistical-optimization approach** — in leaf protein or in an analogous food '
             'system whose method transfers to leaf-protein purification. Each card states the '
             'transfer logic (why an off-topic system still informs this project).',
 'ai_core': 'Machine learning · deep learning · digital twins',
 'ai_core_n': 'The AI-sensing / AI-modeling precedents. None are about leaf protein — they prove '
              'the *method* works in a comparable food problem.',
 'ai_other': 'Other computational methods (optimization · proteomics)',
 'ai_other_n': 'Statistical process optimization (DOE / RSM) and proteomic characterization — '
               'computational, but not AI-sensing precedents.',
 'technique': 'Technique',
 'system': 'System (not leaf protein)',
 'transfer': 'Why it transfers',
 'ai_done': 'What was done',
 'ai_relevance': 'Why it matters for this project',
 'ai_findings': 'Reported findings',
 'ai_evidence': 'Evidence status',
 'ai_values': 'Measured / extracted values',
 'ai_values_n': 'Values currently stored for this paper. Auto-extracted rows remain unverified '
                'until checked against the quoted source location.',
 'ai_no_values': 'No numeric results are currently stored for this paper.',
 'ai_doi': 'Open DOI',
 'ai_scholar': 'Search title in Google Scholar',
 'ai_pick': 'Choose a paper to inspect in detail',
 'ai_open_n': 'The index stays lightweight; full findings and extracted values load only for '
              'the selected paper.',
 'no_rows': 'No papers match these filters.',
 'cats_h': 'Topic coverage',
 'cats_n': 'The controlled vocabulary that makes the corpus queryable.',
 'prov': 'Every number traces to a paper_id · nothing fabricated · null ≠ zero',
 'reported': 'reported value',
 'needs': 'needs verify',
 'sensory_h': 'Sensory target matrix',
 'sensory_n': 'The real product target: not just protein recovery, but lower off-flavor, lower '
              'off-odor, less green colour, and lower enzymatic oxidation markers. This view '
              'shows where the corpus has measured target evidence and where it is still thin.',
 'evidence_h': 'Core vs transfer evidence',
 'evidence_n': 'Core evidence directly studies leaf/pulse/plant-protein extraction or ingredient '
               'quality. Transfer evidence is mechanistically useful but comes from adjacent '
               'systems such as fish, shrimp, tea, or generic hydrolysates.',
 'hyp_h': 'Working hypothesis map',
 'hyp_n': 'The literature is converging on a process hypothesis: clean leaf protein requires '
          'early control of enzymatic oxidation and pigment/phenolic carryover, then a '
          'separation step that preserves functional protein while stripping sensory defects.',
 'coverage': 'coverage',
 'core_evidence': 'Core evidence',
 'transfer_evidence': 'Transfer evidence'}
TECH_LABEL = {
    "deep_learning": "Deep learning", "ML": "Machine learning", "digital_twin": "Digital twin",
    "DOE_RSM": "DOE / RSM", "proteomics": "Proteomics",
}

# Curated plain-language accounts of what the five AI/ML records actually did.
# Several records are literature clusters or reviews, not single ML experiments;
# keeping that distinction visible prevents overstating the evidence.
AI_METHOD_EXPLANATIONS = {
    "mandal2026_ml_functional_performance": {
        "study_type": "Original machine-learning regression study",
        "workflow": (
            "Built a 150-point dataset spanning soy, pea, chickpea, rice, hemp, camelina and "
            "pennycress ingredients. The inputs were measurable structural descriptors such as "
            "surface hydrophobicity, zeta potential, undenatured protein, soluble polymers and "
            "beta-sheet content. Multiple regression models were trained and tuned with 5-fold "
            "cross-validation."
        ),
        "target": (
            "Predict solubility, emulsifying activity, emulsifying capacity and gel strength "
            "without running every functional test on every candidate ingredient."
        ),
        "result": (
            "Gaussian support-vector regression was the strongest physically plausible model "
            "(reported R²: 0.7383–0.8906 across the four targets)."
        ),
        "project_use": (
            "A direct precedent for screening a leaf-protein ingredient from a compact panel of "
            "analytical measurements; it does not predict off-flavor, color or LOX activity."
        ),
    },
    "digital_twin_food_processing_cluster": {
        "study_type": "Cluster; the main evidence is one verified neural-ODE control study",
        "workflow": (
            "Kannapinn et al. generated process trajectories with a high-fidelity finite-element "
            "simulation of chicken cooking, trained an augmented neural ODE as a fast reduced-order "
            "surrogate, and embedded it in model-predictive control. At each control step, a "
            "sub-optimization re-synchronized the surrogate with the measured core temperature."
        ),
        "target": (
            "Predict the evolving thermal state fast enough to choose oven controls online and "
            "reach product targets autonomously."
        ),
        "result": (
            "The surrogate reported 0.18–0.49% relative time-series error and ran about 36,000× "
            "faster than real time, enabling many candidate control trajectories to be evaluated."
        ),
        "project_use": (
            "A methodological precedent for a dynamic process twin. Important limitation: this was "
            "an in-silico oven experiment trained on clean simulation data—not a leaf-protein or "
            "off-flavor experiment using sparse, noisy physical sensor data."
        ),
    },
    "search_2026_sfp2_70048": {
        "study_type": "Review article—not a new ML model or training experiment",
        "workflow": (
            "Reviewed nutritional, sensory and functional limitations of plant proteins, then "
            "organized physical, chemical and biological modification methods and their effects on "
            "protein structure. A final section surveyed AI, machine learning and molecular docking "
            "examples used to connect molecular or structural changes with ingredient behavior."
        ),
        "target": (
            "Provide an integrated map of how processing changes structure and how computational "
            "tools can help interpret or predict the resulting quality."
        ),
        "result": (
            "Its contribution is synthesis and examples, not a validated model, dataset or new "
            "prediction accuracy."
        ),
        "project_use": (
            "Useful for framing and references across structure, off-flavor and functionality, but "
            "it should not be counted as independent experimental ML evidence."
        ),
    },
    "enose_ml_offflavor_cluster": {
        "study_type": "Cluster combining review evidence with a catfish e-nose experiment",
        "workflow": (
            "In the catfish study, headspace from good-flavor and off-flavor fillet cores was read "
            "by a 32-sensor conducting-polymer electronic nose. Sensor resistance patterns were "
            "used to build reference odor classes and train an artificial neural-network pattern "
            "recognizer for unknown samples. The associated review supplies broader field context."
        ),
        "target": (
            "Classify a food sample as good-flavor or off-flavor from its multichannel volatile "
            "fingerprint rather than relying only on human graders."
        ),
        "result": (
            "Across three trials, the catfish system correctly identified 90.7–98.8% of off-flavor "
            "samples and 95.3–98.5% of good-flavor samples, with some inconclusive cases."
        ),
        "project_use": (
            "Shows that sensor-array fingerprints can support learned off-flavor classification. "
            "It is transfer evidence from fish, and does not establish performance for leaf protein."
        ),
    },
    "deuscher2019_chocolate_ptrms": {
        "study_type": "Original chemometric sensory-classification study",
        "workflow": (
            "Deuscher et al. measured PTR-ToF-MS volatile fingerprints for 206 dark chocolates "
            "already assigned to four sensory categories, then trained a supervised PLS-DA model "
            "and used feature selection to find discriminating ions. Samples required two hours of "
            "headspace equilibration; acquisition took five minutes per vial."
        ),
        "target": (
            "Predict one of four human sensory categories from a PTR-ToF-MS headspace fingerprint."
        ),
        "result": (
            "The full model correctly classified 60/62 independent test samples (96.8%). Models "
            "using 22 and 10 selected ions classified 56/62 and 57/62, respectively."
        ),
        "project_use": (
            "A close precedent for mapping VOC fingerprints to sensory labels. PLS-DA is classical "
            "chemometrics—not deep learning—and the study used chocolate rather than leaf protein."
        ),
    },
}

# Read-only mode for the shared/deployed instance: no DB writes (verification is
# done on the local instance). Set env LEAF_READONLY=1 on Streamlit Cloud.
READ_ONLY = os.environ.get("LEAF_READONLY", "").lower() in ("1", "true", "yes")

# Human-readable names for the controlled quantities (the raw keys are terse).
QUANTITY_LABEL = {
    "protein_purity_pct": "Protein content %  (how pure)",
    "yield_pct": "Yield %  (how much protein recovered)",
    "chlorophyll_removal_pct": "Chlorophyll removal %  (colour)",
    "rubisco_specificity_pct": "RuBisCO specificity %",
    "chlorophyll_content": "Chlorophyll content  (colour)",
    "sensory_offodor_score": "Off-odor score  (aroma)",
    "sensory_offflavor_score": "Off-flavor score  (taste)",
    "total_C6_aldehydes": "Total C6 aldehydes  (green aroma)",
    "hexanal_conc": "Hexanal  (grassy aroma)",
    "color_L": "Colour L*  (lightness)", "color_a": "Colour a*  (green–red)",
    "color_b": "Colour b*  (blue–yellow)", "LOX_activity": "LOX activity",
    "model_r2_solubility": "Model R2 — solubility prediction",
    "model_r2_emulsifying_activity_index": "Model R2 — emulsifying activity prediction",
    "model_r2_emulsifying_capacity": "Model R2 — emulsifying capacity prediction",
    "sensory_classification_accuracy": "Sensory classification accuracy",
    "model_r2_gel_strength": "Model R2 — gel strength prediction",
    "model_rmse_solubility": "Model RMSE — solubility prediction",
    "model_rmse_emulsifying_activity_index": "Model RMSE — emulsifying activity prediction",
    "model_rmse_emulsifying_capacity": "Model RMSE — emulsifying capacity prediction",
    "model_rmse_gel_strength": "Model RMSE — gel strength prediction",
    "dataset_n_points": "Dataset size  (data points)",
}
# quantities that speak to the REAL target — off-odor / off-flavor / colour
_SENSORY_KW = ("odor", "odour", "flavor", "flavour", "aldehyde", "hexanal", "hexenal",
               "voc", "sensory", "aroma", "chlorophyll", "color", "colour", "green", "lox")
TARGET_DIMENSIONS = {
    "Off-flavor / aroma": ("odor", "odour", "flavor", "flavour", "aroma", "hexanal",
                           "aldehyde", "voc", "sensory", "beany"),
    "Colour / pigments": ("chlorophyll", "color", "colour", "green", "browning", "melanosis"),
    "Oxidation / enzymes": ("lox", "lipoxygenase", "polyphenol", "phenolic", "oxidation",
                            "enzyme", "enzymatic"),
    "Protein recovery": ("protein_purity", "yield", "rubisco", "solubility", "protein content"),
}
CORE_TERMS = ("leaf", "rubisco", "plant protein", "pea protein", "chickpea", "camelina",
              "pennycress", "clover", "duckweed", "alfalfa", "nettle", "sugar beet",
              "spinach", "radish", "moringa", "cassava", "cauliflower")
TRANSFER_TERMS = ("tuna", "shrimp", "tea", "fish", "hydrolysate", "liver", "chocolate",
                  "milk", "dairy")


def q_friendly(q: str) -> str:
    return QUANTITY_LABEL.get(q, (q or "").replace("_", " "))


def q_is_sensory(q: str) -> bool:
    ql = (q or "").lower()
    return any(k in ql for k in _SENSORY_KW)


def paper_blob(row) -> str:
    return " ".join([
        clean_text(row.get("paper_id") if hasattr(row, "get") else row.paper_id),
        clean_text(row.get("title") if hasattr(row, "get") else row.title),
        clean_text(row.get("system") if hasattr(row, "get") else row.system),
        clean_text(row.get("extraction_method_family") if hasattr(row, "get") else row.extraction_method_family),
        clean_text(row.get("scientific_story") if hasattr(row, "get") else row.scientific_story),
        " ".join(row.get("cats", []) if hasattr(row, "get") else row.cats),
    ]).lower()


def evidence_class(row) -> str:
    blob = paper_blob(row)
    target = any(k in blob for ks in TARGET_DIMENSIONS.values() for k in ks)
    core = any(k in blob for k in CORE_TERMS)
    transfer = any(k in blob for k in TRANSFER_TERMS)
    if core and target:
        return "Core evidence"
    if transfer and target:
        return "Transfer evidence"
    if core:
        return "Core context"
    return "Transfer/context"


def dimension_hits(row) -> list[str]:
    blob = paper_blob(row)
    return [name for name, terms in TARGET_DIMENSIONS.items() if any(t in blob for t in terms)]


_AROMA_KW = ("odor", "odour", "flavor", "flavour", "aldehyde", "hexanal", "hexenal",
             "voc", "sensory", "aroma", "lox")
_COLOUR_KW = ("chlorophyll", "color", "colour", "green")


def q_target_emoji(q: str) -> str:
    """👃 for aroma/flavor quantities, 🎨 for colour ones, '' otherwise —
    so a colour parameter never gets the nose icon."""
    ql = (q or "").lower()
    if any(k in ql for k in _AROMA_KW):
        return "👃"
    if any(k in ql for k in _COLOUR_KW):
        return "🎨"
    return ""


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


# ── data ──────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load(_mtime: float):
    con = sqlite3.connect(DB_PATH)
    papers = pd.read_sql_query("SELECT * FROM papers", con)
    numeric = pd.read_sql_query("SELECT * FROM numeric_results", con)
    cats = pd.read_sql_query("SELECT * FROM paper_categories", con)
    con.close()

    papers["year"] = pd.to_numeric(papers["year"], errors="coerce").astype("Int64")

    def cats_of(pid):
        return cats.loc[cats.paper_id == pid, "category"].tolist()

    papers["cats"] = papers.paper_id.map(cats_of)
    papers["species"] = papers.cats.map(
        lambda cs: next((c.split(":", 1)[1] for c in cs if c.startswith("species:")), "other"))
    papers["analysis"] = papers.cats.map(
        lambda cs: [c.split(":", 1)[1] for c in cs if c.startswith("analysis:")])

    if "provenance" not in numeric.columns:
        numeric["provenance"] = "seed"
    # headline purity/yield come from the curated SEED rows (one per paper), so the
    # overview charts stay clean; the many llm-extracted rows populate the Extracted tab.
    seed_num = numeric[numeric.provenance == "seed"]
    pv = seed_num[seed_num.quantity == "protein_purity_pct"].drop_duplicates("paper_id").set_index("paper_id")
    yv = seed_num[seed_num.quantity == "yield_pct"].drop_duplicates("paper_id").set_index("paper_id")
    papers["purity"] = papers.paper_id.map(pv["value"])
    papers["purity_flag"] = papers.paper_id.map(pv["needs_human"]).fillna(0).astype(int)
    papers["yield"] = papers.paper_id.map(yv["value"])
    papers["yield_flag"] = papers.paper_id.map(yv["needs_human"]).fillna(0).astype(int)
    # NB: do NOT name this column "flags" — it collides with the reserved pandas
    # DataFrame/Series `.flags` attribute, so attribute access returns the wrong thing.
    papers["n_flags"] = papers.paper_id.map(
        seed_num[seed_num.needs_human == 1].groupby("paper_id").size()).fillna(0).astype(int)
    papers["n_extracted"] = papers.paper_id.map(
        numeric[numeric.provenance != "seed"].groupby("paper_id").size()
    ).fillna(0).astype(int)
    papers["year_str"] = papers["year"].map(lambda y: "" if pd.isna(y) else str(int(y)))
    return papers, numeric, cats


@st.cache_data(show_spinner=False)
def export_frames(_mtime: float):
    con = sqlite3.connect(DB_PATH)
    raw = pd.read_sql_query(
        """SELECT n.result_id, n.paper_id, p.title, p.year, p.source_type, p.system,
                  n.quantity, n.value AS value_raw, n.unit AS unit_raw,
                  n.sd_error, n.error_type, n.n_replicates, n.p_value,
                  n.method, n.species, n.treatment_condition, n.basis,
                  n.source_location, n.is_from_SI, n.provenance, n.needs_human,
                  n.extracted_date
           FROM numeric_results n JOIN papers p USING(paper_id)""", con)
    validated = pd.read_sql_query(
        """SELECT n.result_id, n.paper_id, n.quantity, n.value AS value_raw, n.unit AS unit_raw,
                  n.verified, n.verified_value, n.verified_by, n.confidence,
                  n.verified_note, n.verified_date, n.provenance, n.needs_human,
                  CASE WHEN n.verified=1 THEN 'human_verified'
                       WHEN n.provenance='seed_verified' THEN 'curator_verified'
                       WHEN n.provenance='seed' AND COALESCE(n.needs_human,0)=0 THEN 'curated_seed_clean'
                       ELSE 'assumed_validated_pending_audit' END AS validation_basis,
                  CASE WHEN n.verified=1 AND n.verified_value IS NOT NULL
                       THEN n.verified_value ELSE n.value END AS value_validated,
                  n.source_location
           FROM numeric_results n""", con)
    harmonized = pd.read_sql_query(
        """SELECT n.result_id, n.paper_id, p.title, n.quantity AS quantity_raw,
                  n.value AS value_raw, n.unit AS unit_raw,
                  CASE WHEN n.verified=1 AND n.verified_value IS NOT NULL
                       THEN n.verified_value ELSE n.value END AS value_validated,
                  CASE WHEN n.verified=1 THEN 'human_verified'
                       WHEN n.provenance='seed_verified' THEN 'curator_verified'
                       WHEN n.provenance='seed' AND COALESCE(n.needs_human,0)=0 THEN 'curated_seed_clean'
                       ELSE 'assumed_validated_pending_audit' END AS validation_basis,
                  h.quantity_std, h.value_std, h.unit_std, h.ontology_term,
                  h.harmonization_status, h.conversion_formula, h.mapping_version,
                  h.harmonization_notes, n.treatment_condition, n.basis,
                  f.ph, f.temperature_c, f.time_min, f.oxygen_control,
                  f.sonication, f.heat_treatment, f.feature_status,
                  n.source_location, n.provenance
           FROM numeric_results n JOIN papers p USING(paper_id)
           LEFT JOIN numeric_results_harmonized h USING(result_id)
           LEFT JOIN treatment_features f USING(result_id)""", con)
    con.close()
    valid_basis = {"human_verified", "curator_verified", "curated_seed_clean"}
    if ASSUME_ALL_VALIDATED:
        valid_basis.add("assumed_validated_pending_audit")
    analysis_long = harmonized[
        harmonized.validation_basis.isin(valid_basis)
        & harmonized.harmonization_status.isin(["exact", "converted"])
        & harmonized.value_std.notna()
    ].copy()
    analysis_long["feature_key"] = (
        analysis_long.quantity_std.fillna("unknown") + "__" +
        analysis_long.unit_std.fillna("unit_unknown").astype(str).str.replace(r"[^A-Za-z0-9]+", "_", regex=True) + "__" +
        analysis_long.basis.fillna("basis_unknown").astype(str).str.replace(r"[^A-Za-z0-9]+", "_", regex=True)
    )
    index_cols = ["paper_id", "treatment_condition", "ph", "temperature_c", "time_min",
                  "oxygen_control", "sonication", "heat_treatment"]
    if len(analysis_long):
        wide_source = analysis_long.copy()
        wide_source["treatment_condition"] = wide_source.treatment_condition.fillna("not_reported")
        for col in index_cols[2:]:
            wide_source[col] = wide_source[col].fillna("not_reported")
        analysis_wide = wide_source.pivot_table(
            index=index_cols, columns="feature_key", values="value_std", aggfunc="first").reset_index()
        analysis_wide.columns.name = None
    else:
        analysis_wide = pd.DataFrame(columns=index_cols)
    return raw, validated, harmonized, analysis_long, analysis_wide


@st.cache_data(show_spinner=False)
def knowledge_frames(_mtime: float):
    con = sqlite3.connect(DB_PATH)
    try:
        claims = pd.read_sql_query(
            """SELECT c.claim_id,c.paper_id,r.source_scope,r.study_role,r.evidence_domain,
                      t.treatment_family,t.treatment_signature,
                      c.outcome_id,c.comparator_type,c.direction,c.effect_type,c.effect_value,
                      c.effect_unit,c.confidence,c.quote_match,c.validation_status,
                      c.source_location,c.source_quote
               FROM evidence_claims c JOIN knowledge_treatments t USING(treatment_id)
               JOIN knowledge_paper_roles r USING(paper_id)""", con)
        candidates = pd.read_sql_query("SELECT * FROM experiment_candidates", con)
    except Exception:
        claims, candidates = pd.DataFrame(), pd.DataFrame()
    con.close()
    return claims, candidates


def ensure_cols():
    """Add verification columns to numeric_results if missing (one-time migration)."""
    con = sqlite3.connect(DB_PATH)
    have = [r[1] for r in con.execute("PRAGMA table_info(numeric_results)")]
    for name, ddl in [("provenance", "TEXT DEFAULT 'seed'"), ("verified", "INTEGER DEFAULT 0"),
                      ("verified_value", "REAL"), ("verified_by", "TEXT"),
                      ("confidence", "TEXT"), ("verified_note", "TEXT"), ("verified_date", "TEXT")]:
        if name not in have:
            con.execute(f"ALTER TABLE numeric_results ADD COLUMN {name} {ddl}")
    con.commit()
    con.close()


ensure_cols()
mtime = os.path.getmtime(DB_PATH) if os.path.exists(DB_PATH) else 0.0
papers, numeric, cats = load(mtime)

# ── global CSS ────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  .stApp {{background:{CANVAS}}}
  header[data-testid="stHeader"] {{background:{CANVAS};box-shadow:0 1px 0 {RING}}}
  .block-container {{padding-top:4.4rem;max-width:1400px}}
  h1,h2,h3 {{letter-spacing:-.01em}}
  .llead {{color:{INK2};font-size:.95rem;max-width:70ch}}
  .eyebrow {{font-family:ui-monospace,Menlo,monospace;font-size:.72rem;letter-spacing:.18em;
     text-transform:uppercase;color:{AMBER};margin-bottom:.35rem}}
  div[data-testid="stMetric"] {{background:{SURFACE};border:1px solid {RING};border-radius:14px;
     padding:14px 16px;box-shadow:0 1px 2px rgba(15,23,42,.04)}}
  div[data-testid="stMetricValue"] {{font-variant-numeric:tabular-nums}}
  .chip {{display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:.68rem;
     padding:2px 9px;border-radius:999px;border:1px solid {RING};color:{INK2};margin:2px 4px 2px 0}}
  .chip.tech {{color:{ACCENT};border-color:{ACCENT}}}
  .chip.sys {{color:{CYAN};border-color:{CYAN}}}
  .aicard {{background:{SURFACE};border:1px solid {RING};border-left:3px solid {ACCENT};
     border-radius:12px;padding:14px 18px;margin-bottom:10px}}
  .transfer {{color:{INK};font-size:.9rem;border-left:2px solid {AMBER};padding-left:12px;margin-top:8px}}
  .foot {{color:{INK2};font-family:ui-monospace,Menlo,monospace;font-size:.75rem;
     border-top:1px solid {RING};margin-top:2rem;padding-top:1rem}}
</style>
""", unsafe_allow_html=True)

# ── sidebar: refresh ──────────────────────────────────────────────────────────
t = T
with st.sidebar:
    st.markdown("### Leaf Literature Agent")
    if st.button(t["refresh"], width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption(t["phase"])
    st.caption(f"db/leaf_lit.db · {len(papers)} {t['k_papers'].lower()}")
    if READ_ONLY:
        st.caption("🔒 read-only shared view")


# ── header ────────────────────────────────────────────────────────────────────
st.markdown(f'<div class="eyebrow">Leaf Protein · Literature Intelligence</div>', unsafe_allow_html=True)
st.markdown(f"# {t['title']}")
st.markdown(f'<p class="llead">{t["tagline"]}</p>', unsafe_allow_html=True)

seed_num = numeric[numeric.provenance == "seed"]
extracted_num = numeric[numeric.provenance != "seed"]
n_flag = int((seed_num.needs_human == 1).sum())
n_full = int(papers.verification_level.fillna("").str.contains("full_text").sum())
n_ai = int(papers.analysis.map(lambda a: any(x in a for x in ("ML", "deep_learning", "digital_twin"))).sum())

c = st.columns(7)
c[0].metric(t["k_papers"], len(papers))
c[1].metric(t["k_numeric"], len(seed_num))
c[2].metric(t["k_flag"], n_flag)
c[3].metric(t["k_species"], papers.species.nunique())
c[4].metric(t["k_full"], n_full)
c[5].metric(t["k_ai"], n_ai)
c[6].metric(t["k_extracted"], len(extracted_num), help=t["k_extracted_help"])

(tab_ov, tab_sensory, tab_evidence, tab_hypothesis, tab_corpus, tab_ex, tab_norm, tab_exports, tab_knowledge, tab_verify, tab_gaps,
 tab_compare, tab_ai, tab_cats) = st.tabs(
    [t["tab_overview"], t["tab_sensory"], t["tab_evidence"], t["tab_hypothesis"],
     t["tab_corpus"], t["tab_extracted"], t["tab_normalize"], t["tab_exports"], t["tab_knowledge"],
     t["tab_verify"], t["tab_gaps"], t["tab_compare"], t["tab_ai"], t["tab_cats"]])


# ── charts helper ─────────────────────────────────────────────────────────────
def bar_chart(df, quantity, title):
    d = df[df.quantity == quantity].copy()
    d["status"] = d.needs_human.map({0: t["reported"], 1: t["needs"]})
    d["src"] = d.source_location.str.slice(0, 160)
    chart = (
        alt.Chart(d)
        .mark_bar(cornerRadiusEnd=4, height=16)
        .encode(
            x=alt.X("value:Q", title=None, scale=alt.Scale(domain=[0, 100]),
                    axis=alt.Axis(grid=True, gridColor=RING, format="~s")),
            y=alt.Y("paper_id:N", sort="-x", title=None,
                    axis=alt.Axis(labelColor=INK2, labelFont="ui-monospace", labelLimit=200)),
            color=alt.Color("status:N",
                            scale=alt.Scale(domain=[t["reported"], t["needs"]], range=[ACCENT, AMBER]),
                            legend=alt.Legend(title=None, orient="top", labelColor=INK2)),
            tooltip=[alt.Tooltip("paper_id:N"), alt.Tooltip("value:Q", title=quantity),
                     alt.Tooltip("species:N"), alt.Tooltip("src:N", title="source")],
        )
        .properties(height=max(240, 22 * len(d)))
        .configure_view(strokeWidth=0, fill=SURFACE)
        .configure_axis(labelColor=INK2, titleColor=INK2)
    )
    return chart


with tab_ov:
    st.info(t["note_purity"])
    st.markdown(f"#### {t['purity_h']}")
    st.markdown(f'<p class="llead">{t["purity_n"]}</p>', unsafe_allow_html=True)
    st.altair_chart(bar_chart(seed_num, "protein_purity_pct", t["purity_h"]), width="stretch")
    st.markdown(f"#### {t['yield_h']}")
    st.markdown(f'<p class="llead">{t["yield_n"]}</p>', unsafe_allow_html=True)
    st.altair_chart(bar_chart(seed_num, "yield_pct", t["yield_h"]), width="stretch")


with tab_sensory:
    st.markdown(f"### {t['sensory_h']}")
    st.markdown(f'<p class="llead">{t["sensory_n"]}</p>', unsafe_allow_html=True)
    target_quantities = sorted(q for q in numeric.quantity.dropna().unique() if q_is_sensory(q))
    target_rows = numeric[numeric.quantity.isin(target_quantities)].copy()

    sm = st.columns(4)
    sm[0].metric("Target quantities", len(target_quantities))
    sm[1].metric("Papers with target data", target_rows.paper_id.nunique())
    sm[2].metric("Target numeric rows", len(target_rows))
    sm[3].metric("Need verification", int(target_rows.needs_human.fillna(0).sum()) if len(target_rows) else 0)

    dim_records = []
    for _, p in papers.iterrows():
        for dim in dimension_hits(p):
            dim_records.append({
                "paper_id": p.paper_id,
                "dimension": dim,
                "evidence": evidence_class(p),
                "relevance": clean_text(p.relevance) or "Unknown",
            })
    dim_df = pd.DataFrame(dim_records)
    if len(dim_df):
        heat = dim_df.groupby(["dimension", "evidence"]).paper_id.nunique().reset_index(name="papers")
        chart = (
            alt.Chart(heat).mark_rect().encode(
                x=alt.X("evidence:N", title=None, axis=alt.Axis(labelColor=INK2, labelAngle=-20)),
                y=alt.Y("dimension:N", title=None, axis=alt.Axis(labelColor=INK2)),
                color=alt.Color("papers:Q", scale=alt.Scale(scheme="greens"),
                                legend=alt.Legend(title="papers", labelColor=INK2)),
                tooltip=["dimension", "evidence", "papers"],
            ).properties(height=240).configure_view(strokeWidth=0, fill=SURFACE)
        )
        st.markdown(f"#### {t['coverage']}")
        st.altair_chart(chart, width="stretch")

    if len(target_rows):
        view = target_rows.copy()
        view["quantity"] = view.quantity.map(q_friendly)
        view["source"] = view.provenance.map(lambda p: "seed" if p == "seed" else "extracted")
        st.dataframe(
            view[["paper_id", "quantity", "value", "unit", "source", "needs_human", "source_location"]]
            .sort_values(["paper_id", "quantity"]),
            width="stretch", hide_index=True,
            column_config={"value": st.column_config.NumberColumn(format="%.4g"),
                           "source_location": st.column_config.TextColumn("source", width="large")},
        )
    else:
        st.info("No sensory / colour numeric rows yet.")


with tab_evidence:
    st.markdown(f"### {t['evidence_h']}")
    st.markdown(f'<p class="llead">{t["evidence_n"]}</p>', unsafe_allow_html=True)
    ev = papers.copy()
    ev["evidence"] = ev.apply(evidence_class, axis=1)
    ev["target_dimensions"] = ev.apply(lambda r: ", ".join(dimension_hits(r)) or "context only", axis=1)
    ev["target_hits"] = ev.target_dimensions.ne("context only")

    em = st.columns(4)
    em[0].metric(t["core_evidence"], int((ev.evidence == "Core evidence").sum()))
    em[1].metric(t["transfer_evidence"], int((ev.evidence == "Transfer evidence").sum()))
    em[2].metric("Core context", int((ev.evidence == "Core context").sum()))
    em[3].metric("Target-related papers", int(ev.target_hits.sum()))

    counts = ev.groupby(["evidence", "relevance"]).paper_id.nunique().reset_index(name="papers")
    if len(counts):
        chart = (
            alt.Chart(counts).mark_bar(cornerRadiusEnd=4).encode(
                x=alt.X("papers:Q", title=None, axis=alt.Axis(grid=True, gridColor=RING)),
                y=alt.Y("evidence:N", title=None, sort="-x", axis=alt.Axis(labelColor=INK2)),
                color=alt.Color("relevance:N", legend=alt.Legend(title=None, orient="top", labelColor=INK2),
                                scale=alt.Scale(scheme="tableau10")),
                tooltip=["evidence", "relevance", "papers"],
            ).properties(height=260).configure_view(strokeWidth=0, fill=SURFACE)
        )
        st.altair_chart(chart, width="stretch")

    show = ev[["paper_id", "year_str", "species", "relevance", "evidence",
               "target_dimensions", "title", "n_extracted"]].rename(columns={
                   "paper_id": "paper", "year_str": "year", "target_dimensions": "target dimensions",
                   "n_extracted": "extracted rows"})
    st.dataframe(show.sort_values(["evidence", "relevance", "paper"]), width="stretch", hide_index=True)


with tab_hypothesis:
    st.markdown(f"### {t['hyp_h']}")
    st.markdown(f'<p class="llead">{t["hyp_n"]}</p>', unsafe_allow_html=True)
    steps = [
        ("1. Oxidation starts early",
         "Cell disruption exposes lipids, phenolics, pigments and enzymes. LOX/PPO-style chemistry is the recurring risk signal."),
        ("2. Sensory defects are measurable",
         "The corpus now has explicit hooks for aldehydes, hexanal, off-odor/off-flavor scores, chlorophyll and colour coordinates."),
        ("3. Intervention must be upstream",
         "Promising routes are rapid pH control, heat/radio-frequency inactivation, antioxidant handling and pigment/phenolic removal."),
        ("4. Protein quality still constrains the route",
         "A clean powder is only useful if recovery, purity, solubility and functional performance stay within the target window."),
    ]
    cols = st.columns(4)
    for col, (head, body) in zip(cols, steps):
        col.markdown(f"**{head}**")
        col.markdown(body)

    st.divider()
    hypo = papers.copy()
    hypo["evidence"] = hypo.apply(evidence_class, axis=1)
    hypo["target_dimensions"] = hypo.apply(lambda r: ", ".join(dimension_hits(r)) or "", axis=1)
    hypo = hypo[hypo.target_dimensions.ne("")]
    if len(hypo):
        st.markdown("#### Papers supporting the hypothesis")
        st.dataframe(
            hypo[["paper_id", "year_str", "species", "relevance", "evidence",
                  "target_dimensions", "title", "scientific_story"]]
            .rename(columns={"paper_id": "paper", "year_str": "year",
                             "target_dimensions": "target dimensions", "scientific_story": "story"})
            .sort_values(["relevance", "evidence", "paper"]),
            width="stretch", hide_index=True,
            column_config={"story": st.column_config.TextColumn(width="large"),
                           "title": st.column_config.TextColumn(width="large")},
        )


with tab_ex:
    st.markdown(f"### {t['ex_h']}")
    st.warning(t["ex_warn"])
    st.markdown(f'<p class="llead">{t["ex_n"]}</p>', unsafe_allow_html=True)
    exd = extracted_num.copy()
    fx = st.columns([1.6, 1.4, 1])
    exq = fx[0].text_input(t["ex_search"], "", key="ex_q")
    exp = fx[1].multiselect(t["ex_paper"], sorted(exd.paper_id.unique()), key="ex_paper")
    exflag = fx[2].checkbox(t["ex_only_flag"], key="ex_flag")
    if exp:
        exd = exd[exd.paper_id.isin(exp)]
    if exflag:
        exd = exd[exd.needs_human == 1]
    if exq:
        hay = (exd.quantity.fillna("") + " " + exd.paper_id + " "
               + exd.source_location.fillna("")).str.lower()
        exd = exd[hay.str.contains(re.escape(exq.lower()))]
    st.caption(f"{t['showing']} {len(exd)} {t['of']} {len(extracted_num)}")
    show = exd[["paper_id", "quantity", "value", "unit", "treatment_condition",
                "needs_human", "source_location"]].rename(
        columns={"paper_id": "paper", "needs_human": "⚠", "source_location": "source (verbatim)"})
    st.dataframe(show, width="stretch", hide_index=True,
                 column_config={"value": st.column_config.NumberColumn(format="%.3g")})


with tab_corpus:
    st.markdown(f"### {t['filters']}")
    fc = st.columns([2, 1.4, 1.4, 1.4])
    q = fc[0].text_input(t["f_search"], "")
    fsp = fc[1].multiselect(t["f_species"], sorted(papers.species.unique()))
    frel = fc[2].multiselect(t["f_rel"], ["High", "Medium", "Low"])
    fsource = fc[3].multiselect(t["f_source_type"], sorted(papers.source_type.dropna().unique()))
    fflag = st.checkbox(t["f_flag"], value=False)

    view = papers.copy()
    if fsp:
        view = view[view.species.isin(fsp)]
    if frel:
        view = view[view.relevance.isin(frel)]
    if fsource:
        view = view[view.source_type.isin(fsource)]
    if fflag:
        view = view[view["n_flags"] > 0]
    if q:
        ql = q.lower()
        hay = (view.paper_id + " " + view.title.fillna("") + " " + view.system.fillna("")
               + " " + view.extraction_method_family.fillna("")).str.lower()
        view = view[hay.str.contains(re.escape(ql))]

    st.caption(f"{t['showing']} {len(view)} {t['of']} {len(papers)} {t['papers']}")
    show = view[["paper_id", "year", "source_type", "species", "relevance", "verification_level",
                 "purity", "yield", "n_flags"]].rename(columns={
        "paper_id": "paper", "verification_level": "text level", "n_flags": "⚠ flags"})
    st.dataframe(show, width="stretch", hide_index=True,
                 column_config={
                     "purity": st.column_config.NumberColumn(
                         "protein %", format="%.1f", help="Protein CONTENT of the isolate (how pure)."),
                     "yield": st.column_config.NumberColumn(
                         "yield %", format="%.1f",
                         help="How MUCH protein was recovered, as % of the protein in the leaf. "
                              "High purity + low yield = a pure product but little of it."),
                     "⚠ flags": st.column_config.NumberColumn(
                         "⚠", help="How many of this paper's numbers are flagged needs-verify.")})

    if len(view) == 0:
        st.info(t["no_rows"])
    for _, p in view.iterrows():
        flag = " ⚠" if p["n_flags"] else ""
        with st.expander(f"{p.paper_id} · {p.year_str} · {p.species}{flag}"):
            st.markdown(f"**{p.title or ''}**")
            if p.scientific_story:
                st.markdown(f"*{p.scientific_story}*")
            st.markdown("  ".join(f'<span class="chip">{c}</span>' for c in p.cats),
                        unsafe_allow_html=True)
            if p.key_findings:
                st.markdown(f"**{t['findings']}**")
                st.markdown(f'<div style="max-height:280px;overflow:auto;color:{INK2};font-size:.86rem;'
                            f'white-space:pre-wrap">{p.key_findings}</div>', unsafe_allow_html=True)
            meta = " · ".join(x for x in [f"doi: {clean_text(p.doi)}" if clean_text(p.doi) else "", clean_text(p.source_type)] if x)
            if meta:
                st.caption(meta)


with tab_ai:
    st.markdown(f'<p class="llead">{t["ai_intro"]}</p>', unsafe_allow_html=True)

    def ai_card(p):
        title = clean_text(p.title) or p.paper_id
        year = f" · {p.year_str}" if p.year_str else ""
        with st.expander(f"{title}{year}"):
            techs = "  ".join(
                f'<span class="chip tech">{TECH_LABEL.get(x, x)}</span>' for x in p.analysis)
            if techs:
                st.markdown(techs, unsafe_allow_html=True)

            authors = clean_text(p.authors)
            venue = clean_text(p.venue)
            if authors:
                st.markdown(f"**Authors:** {authors}")
            if venue:
                st.markdown(f"**Venue:** {venue}")

            links = []
            doi = clean_text(p.doi).strip()
            # Some legacy cluster rows contain prose after a DOI. Only create a DOI
            # link when the field itself is one clean identifier.
            if re.fullmatch(r"10\.\d{4,9}/\S+", doi, flags=re.I):
                links.append(f"[{t['ai_doi']}](https://doi.org/{doi})")
            links.append(
                f"[{t['ai_scholar']}](https://scholar.google.com/scholar?q={quote_plus(title)})")
            st.markdown(" · ".join(links))

            st.markdown(f"#### {t['ai_done']}")
            explanation = AI_METHOD_EXPLANATIONS.get(p.paper_id)
            if explanation:
                st.markdown(
                    f"**Study type:** {explanation['study_type']}\n\n"
                    f"**Workflow:** {explanation['workflow']}\n\n"
                    f"**Prediction / control target:** {explanation['target']}\n\n"
                    f"**Main result:** {explanation['result']}\n\n"
                    f"**What transfers to this project:** {explanation['project_use']}"
                )

            done = []
            system = clean_text(p.system)
            method_family = clean_text(p.extraction_method_family)
            if system:
                done.append(f"**System / material:** {system}")
            if method_family:
                done.append(f"**Reported approach:** {method_family}")
            paper_num = numeric[numeric.paper_id == p.paper_id]
            measured_methods = sorted({clean_text(x).strip() for x in paper_num.method if clean_text(x).strip()})
            if measured_methods:
                shown = ", ".join(measured_methods[:12])
                if len(measured_methods) > 12:
                    shown += f" (+{len(measured_methods) - 12} more)"
                done.append(f"**Methods represented in extracted results:** {shown}")
            if done:
                if explanation:
                    st.markdown("**Database method metadata**")
                st.markdown("\n\n".join(done))
            elif not explanation:
                st.caption("The database does not yet contain a detailed method description.")

            story = clean_text(p.scientific_story)
            if story:
                st.markdown(f"#### {t['ai_relevance']}")
                st.markdown(story)

            findings = clean_text(p.key_findings)
            if findings:
                st.markdown(f"#### {t['ai_findings']}")
                st.markdown(findings)

            evidence = " · ".join(filter(None, [
                f"verification: {clean_text(p.verification_level)}" if clean_text(p.verification_level) else "",
                f"access: {clean_text(p.access_status)}" if clean_text(p.access_status) else "",
                f"source: {clean_text(p.source_type)}" if clean_text(p.source_type) else "",
                f"paper_id: {p.paper_id}",
            ]))
            st.markdown(f"#### {t['ai_evidence']}")
            st.caption(evidence)

            st.markdown(f"#### {t['ai_values']}")
            if paper_num.empty:
                st.info(t["ai_no_values"])
            else:
                st.caption(f"{len(paper_num)} rows · {t['ai_values_n']}")
                value_cols = [
                    "quantity", "value", "unit", "method", "treatment_condition",
                    "source_location", "provenance", "needs_human", "verified",
                ]
                value_cols = [c for c in value_cols if c in paper_num.columns]
                st.dataframe(paper_num[value_cols], width="stretch", hide_index=True,
                             height=min(520, 38 + 35 * min(len(paper_num), 14)))

    core = papers[papers.analysis.map(lambda a: any(x in a for x in ("ML", "deep_learning", "digital_twin")))]
    other = papers[papers.analysis.map(lambda a: any(x in a for x in ("DOE_RSM", "proteomics"))) &
                   ~papers.paper_id.isin(core.paper_id)]

    def ai_index(frame):
        """Compact index only; rendering every paper's full extraction overloads Cloud."""
        rows = []
        for _, paper in frame.sort_values(["year", "title"], ascending=[False, True]).iterrows():
            doi = clean_text(paper.doi).strip()
            title = clean_text(paper.title) or paper.paper_id
            link = (f"https://doi.org/{doi}" if re.fullmatch(r"10\.\d{4,9}/\S+", doi, flags=re.I)
                    else f"https://scholar.google.com/scholar?q={quote_plus(title)}")
            rows.append({
                "paper_id": paper.paper_id,
                "year": paper.year,
                "title": title,
                "approach": ", ".join(TECH_LABEL.get(x, x) for x in paper.analysis),
                "system": clean_text(paper.system),
                "paper link": link,
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                     column_config={"paper link": st.column_config.LinkColumn(
                         "paper link", display_text="Open ↗")})

    st.markdown(f"### {t['ai_core']}")
    st.markdown(f'<p class="llead">{t["ai_core_n"]}</p>', unsafe_allow_html=True)
    ai_index(core)

    if len(other):
        st.markdown(f"### {t['ai_other']}")
        st.markdown(f'<p class="llead">{t["ai_other_n"]}</p>', unsafe_allow_html=True)
        ai_index(other)

    all_ai = pd.concat([core, other]).drop_duplicates("paper_id").sort_values("paper_id")
    st.markdown(f"### {t['open']}")
    st.caption(t["ai_open_n"])
    label_to_id = {
        f"{clean_text(row.title) or row.paper_id} ({row.year_str or 'year unknown'}) · {row.paper_id}":
            row.paper_id
        for _, row in all_ai.iterrows()
    }
    selected_label = st.selectbox(t["ai_pick"], list(label_to_id), key="ai_paper_detail")
    if selected_label:
        selected_ai = label_to_id[selected_label]
        ai_card(all_ai[all_ai.paper_id == selected_ai].iloc[0])


with tab_cats:
    st.markdown(f"### {t['cats_h']}")
    st.markdown(f'<p class="llead">{t["cats_n"]}</p>', unsafe_allow_html=True)
    cc = cats.copy()
    cc["group"] = cc.category.str.split(":").str[0]
    counts = cc.category.value_counts().reset_index()
    counts.columns = ["category", "n"]
    counts["group"] = counts.category.str.split(":").str[0]
    chart = (
        alt.Chart(counts).mark_bar(cornerRadiusEnd=4, height=16)
        .encode(
            x=alt.X("n:Q", title=None, axis=alt.Axis(grid=True, gridColor=RING)),
            y=alt.Y("category:N", sort="-x", title=None,
                    axis=alt.Axis(labelColor=INK2, labelFont="ui-monospace", labelLimit=220)),
            color=alt.Color("group:N", legend=alt.Legend(title=None, orient="top", labelColor=INK2),
                            scale=alt.Scale(scheme="tableau10")),
            tooltip=["category", "n"],
        )
        .properties(height=max(300, 20 * len(counts)))
        .configure_view(strokeWidth=0, fill=SURFACE)
    )
    st.altair_chart(chart, width="stretch")

with tab_norm:
    st.markdown(f"### {t['norm_h']}")
    st.markdown(f'<p class="llead">{t["norm_n"]}</p>', unsafe_allow_html=True)
    # study-count per quantity, shown at selection time (so a 1-study parameter is obvious)
    qcounts = numeric.groupby("quantity").paper_id.nunique().to_dict()
    only_sensory = st.checkbox(t["norm_sensory_only"], key="norm_sens")
    quants = [q for q in sorted(qcounts, key=lambda x: (-qcounts[x], x))
              if (not only_sensory or q_is_sensory(q))]
    if not quants:
        st.info(t["norm_none"])
    else:
        default_ix = quants.index("protein_purity_pct") if "protein_purity_pct" in quants else 0
        qsel = st.selectbox(
            t["norm_pick"], quants, index=default_ix,
            format_func=lambda q: f"{q_target_emoji(q) + ' ' if q_target_emoji(q) else ''}"
                                  f"{q_friendly(q)}  ·  {qcounts[q]} "
                                  f"{'study' if qcounts[q] == 1 else 'studies'}")
        d = numeric[numeric.quantity == qsel].copy()
        units = ", ".join(sorted({str(u) for u in d.unit.dropna().unique()})) or "—"
        st.caption(f"{t['norm_learnable']}: {d.paper_id.nunique()}   ·   {t['norm_unit']}: {units}"
                   + (f"   ·   {q_target_emoji(qsel)} {t['norm_is_sensory']}" if q_is_sensory(qsel) else ""))
        if d.paper_id.nunique() < 2:
            st.warning(t["norm_thin"])
        d["prov"] = d.provenance.map(lambda p: "seed" if p == "seed" else "extracted")
        dot = (
            alt.Chart(d).mark_circle(size=95, opacity=.8).encode(
                x=alt.X("value:Q", title=q_friendly(qsel)),
                y=alt.Y("paper_id:N", sort="-x", title=None,
                        axis=alt.Axis(labelColor=INK2, labelFont="ui-monospace", labelLimit=200)),
                color=alt.Color("prov:N", scale=alt.Scale(domain=["seed", "extracted"], range=[ACCENT, CYAN]),
                                legend=alt.Legend(title=None, orient="top", labelColor=INK2)),
                tooltip=["paper_id", "value", "unit", "species", "treatment_condition", "provenance", "source_location"],
            ).properties(height=max(240, 20 * d.paper_id.nunique()))
            .configure_view(strokeWidth=0, fill=SURFACE).configure_axis(labelColor=INK2, titleColor=INK2))
        st.altair_chart(dot, width="stretch")
        st.dataframe(
            d[["paper_id", "value", "unit", "species", "treatment_condition", "sd_error",
               "n_replicates", "provenance", "source_location"]].sort_values("value", ascending=False),
            width="stretch", hide_index=True)


with tab_exports:
    st.markdown(f"### {t['exports_h']}")
    st.markdown(f'<p class="llead">{t["exports_n"]}</p>', unsafe_allow_html=True)
    raw_x, valid_x, harm_x, analysis_long_x, analysis_wide_x = export_frames(mtime)
    validated_mask = valid_x.validation_basis.ne("unvalidated")
    harmonized_mask = harm_x.harmonization_status.isin(["exact", "converted", "identity_only"])
    metrics = st.columns(5)
    metrics[0].metric("Raw rows", len(raw_x))
    metrics[1].metric("Validated", int(validated_mask.sum()))
    metrics[2].metric("Harmonized", int(harmonized_mask.sum()))
    metrics[3].metric("Analysis-ready", len(analysis_long_x))
    metrics[4].metric("Papers represented", analysis_long_x.paper_id.nunique())

    coverage = pd.DataFrame([{
        "corpus_papers": len(papers),
        "full_text_or_SI_papers": int(papers.verification_level.fillna("").str.contains("full_text").sum()),
        "raw_numeric_rows": len(raw_x),
        "validated_rows": int(validated_mask.sum()),
        "harmonized_or_identity_preserved_rows": int(harmonized_mask.sum()),
        "analysis_ready_rows": len(analysis_long_x),
        "analysis_ready_papers": analysis_long_x.paper_id.nunique(),
        "excluded_unvalidated": int((~validated_mask).sum()),
        "validation_policy": "assume_all_pending_audit" if ASSUME_ALL_VALIDATED else "verified_only",
        "excluded_not_harmonizable_or_unmapped": int((~harmonized_mask).sum()),
        "mapping_version": next((x for x in harm_x.mapping_version.dropna().unique()), "not built"),
    }])
    st.markdown("#### Coverage manifest")
    st.dataframe(coverage, width="stretch", hide_index=True)
    st.warning("Temporary policy: all rows are included as assumed_validated_pending_audit. "
               "The original verified flags remain unchanged for the later formal audit.")

    st.markdown("#### Download layers")
    dl = st.columns(3)
    dl[0].download_button("⬇ 1 · Raw immutable", raw_x.to_csv(index=False).encode("utf-8"),
                          "leaf_data_1_raw.csv", "text/csv", width="stretch")
    dl[1].download_button("⬇ 2 · Validation layer", valid_x.to_csv(index=False).encode("utf-8"),
                          "leaf_data_2_validated.csv", "text/csv", width="stretch")
    dl[2].download_button("⬇ 3 · Harmonized long", harm_x.to_csv(index=False).encode("utf-8"),
                          "leaf_data_3_harmonized.csv", "text/csv", width="stretch")
    dl2 = st.columns(3)
    dl2[0].download_button("⬇ 4A · Analysis-ready long",
                           analysis_long_x.to_csv(index=False).encode("utf-8"),
                           "leaf_data_4_analysis_long.csv", "text/csv", width="stretch")
    dl2[1].download_button("⬇ 4B · Analysis-ready wide",
                           analysis_wide_x.to_csv(index=False).encode("utf-8"),
                           "leaf_data_4_analysis_wide.csv", "text/csv", width="stretch")
    dl2[2].download_button("⬇ Coverage manifest", coverage.to_csv(index=False).encode("utf-8"),
                           "leaf_data_coverage_manifest.csv", "text/csv", width="stretch")

    status_counts = harm_x.harmonization_status.fillna("not_built").value_counts().rename_axis(
        "harmonization_status").reset_index(name="rows")
    st.markdown("#### Harmonization exclusions")
    st.dataframe(status_counts, width="stretch", hide_index=True)


with tab_knowledge:
    st.markdown(f"### {t['knowledge_h']}")
    st.markdown(f'<p class="llead">{t["knowledge_n"]}</p>', unsafe_allow_html=True)
    claims_x, candidates_x = knowledge_frames(mtime)
    if claims_x.empty:
        st.info("Knowledge extraction has not been built yet.")
    else:
        km = st.columns(5)
        km[0].metric("Claims", len(claims_x))
        km[1].metric("Source-quote matched", int(claims_x.quote_match.fillna(0).sum()))
        km[2].metric("Papers", claims_x.paper_id.nunique())
        km[3].metric("Treatment families", claims_x.treatment_family.nunique())
        km[4].metric("Candidates", len(candidates_x))

        st.markdown("#### Experiment Candidate Matrix")
        level = st.radio("Aggregation", ["family", "signature"], horizontal=True,
                         help="Family selects DOE factors; signature preserves ordered process steps.")
        cm = candidates_x[candidates_x.aggregation_level == level].copy()
        cf = st.columns(5)
        selected_outcomes = cf[0].multiselect("Outcomes", sorted(cm.outcome_id.unique()))
        selected_families = cf[1].multiselect("Treatment families", sorted(cm.treatment_family.unique()))
        source_scope = cf[2].selectbox("Source type", ["scientific", "patent"])
        evidence_domain = cf[3].selectbox("Evidence domain", ["core_leaf_process", "transfer"])
        min_papers = cf[4].number_input("Minimum papers", min_value=1, value=1, step=1)
        if selected_outcomes:
            cm = cm[cm.outcome_id.isin(selected_outcomes)]
        if selected_families:
            cm = cm[cm.treatment_family.isin(selected_families)]
        cm = cm[(cm.source_scope == source_scope) & (cm.evidence_domain == evidence_domain)]
        cm = cm[cm.paper_count >= min_papers].sort_values("evidence_score", ascending=False)
        candidate_cols = ["source_scope", "evidence_domain", "treatment_family", "treatment_signature", "outcome_id", "paper_count",
                          "species_count", "positive_claims", "neutral_claims", "negative_claims",
                          "contradiction_rate", "evidence_score", "confidence", "parameter_ranges",
                          "representative_papers", "doe_role"]
        st.dataframe(cm[candidate_cols], width="stretch", hide_index=True,
                     column_config={"treatment_signature": st.column_config.TextColumn(width="large"),
                                    "parameter_ranges": st.column_config.TextColumn(width="large")})
        st.download_button("⬇ Experiment Candidate Matrix", cm.to_csv(index=False).encode("utf-8"),
                           f"experiment_candidates_{level}.csv", "text/csv")

        st.markdown("#### Trace candidates back to evidence")
        trace_family = st.selectbox("Treatment family", sorted(claims_x.treatment_family.unique()))
        traced = claims_x[(claims_x.treatment_family == trace_family)
                          & (claims_x.source_scope == source_scope)].sort_values(
            ["outcome_id", "paper_id"])
        st.dataframe(traced[["paper_id", "source_scope", "study_role", "evidence_domain",
                             "outcome_id", "direction", "effect_value", "effect_unit",
                             "confidence", "quote_match", "source_location", "source_quote"]],
                     width="stretch", hide_index=True,
                     column_config={"source_quote": st.column_config.TextColumn(width="large")})
        st.download_button("⬇ Evidence claims", claims_x.to_csv(index=False).encode("utf-8"),
                           "knowledge_evidence_claims.csv", "text/csv")

        missing_csv = os.path.join(os.path.dirname(DB_PATH), "..", "inbox", "MISSING_FULL_TEXT.csv")
        if os.path.exists(missing_csv):
            st.markdown("#### Missing source material")
            missing_bytes = open(missing_csv, "rb").read()
            st.download_button("⬇ Missing full text / SI", missing_bytes,
                               "missing_full_text.csv", "text/csv")


with tab_verify:
    st.markdown(f"### {t['ver_h']}")
    st.markdown(f'<p class="llead">{t["ver_n"]}</p>', unsafe_allow_html=True)
    st.info(t["ver_how"])
    if READ_ONLY:
        st.warning(t["ro_banner"])
    _pm_path = os.path.join(os.path.dirname(DB_PATH), "pdf_sources.json")
    pdf_base = {}
    if os.path.exists(_pm_path):
        for k, v in json.load(open(_pm_path, encoding="utf-8")).items():
            if not k.startswith("_"):
                pdf_base[k] = os.path.basename(v)
    scope = st.radio(t["ver_scope"], [t["ver_flagged"], t["ver_all"]], horizontal=True)
    vdf = numeric.copy()
    vdf["verified"] = vdf["verified"].fillna(0).astype(int) if "verified" in vdf.columns else 0
    if scope == t["ver_flagged"]:
        vdf = vdf[(vdf.needs_human == 1) & (vdf.verified == 0)]
    vdf["pdf"] = vdf.paper_id.map(pdf_base).fillna("— (no local PDF)")
    vcols = ["result_id", "paper_id", "pdf", "quantity", "value", "unit", "provenance",
             "needs_human", "verified", "verified_value", "verified_by", "confidence",
             "verified_note", "source_location"]
    vdf = vdf[vcols].copy()
    vdf["verified"] = vdf["verified"].astype(bool)
    if len(vdf) == 0:
        st.success(t["ver_none"])
    elif READ_ONLY:
        st.dataframe(vdf.drop(columns=["result_id"]).rename(
            columns={"pdf": t["ver_pdf"], "source_location": "source (verbatim)"}),
            width="stretch", hide_index=True)
    else:
        st.caption(f"{len(vdf)} rows")
        edited = st.data_editor(
            vdf, width="stretch", hide_index=True, key="verify_editor",
            disabled=["result_id", "paper_id", "pdf", "quantity", "value", "unit", "provenance",
                      "needs_human", "source_location"],
            column_config={
                "pdf": st.column_config.TextColumn(t["ver_pdf"]),
                "verified": st.column_config.CheckboxColumn("✓ verified"),
                "value": st.column_config.NumberColumn("value", format="%.4g"),
                "verified_value": st.column_config.NumberColumn("corrected value", format="%.4g"),
                "confidence": st.column_config.SelectboxColumn(
                    "confidence", options=["High", "Medium", "Low"]),
                "verified_note": st.column_config.TextColumn("note"),
                "source_location": st.column_config.TextColumn("source (verbatim)", width="large"),
            })
        if st.button(t["ver_save"], type="primary"):
            orig = vdf.set_index("result_id")
            ed = edited.set_index("result_id")
            con = sqlite3.connect(DB_PATH)
            n = 0
            for rid in ed.index:
                o, e = orig.loc[rid], ed.loc[rid]
                changed = (bool(o.verified) != bool(e.verified)
                           or (str(o.verified_note) != str(e.verified_note))
                           or (str(o.verified_value) != str(e.verified_value))
                           or (str(o.verified_by) != str(e.verified_by))
                           or (str(o.confidence) != str(e.confidence)))
                if not changed:
                    continue
                con.execute(
                    """UPDATE numeric_results
                       SET verified=?, verified_value=?, verified_by=?, confidence=?, verified_note=?,
                           verified_date=?, needs_human=CASE WHEN ?=1 THEN 0 ELSE needs_human END
                       WHERE result_id=?""",
                    (int(bool(e.verified)), float(e.verified_value) if pd.notna(e.verified_value) else None,
                     None if pd.isna(e.verified_by) else str(e.verified_by),
                     None if pd.isna(e.confidence) else str(e.confidence),
                     None if pd.isna(e.verified_note) else str(e.verified_note), date.today().isoformat(),
                     int(bool(e.verified)), int(rid)))
                n += 1
            con.commit()
            con.close()
            st.success(f"{t['ver_saved']} ({n})")
            st.cache_data.clear()
            st.rerun()


with tab_gaps:
    st.markdown(f"### {t['gaps_h']}")
    st.markdown(f'<p class="llead">{t["gaps_n"]}</p>', unsafe_allow_html=True)
    outc = cats[cats.category.str.startswith("outcome:")].copy()
    outc["outcome"] = outc.category.str.split(":").str[1]
    m = outc.merge(papers[["paper_id", "species"]], on="paper_id")
    if len(m):
        mm = m.groupby(["species", "outcome"]).size().reset_index(name="n")
        heat = (
            alt.Chart(mm).mark_rect().encode(
                x=alt.X("outcome:N", title=None, axis=alt.Axis(labelColor=INK2, labelAngle=-30)),
                y=alt.Y("species:N", title=None, axis=alt.Axis(labelColor=INK2, labelFont="ui-monospace")),
                color=alt.Color("n:Q", scale=alt.Scale(scheme="greens"),
                                legend=alt.Legend(title="papers", labelColor=INK2)),
                tooltip=["species", "outcome", "n"],
            ).properties(height=max(260, 22 * m.species.nunique()))
            .configure_view(strokeWidth=0, fill=SURFACE))
        st.altair_chart(heat, width="stretch")
    st.markdown(f"#### {t['gaps_sensory']}")
    sc = st.columns(4)
    for i, oc in enumerate(["off_flavor", "off_odor", "color", "protein_purity"]):
        n = outc[outc.outcome == oc].paper_id.nunique()
        sc[i].metric(oc, n)


with tab_compare:
    st.markdown(f"### {t['cmp_h']}")
    sel = st.multiselect(t["cmp_pick"], sorted(papers.paper_id), max_selections=4)
    if sel:
        sub = papers[papers.paper_id.isin(sel)].set_index("paper_id")
        st.dataframe(sub[["year_str", "species", "relevance", "verification_level",
                          "extraction_method_family", "purity", "yield"]].T, width="stretch")
        nn = seed_num[seed_num.paper_id.isin(sel)]
        if len(nn):
            piv = nn.pivot_table(index="quantity", columns="paper_id", values="value", aggfunc="first")
            st.dataframe(piv, width="stretch")
    st.divider()
    st.markdown(f"### {t['qry_h']}")
    st.markdown(f'<p class="llead">{t["qry_n"]}</p>', unsafe_allow_html=True)
    qc = st.columns(3)
    qq = qc[0].multiselect(t["norm_pick"], sorted(numeric.quantity.dropna().unique()))
    qs = qc[1].multiselect(t["f_species"], sorted(numeric.species.dropna().unique()))
    qp = qc[2].radio(t["qry_prov"], ["seed+extracted", "seed", "extracted"], horizontal=True)
    qd = numeric.copy()
    if qq:
        qd = qd[qd.quantity.isin(qq)]
    if qs:
        qd = qd[qd.species.isin(qs)]
    if qp == "seed":
        qd = qd[qd.provenance == "seed"]
    elif qp == "extracted":
        qd = qd[qd.provenance.str.startswith("llm:")]
    out = qd[["paper_id", "quantity", "value", "unit", "species", "treatment_condition",
              "provenance", "needs_human", "source_location"]]
    st.caption(f"{len(out)} rows")
    st.dataframe(out, width="stretch", hide_index=True)
    st.download_button(t["qry_dl"], out.to_csv(index=False).encode("utf-8"),
                       "leaf_query.csv", "text/csv")


st.markdown(f'<div class="foot">{t["prov"]} · db/leaf_lit.db · schema v1</div>',
            unsafe_allow_html=True)
