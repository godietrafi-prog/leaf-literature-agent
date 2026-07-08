---
citekey: duckweed_fbt2025
title: "Optimization of Protein Extraction from Duckweed Using Different Extraction Processes"
authors: Maag, D.; Cutroneo, S.; Tedeschi, T.; Gruner-Lempart, P.; Rauh, C.; Ozmutlu Karslioglu, D.
year: 2025
doi: 10.1007/s11947-025-03777-x
source_type: "peer-reviewed, full text obtained (user-provided PDF; two identical-content files confirmed as the same paper - Optimization_of_Protein_Extraction_from_Duckweed_U.pdf and s11947-025-03777-x.pdf - only one citekey/metadata file needed). Food and Bioprocess Technology 18:5510-5531."
system: duckweed (Lemna gibba)
extraction_method_family: "four extraction processes directly compared: conventional (heat/pH) + isoelectric precipitation (IEP); ultrasound-assisted extraction (UAE) + IEP; conventional + ultrafiltration (UF); UAE + UF"
key_parameters: "LG-C = conventional extraction + IEP; LG-US-C = UAE + IEP; LG-UF = conventional + UF (no precipitation); LG-US-UF = UAE + UF; N-to-protein conversion factor for duckweed empirically established at 5.78+/-0.02 (first paper to do this for duckweed specifically, using RuBisCO-analogy to spinach rather than the generic 6.25 factor)"
outcomes:
  protein_purity_pct: "64.54 (LG-C, highest of the 4); 48.59 (LG-US-C); 54.59 (LG-UF); 50.91 (LG-US-UF)"
  yield_pct: "13.60 (LG-C, lowest); 28.90 (LG-US-C); 24.50 (LG-UF); 41.30 (LG-US-UF, highest)"
  chlorophyll_removal_pct: "not given as a removal %, but total chlorophyll (Table 11) reported directly: LG-UF lowest (0.50 mg/g, best decolorization), LG-C also low (0.76 mg/g); ultrasound methods MUCH higher (LG-US-C 20.34 mg/g, LG-US-UF 13.95 mg/g) - ultrasound INCREASES chlorophyll co-extraction rather than reducing it"
  off_flavor_result: "not addressed directly, but color (L*a*b*) reported as a color/appearance proxy: LG-UF lightest/least green (L*=51.67, a*=+3.66, i.e. slightly reddish not green); ultrasound samples much greener (a*=-8.13 for LG-US-C, -13.19 for LG-US-UF)"
  target_protein_specificity: "SDS-PAGE shows conventional IEP/UF methods (LG-C, LG-UF) do NOT extract LHCB1 (light-harvesting chlorophyll a/b-binding protein, ~25 kDa) = better RuBisCO-specificity; ultrasound methods (LG-US-C, LG-US-UF) DO extract LHCB1 = worse RuBisCO-specificity despite their higher yield"
relevance: High
one_line_relevance_note: "the clearest 4-way, single-paper demonstration in this entire review of the yield-vs-purity-vs-chlorophyll-vs-RuBisCO-specificity trade-off via ultrasound: LG-US-UF gives the best yield (41.30%) but the worst chlorophyll co-extraction and the only condition where the chlorophyll-binding protein LHCB1 itself is extracted alongside RuBisCO"
---
**EXPANSION NOTE (2026-07-05):** the earlier metadata for this file recorded only a single data point (50.91% purity / 41.30% yield, the LG-US-UF condition) - accurate but incomplete. Full-text reading confirms the paper actually reports FOUR distinct extraction conditions with a clear, internally consistent trade-off pattern, now captured in full above and should be reflected as 4 separate rows (or one row with all 4 conditions noted) in protocol_matrix.md's ultrasound-assisted table, not just the single highest-yield condition.

**Table 10 (protein/yield) and Table 11 (chlorophyll) - the core dataset:**
| Condition | Purity % | Yield % | Total Chl (mg/g) | L* | a* |
|---|---|---|---|---|---|
| LG-C (conventional + IEP) | 64.54 | 13.60 | 0.76 | - | - |
| LG-US-C (UAE + IEP) | 48.59 | 28.90 | 20.34 | - | -8.13 |
| LG-UF (conventional + UF) | 54.59 | 24.50 | 0.50 | 51.67 | +3.66 |
| LG-US-UF (UAE + UF) | 50.91 | 41.30 | 13.95 | - | -13.19 |

**Interpretation:** within each precipitation-route pair (C vs US-C; UF vs US-UF), adding ultrasound roughly DOUBLES yield (13.60->28.90%; 24.50->41.30%) but costs purity (64.54->48.59%; 54.59->50.91%) AND massively increases chlorophyll co-extraction (0.76->20.34 mg/g; 0.50->13.95 mg/g, i.e. ~27x and ~28x respectively). This is a much larger and more consistent chlorophyll penalty from ultrasound than purity penalty, suggesting ultrasound's main mechanistic cost is disrupting chloroplast/thylakoid membrane structures and releasing bound chlorophyll into solution alongside protein, not simply co-extracting more "generic" non-RuBisCO protein. This is corroborated at the protein-identity level: SDS-PAGE shows LHCB1 (the chlorophyll a/b-binding protein itself, ~25 kDa, structurally analogous to the CBP/LHCB proteins identified as the key pigment-binding culprits in cloverbiorefinery2025's proteomics) is ABSENT from LG-C and LG-UF gels but PRESENT in LG-US-C and LG-US-UF gels - i.e. ultrasound physically breaks open the chloroplast membrane structures that would otherwise keep LHCB1 (and its bound chlorophyll) separate from the soluble RuBisCO fraction during conventional disruption.

**UF vs. IEP (precipitation route) comparison, holding disruption method constant:** UF outperforms IEP on both chlorophyll removal (0.50 vs 0.76 mg/g for conventional; 13.95 vs 20.34 for ultrasound) and lightness/color (only UF conditions reported L*a*b*, with LG-UF being the best of all four on appearance). This is a second, independent confirmation (alongside duckweed_acs2021's own direct rejection of IEP as "insoluble, functionally dead product") that membrane/UF-based separation outperforms isoelectric precipitation for this genus specifically, on both functional and color grounds - reinforcing gaps_and_opportunities.md's #2 recommendation to default to membrane-based routes over precipitation.

**N-to-protein conversion factor finding (methodological, cross-cutting):** this paper is the first identified in this review to empirically derive a duckweed-specific nitrogen-to-protein conversion factor (5.78 +/- 0.02) rather than using the generic Jones factor of 6.25 used by most other papers in this review (including cloverbiorefinery2025, martin2014_spinach, martin2019_sugarbeet). Since a lower conversion factor produces lower apparent "% protein" purity for the same actual nitrogen content, this means duckweed_fbt2025's purity numbers (64.54% etc.) are NOT directly comparable to other papers' purity numbers on a like-for-like basis without adjustment - a caution worth carrying into any cross-species purity comparison table, and a good practice this review's own future carrot-specific work should consider replicating (deriving a carrot-leaf-specific N-to-protein factor via RuBisCO amino acid composition, rather than assuming 6.25 or borrowing another species' factor).
