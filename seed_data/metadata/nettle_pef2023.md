---
citekey: nettle_pef2023
title: "Pulsed electric field assisted extraction of soluble proteins from nettle leaves (Urtica dioica L.): kinetics and optimization using temperature and specific energy"
authors: Kronbauer, M.; Shorstkii, I.; Botelho da Silva, S.; Toepfl, S.; Lammerskitten, A.; Siemer, C.
year: 2023
doi: 10.1039/D3FB00053B
source_type: peer-reviewed, open access (Sustainable Food Technology, RSC, CC BY-NC) - full text obtained
system: nettle (Urtica dioica) leaves, dried and ground (<1mm) or non-ground (1-3mm)
extraction_method_family: PEF (pulsed electric field), fixed field strength 3 kV/cm, varying specific energy and temperature
key_parameters: "CCD/RSM design: temperature 21.7-78.3C, specific energy 5.9-34.1 kJ/kg (factorial range 10-30, axial points extend it); solid:liquid ratio 1:15; extraction time up to 60min, best result at 5min; particle size <1mm vs 1-3mm compared"
outcomes:
  protein_purity_pct: "not measured - this paper reports SOLUBLE PROTEIN YIELD only, not a purified/precipitated concentrate's purity %"
  yield_pct: "best observed 68.6% (78.3C, 20 kJ/kg, 5min, ground <1mm); model-predicted optimum region 70-78C x 10-24 kJ/kg gives >60% in 5 min; validated point 70C/20kJ/kg = 65.1% observed vs 63.0% predicted; control (no PEF) never exceeded 50% even at best temp/time"
  chlorophyll_removal_pct: null (not measured in this paper - see nettle_foods2024 for joint protein+chlorophyll data on nettle)
  off_flavor_result: not addressed
  target_protein_specificity: "targets total soluble protein fraction (RuBisCO-dominant by composition, ~30% of nettle dry mass is protein) - not RuBisCO-specific quantification"
relevance: High
one_line_relevance_note: "quadratic (non-monotonic) relationship confirmed - protein yield RISES with specific energy up to ~20-24 kJ/kg then FALLS above ~25 kJ/kg due to denaturation/aggregation; this is a real optimum to hit, not 'more PEF is always better'"
---
Open access (RSC, CC BY-NC), full text read directly. Key mechanistic/design finding not visible from abstract alone: the relationship between PEF specific energy and protein yield is quadratic, not monotonic - yield increases from 0 up to ~20-24 kJ/kg, then DECREASES above ~25 kJ/kg (RSM equation, ANOVA p<0.01 for the quadratic term), attributed to protein denaturation/aggregation under excessive electric field + heat exposure. This means "more PEF" is not simply better - there is a genuine sweet spot, analogous to the purity-yield trade-off curves seen elsewhere (cauliflower_fbt2026, cassava_scielo) but here it's yield-vs-yield across one parameter's own range, which is a distinct and useful shape for a digital-twin surrogate model to learn (a true interior optimum, not a monotonic frontier). Grinding to <1mm materially helps yield and speeds kinetics vs 1-3mm particles at every condition tested - mechanical particle size reduction and PEF both act on protein accessibility and appear complementary rather than redundant. Important limitation for this project: the paper only measures soluble protein yield (extraction step), not a purified concentrate's purity, color, or off-flavor - PEF here is a first-step tool, not a complete process, and would need pairing with a purification/decolorization step (e.g. membrane filtration per duckweed_acs2021/cloverbiorefinery2025) to address the full target spec set.
