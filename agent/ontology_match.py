#!/usr/bin/env python3
"""Deterministic ontology matching for extracted quantities and units.

The LLM numeric extractor invents a huge long tail of quantity names (in the
current DB: 1,071 distinct quantities, 782 of them appearing exactly once). That
fragmentation is why 84% of harmonized rows are `identity_only` and why
cross-study grouping is unreliable. This module maps any raw quantity string to:

  * a CANONICAL QUANTITY family (a stable slug),
  * an ONTOLOGY outcome_id from db/ontology_v1.json (the 28-node tree), so the
    numeric layer connects to the same controlled vocabulary the claim layer uses,
  * a CANONICAL UNIT (µ/μ unified, DW/percent/score scales normalised).

It is fully deterministic and dependency-free (stdlib only) so it runs anywhere,
is auditable, and never fabricates a mapping — an unrecognised quantity returns
`outcome_id=None` with match_type='unmapped' rather than a wrong guess.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY_PATH = ROOT / "db" / "ontology_v1.json"

# Ordered (regex, outcome_id, canonical_quantity) rules — FIRST match wins, so
# put the most specific patterns first. outcome_id must exist in ontology_v1.json.
# canonical_quantity is a stable family slug that collapses synonyms.
_RULES: list[tuple[re.Pattern, str, str]] = [
    # --- volatiles / off-aroma chemistry (the project's core endpoint) ---
    (re.compile(r"total.*c6.*aldehyd", re.I),            "total_c6_aldehydes", "total_c6_aldehydes"),
    (re.compile(r"\bhexanal", re.I),                      "hexanal",            "hexanal_conc"),
    (re.compile(r"pentanal|heptanal|octanal|nonanal|hexenal|octenal|c6.*volatile|green.*volatile|\bglv\b", re.I),
                                                          "aldehydes",          "c6_related_aldehyde_conc"),
    (re.compile(r"aldehyde", re.I),                       "aldehydes",          "aldehyde_conc"),
    (re.compile(r"\boav\b|\broav\b|odou?r.*activity.*value", re.I),"voc",        "odor_activity_value"),
    (re.compile(r"hexanol|nonanol|octanol|pentanol|octen.?3.?ol|furan|ionone|linalool|ketone|\d.?heptanone|\bketone", re.I),
                                                          "voc",                "volatile_marker_conc"),
    (re.compile(r"volatile|\bvoc\b|\bptr\b|\bgc.?ms\b|carbonyl", re.I),"voc",    "volatile_conc"),
    # --- lipid oxidation markers ---
    (re.compile(r"lipoxygenase|\blox\b", re.I),           "lox_activity",       "lox_activity"),
    (re.compile(r"polyphenol.*oxidase|\bppo\b|peroxidase|\bpod\b|lipase|catalase|enzyme.*activit",
                re.I),                                    "chemical_markers",   "enzyme_activity"),
    (re.compile(r"tbars|malondialdehyde|\bmda\b|peroxide.*value|\bpov\b|hpode|\bhode\b|hydroperoxid|conjugated.*diene|lipid.*oxidation|free.*radical|\bepr\b|carbonyl.*content",
                re.I),                                    "lipid_oxidation",    "lipid_oxidation_marker"),
    # --- colour ---
    (re.compile(r"chlorophyll.*(removal|reduction|loss)", re.I), "chlorophyll_content", "chlorophyll_removal_pct"),
    (re.compile(r"chlorophyll", re.I),                    "chlorophyll_content","chlorophyll_content"),
    (re.compile(r"\bcolou?r_?l\b|\bl\*|lightness|cie.*l", re.I), "colour_coordinates", "color_L"),
    (re.compile(r"\bcolou?r_?a\b|\ba\*|redness|cie.*a", re.I),   "colour_coordinates", "color_a"),
    (re.compile(r"\bcolou?r_?b\b|\bb\*|yellowness|cie.*b", re.I),"colour_coordinates", "color_b"),
    (re.compile(r"chroma|hue|whiteness|browning.*index|total.*colou?r.*diff|delta.*e", re.I),
                                                          "colour_coordinates", "color_metric"),
    (re.compile(r"(green|brown|colou?r).*(intensity|score|appearance)|colou?r.*(liking|acceptab)", re.I),
                                                          "colour_quality",     "sensory_color_score"),
    # --- sensory (keep chemical and sensory strictly separate) ---
    (re.compile(r"off.?odou?r|off.?smell", re.I),         "off_odor",           "sensory_offodor_score"),
    (re.compile(r"off.?flavou?r|off.?taste|bitter|astringen", re.I), "off_flavor", "sensory_offflavor_score"),
    (re.compile(r"beany|bean.?like", re.I),               "beany_aroma",        "sensory_beany_score"),
    (re.compile(r"green.*(aroma|note|odou?r|grassy)|grassy", re.I), "green_aroma", "sensory_green_aroma_score"),
    (re.compile(r"overall.*(liking|acceptab|accept)|hedonic|consumer.*accept|overall.*quality.*score|palatab",
                re.I),                                    "sensory_quality",    "overall_liking_score"),
    (re.compile(r"sensor|organolept|\bqda\b|flavou?r.*score|aroma.*score|taste.*score|odou?r.*score",
                re.I),                                    "sensory_quality",    "sensory_score"),
    # --- functional protein quality ---
    (re.compile(r"solubilit", re.I),                      "protein_solubility", "protein_solubility_pct"),
    (re.compile(r"emulsif|emulsion|\beai\b|\besi\b|droplet|dilatational|coacervat|encapsulat", re.I),
                                                          "emulsification",     "emulsifying_index"),
    (re.compile(r"foam", re.I),                           "foaming",            "foaming_capacity"),
    (re.compile(r"\bgel|gelation|gel.*strength|storage.*modulus|\bg'\b", re.I), "gelation", "gelation_metric"),
    (re.compile(r"water.*(holding|absorption)|oil.*(holding|absorption)|\bwhc\b|\bohc\b", re.I),
                                                          "functional_quality", "holding_capacity"),
    (re.compile(r"hydrophobic|zeta.*potential|particle.*size|droplet.*size|\bd\[?4.?3|interfacial.*tension|\bdsc\b|denatur|secondary.*structure|alpha.*helix|beta.*sheet|thermal.*(stability|transition)|melting.*temp|fluorescence",
                re.I),                                    "protein_damage",     "protein_structure_metric"),
    (re.compile(r"tensile|elongation|young.*modulus|mechanical|puncture|firmness|texture|hardness|cooking.*loss|viscosit|conductivit|\bwhc\b|turns.*fraction",
                re.I),                                    "functional_quality", "mechanical_metric"),
    # --- process performance ---
    (re.compile(r"rubisco", re.I),                        "rubisco_specificity","rubisco_specificity_pct"),
    (re.compile(r"purity|protein.*(content|concentration)|protein.*isolate.*content", re.I),
                                                          "protein_purity",     "protein_purity_pct"),
    (re.compile(r"yield|recovery|extractab|protein.*extract|extract.*(efficiency|rate|yield)|nitrogen.*retain",
                re.I),                                    "protein_recovery",   "yield_pct"),
    # --- chemical markers / composition / antinutrients ---
    (re.compile(r"phenol|polyphenol|\btpc\b|flavonoid|tannin.*content", re.I), "phenolic_content", "total_phenolic_content"),
    (re.compile(r"antioxidant|\babts\b|\bdpph\b|\bfrap\b|radical.*scaveng|reducing.*power", re.I),
                                                          "chemical_markers",   "antioxidant_capacity"),
    (re.compile(r"trypsin.*inhibitor|antinutri|phytate|phytic|oxalate|saponin|lectin|tannin",
                re.I),                                    "safety_antinutrients","antinutrient_content"),
    (re.compile(r"diaas|pdcaas|amino.*acid|essential.*amino|\bteaa\b|lysine|methionine|tryptophan.*content|protein.*digestib|allergenic",
                re.I),                                    "safety_antinutrients","protein_nutritional_quality"),
    (re.compile(r"metal.*chelat|chelat|sulfhydryl|thiol|free.*sulph", re.I),
                                                          "chemical_markers",   "reactive_group_content"),
    (re.compile(r"crude.*protein|total.*protein|nitrogen.*content|\bnfe\b", re.I), "protein_purity", "crude_protein_pct"),
    (re.compile(r"moisture|\bash\b|crude.*fib|dietary.*fib|crude.*fat|ether.*extract|fat.*content|lipid.*content|\bffa\b|\btag\b|\bpl\b|tocopherol|"
                r"dry.*matter|carbohydrate|\bstarch|calcium|\bca.*content|iron|\bfe.*content|zinc|potassium|magnesium|mineral|proximate|energy.*content|"
                r"glycemic|bioaccess|digestib|residual.*lipid|oil.*index|conversion.*factor",
                re.I),                                    "chemical_markers",   "proximate_composition"),
]

_UNIT_ALIASES = {
    "percent": "%", "pct": "%", "%": "%",
    "ppb": "ppb", "ppbv": "ppbv", "ppm": "ppm",
    "fold": "fold", "count": "count", "dimensionless": "dimensionless",
    "au": "AU", "u/g": "U/g", "u/ml": "U/mL",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


def load_outcome_ids() -> set[str]:
    ont = json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    return {o["id"] for o in ont["outcomes"]}


_VALID_OUTCOMES = None


def match_quantity(raw_quantity: str) -> dict:
    """Map a raw quantity string to canonical family + ontology outcome_id.

    Returns {quantity_canonical, outcome_id, match_type}. match_type is one of
    'exact' (already a canonical family), 'pattern' (matched a rule), or
    'unmapped' (no confident match — outcome_id is None, never guessed).
    """
    global _VALID_OUTCOMES
    if _VALID_OUTCOMES is None:
        _VALID_OUTCOMES = load_outcome_ids()
    raw = (raw_quantity or "").strip()
    if not raw:
        return {"quantity_canonical": None, "outcome_id": None, "match_type": "unmapped"}
    # Match against an underscore-normalised form so `\bword\b` patterns fire on
    # slug-style names (ash_content, lox_activity, DSC_first_peak) where `_` would
    # otherwise count as a word character and defeat the boundary.
    norm = re.sub(r"_+", " ", raw.lower())
    for pattern, outcome_id, canonical in _RULES:
        if pattern.search(norm) or pattern.search(raw):
            oid = outcome_id if outcome_id in _VALID_OUTCOMES else None
            match_type = "exact" if _slug(raw) == canonical else "pattern"
            return {"quantity_canonical": canonical, "outcome_id": oid, "match_type": match_type}
    return {"quantity_canonical": _slug(raw), "outcome_id": None, "match_type": "unmapped"}


def canonical_unit(unit: str | None) -> str | None:
    """Normalise a unit string: unify micro sign, drop whitespace, alias common
    forms, and standardise dry-weight notation. Never converts magnitude."""
    if not unit:
        return None
    u = unit.strip()
    u = u.replace("µ", "u").replace("μ", "u")            # both micro signs -> u
    u = re.sub(r"\bdry\s*weight\b", "DW", u, flags=re.I)
    u = re.sub(r"\bdry\s*matter\b", "DW", u, flags=re.I)
    u = re.sub(r"\s+", " ", u).strip()
    key = u.lower().replace(" ", "")
    if key in _UNIT_ALIASES:
        return _UNIT_ALIASES[key]
    # collapse "score (1-9 scale)" / "9-point hedonic scale" family
    if re.search(r"scale|hedonic|point|score", u, re.I):
        m = re.search(r"(\d+)\s*[-–]\s*(\d+)|(\d+)\s*[- ]?point", u)
        if m:
            lo, hi, pts = m.groups()
            span = f"{lo}-{hi}" if lo else f"1-{pts}"
            return f"score_{span}"
        return "score"
    return u


if __name__ == "__main__":
    # quick self-test against a spread of real DB quantities
    samples = ["yield_pct", "protein_purity_pct", "sensory_offodor_score", "LOX_activity",
               "hexanal_conc", "total_C6_aldehydes", "zeta_potential", "green_color_intensity_score",
               "DIAAS", "trypsin_inhibitor_activity", "color_L", "overall_liking_score",
               "some_weird_unseen_metric_xyz"]
    for q in samples:
        print(f"{q:38s} -> {match_quantity(q)}")
    for u in ["µg/g DW", "μg/kg", "score (1-9 scale)", "9-point hedonic scale", "%", "mg/mL"]:
        print(f"unit {u!r:24s} -> {canonical_unit(u)!r}")
