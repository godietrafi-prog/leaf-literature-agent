#!/usr/bin/env python3
"""
extract.py — LLM-assisted extraction of structured results from a paper.

Given a paper's text (main text + parsed SI), produce the DB-shaped record:
categorical tags, a scientific-story summary, key findings, and numeric_results
with units, uncertainty, method, treatment, and a verbatim source_location.

Two backends:
  * real  — Claude on Bedrock via bedrock_client.BedrockClient (needs SDK+creds)
  * mock  — a deterministic, dependency-free baseline extractor that regexes
            "<number>%" figures near quantity keywords out of the text. It is a
            *weak* extractor on purpose: its job is to exercise the eval harness
            (agent/eval_extract.py) end-to-end and give a real, non-cheating
            precision/recall signal to compare future LLM runs against.

The hard rule (the parent review's "7 data-quality corrections"): never invent a
number the source does not state. The prompt instructs the LLM to return null +
needs_human rather than guess; the mock simply reports only what it literally
matched.
"""
from __future__ import annotations

import re

# JSON schema the LLM must fill — aligned to docs/DB_SCHEMA.md.
EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scientific_story": {"type": "string"},
        "key_findings": {"type": "string"},
        "categories": {"type": "array", "items": {"type": "string"}},
        "numeric_results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "quantity": {"type": "string"},
                    "value": {"type": ["number", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "sd_error": {"type": ["number", "null"]},
                    "error_type": {"type": ["string", "null"]},
                    "n_replicates": {"type": ["integer", "null"]},
                    "p_value": {"type": ["number", "null"]},
                    "method": {"type": ["string", "null"]},
                    "species": {"type": ["string", "null"]},
                    "treatment_condition": {"type": ["string", "null"]},
                    "basis": {"type": ["string", "null"]},
                    "source_location": {"type": "string"},
                    "is_from_SI": {"type": "integer"},
                    "needs_human": {"type": "integer"},
                },
                "required": ["quantity", "value", "source_location", "needs_human"],
            },
        },
    },
    "required": ["scientific_story", "key_findings", "categories", "numeric_results"],
}

SYSTEM_PROMPT = """You are a scientific-literature extraction engine for a leaf-protein \
research group studying off-odour/off-flavour/colour and their oxidative (LOX) mechanisms. \
You read a paper (and its supplementary material when provided) and return STRICTLY VALID \
JSON matching the given schema — no prose outside the JSON.

Non-negotiable rules:
1. NEVER invent a number the paper does not report. If a value is implied but not stated, \
set value to null and needs_human to 1.
2. Every numeric result MUST carry a verbatim source_location — a short quote or an explicit \
Table/Figure reference (e.g. "Table 2, row hexanal") — so it is auditable back to the paper.
3. Capture uncertainty when reported: sd_error + error_type (SD/SEM/CI95/range), \
n_replicates, p_value. Leave them null when the paper does not report them; do not guess.
4. Mark is_from_SI=1 for values taken from supplementary material.
5. Set needs_human=1 whenever you are uncertain about a value, unit, or its mapping.

Completeness and granularity (raise recall without inventing):
6. Extract EVERY reported quantitative result relevant to extraction performance, protein \
purity/yield, colour/chlorophyll, VOC/off-flavour (hexanal and other C6/aldehydes, OAV), \
LOX/oxidation markers, functional protein quality, antinutrients and safety. Ignore \
background/literature-review numbers that are not results of THIS paper.
7. Emit ONE row per (quantity × treatment_condition). Do not collapse several conditions \
into one "best" number — a factorial/CCD table yields many rows. Always fill \
treatment_condition (the process condition: pH, temperature, time, method, atmosphere) and \
method (GC-MS / HS-SPME-GC-MS / PTR-MS / colorimeter / sensory panel / Kjeldahl / assay).
8. Keep chemical markers and sensory scores as SEPARATE quantities — never merge a hexanal \
concentration with an off-odour sensory score.
9. Record species as the Latin binomial when the paper gives it (e.g. "Pisum sativum"), \
plus cultivar in treatment_condition or basis if relevant.

Controlled quantity vocabulary — reuse these canonical names whenever they fit, so results \
are comparable across papers (use a clear descriptive snake_case name only when none fit): \
protein_purity_pct, yield_pct, protein_recovery_pct, chlorophyll_removal_pct, \
chlorophyll_content, rubisco_specificity_pct, total_C6_aldehydes, hexanal_conc, \
pentanal_conc, LOX_activity, lipid_oxidation_marker, sensory_offodor_score, \
sensory_offflavor_score, overall_liking_score, green_color_intensity_score, \
color_L, color_a, color_b, total_phenolic_content, antioxidant_capacity, \
protein_solubility_pct, emulsifying_activity_index, foaming_capacity."""


def build_user_prompt(paper_text: str, si_text: str | None = None) -> str:
    parts = ["MAIN TEXT:\n" + paper_text]
    if si_text:
        parts.append("\n\nSUPPLEMENTARY MATERIAL:\n" + si_text)
    parts.append(
        "\n\nExtract the record now as JSON matching the schema. Remember: no fabricated "
        "numbers; null + needs_human=1 when unsure; verbatim source_location for every value."
    )
    return "".join(parts)


def extract_paper(paper_text: str, si_text: str | None = None, *, client=None,
                  mock: bool = False) -> dict:
    """Return the structured extraction dict for one paper."""
    if mock or client is None:
        return _mock_extract(paper_text, si_text)
    user = build_user_prompt(paper_text, si_text)
    return client.complete_json(SYSTEM_PROMPT, user, EXTRACTION_SCHEMA)


# ── mock baseline extractor (no LLM, no deps) ────────────────────────────────
# Maps a keyword seen near a "<num>%" to a controlled quantity.
_QUANTITY_CUES = [
    (("purity", "protein content", "protein purity"), "protein_purity_pct"),
    (("yield", "recovery"), "yield_pct"),
    (("chlorophyll removal", "chlorophyll reduction"), "chlorophyll_removal_pct"),
    (("rubisco",), "rubisco_specificity_pct"),
]
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%")


def _mock_extract(paper_text: str, si_text: str | None = None) -> dict:
    text = (paper_text or "") + ("\n" + si_text if si_text else "")
    low = text.lower()
    results = []
    seen = set()
    for m in _PCT_RE.finditer(text):
        value = float(m.group(1))
        window = low[max(0, m.start() - 60):m.start() + 10]
        quantity = next(
            (q for cues, q in _QUANTITY_CUES if any(c in window for c in cues)), None
        )
        if quantity is None:
            continue
        # keep the single highest value per quantity (matches the seed convention
        # of recording a paper's best reported figure)
        if quantity in seen:
            continue
        seen.add(quantity)
        snippet = text[max(0, m.start() - 40):m.end() + 5].replace("\n", " ").strip()
        results.append({
            "quantity": quantity, "value": value, "unit": "%",
            "sd_error": None, "error_type": None, "n_replicates": None, "p_value": None,
            "method": None, "species": None, "treatment_condition": None, "basis": None,
            "source_location": snippet, "is_from_SI": 0, "needs_human": 1,
        })
    return {
        "cache_key": None, "cached": False,
        "scientific_story": "(mock extractor — no summary)",
        "key_findings": "(mock extractor — regex baseline over provided text)",
        "categories": [],
        "numeric_results": results,
    }
