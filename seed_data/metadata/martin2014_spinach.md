---
citekey: martin2014_spinach
title: "Characterization of Heat-Set Gels from RuBisCO in Comparison to Those from Other Proteins"
authors: Martin, Anneke H.; Nieuwland, Maaike; de Jong, Govardus A.H.
year: 2014
doi: 10.1021/jf502905g
source_type: "peer-reviewed, full text obtained (user-provided PDF; jf502905g.pdf) - J. Agric. Food Chem. 62:10783-10791"
system: spinach
extraction_method_family: chromatography (anion exchange + size exclusion) - lab-scale, functionality-focused, not yield-optimized
key_parameters: "press juice (Angel juicer) with wet PVPP + 0.1% Na-metabisulfite added at collection -> heat 50C/30min under N2 (chlorophyll removal) -> cool 4-6C -> centrifuge 15000g/35min/6-8C -> clarify pH8 (Tris-base+NaOH) -> 0.5um filter -> Q-Sepharose FF anion exchange (1.4L column, 20mM Tris/HCl pH8) -> desalt -> Sephadex G75 size exclusion -> diafiltration/concentration (Amicon 8200, 3kDa membrane) to pH7"
outcomes:
  protein_purity_pct: 95
  yield_pct: 1.0
  chlorophyll_removal_pct: "not quantified (qualitative only via heat step + PVPP; UV 280/340nm absorbance ratio >40 cited as evidence of near-complete polyphenol absence, not chlorophyll per se)"
  off_flavor_result: "not addressed - paper is purely a functional/gelation-property study, no sensory or flavor testing performed"
  target_protein_specificity: "explicit, isolated RuBisCO isolate confirmed by SEC (single narrow peak, Superdex 200, native ~550 kDa multimeric structure) and SDS-PAGE (2 bands at 12.5 and 55.0 kDa = small/large subunits)"
relevance: High
one_line_relevance_note: "highest purity found anywhere in this review (95%, verified via SEC) via anion-exchange+SEC chromatography; yield is genuinely low (1.0%, i.e. 10 g RuBisCO per kg fresh spinach leaf) but higher than the 3% previously recorded in this file's earlier (uncorrected) version, and clearer than the 0.1% figure floated mid-session before full-text verification - CORRECTED, see note below"
---
**DATA-QUALITY CORRECTION (2026-07-05):** This file previously recorded `yield_pct: 3` (citation-level guess, never independently verified). Full-text reading of jf502905g.pdf found the paper's own explicit statement: "Yield of RuBisCO from spinach was 10 g/kg leaf" - i.e. 10 g per 1 kg fresh leaf mass = **1.0% yield**, not 3%. This is now the 4th documented data-quality correction in this review's tracking log (see literature/needed_pdfs.md), following the 3 corrections already logged from the second pass (duckweed_acs2021, cassava_scielo, moringa_optim_unknown).

Full-text details: This paper's primary purpose is NOT process/yield optimization - it is a functional-property (gelation) characterization study that happens to also report purity and yield as methods-section detail. Spinach was chosen specifically because its RuBisCO large-subunit amino acid sequence is identical to sugar beet's (per UniProt cross-check reported in the paper), making it a convenient model system comparable to the companion sugar-beet RuBisCO work by the same TNO group (Martin et al. 2019, martin2019_sugarbeet).

Process (lab-scale, chromatography-based, NOT the same as the simpler heat+UF+diafiltration process later used in martin2019_sugarbeet on sugar beet): juice pressed, chlorophyll removed by a single 50C/30min heat step under nitrogen (to limit oxidation) with PVPP and sodium metabisulfite added at collection to control polyphenol/phenolase activity, then purified via anion-exchange chromatography (Q-Sepharose FF) followed by size-exclusion chromatography (Sephadex G75) - a two-stage chromatographic purification, explicitly the "gold standard" high-purity route but not economically scalable (small column volumes, low throughput). Purity of 95% was measured by SEC showing one narrow, single peak (Fig. 1A) plus SDS-PAGE showing only the two expected RuBisCO subunit bands (12.5 kDa small subunit, 55.0 kDa large subunit) with no other visible protein bands. UV-vis 280/340 nm absorbance ratio >40 cited as evidence of near-complete absence of polyphenols (not a chlorophyll measurement).

Key functional findings (independent of the purity/yield frontier, but relevant to this project's eventual functionality claims for a carrot RuBisCO product): RuBisCO denaturation temperature Td = 64.9C, lower than whey protein isolate (72C) or egg white protein (78C). RuBisCO has an unusually LOW critical gelation concentration (<2.5% protein forms a self-supporting gel) compared to whey/soy/pea/lupine isolates, and reaches very high storage modulus G' (up to 104 kPa at 10% protein) - i.e., RuBisCO is an exceptionally strong gelling agent at low concentration, but the resulting gels are brittle (low critical strain, low fracture strain) due to a coarser microstructure dominated by hydrophobic/hydrogen-bond interactions rather than disulfide bridges. This is a genuine functional advantage that could be marketed independently of the purity/yield trade-off, IF a carrot-derived RuBisCO isolate retains the same native structure.

Companion/benchmark paper: martin2019_sugarbeet (same TNO group, same general approach applied to sugar beet, but using a simpler non-chromatographic process for the actual isolation - only using SEC/SDS-PAGE for analytical characterization, not production).
