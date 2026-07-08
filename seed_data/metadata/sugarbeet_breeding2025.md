---
citekey: sugarbeet_breeding2025
title: "Leaf protein extractability in sugar beet: Genetic control and breeding potential for dual-purpose cultivars"
authors: Rijken, P.J.; Saleem, A.; Hirschmann, F.; Hackenberg, S.; Bruins, M.; Trindade, L.M.
year: "2025/2026 (Field Crops Research, in press/early online)"
doi: 10.1016/j.fcr.2025.110215
source_type: "peer-reviewed, full text obtained (user-provided PDF). Field Crops Research 336:110215."
system: sugar beet (Beta vulgaris), 200 hybrids across 4 field trials
extraction_method_family: "not a single process protocol - GWAS/genetics study of extractability itself as a trait"
key_parameters: "200 sugar beet hybrids, 4 field trials; measured leaf protein content (LPC), extractable LPC (ELPC), extractable RuBisCO as %DM (ER), and protein extractability (PE, the ratio of extractable to total protein)"
outcomes:
  protein_purity_pct: null
  yield_pct: null
  chlorophyll_removal_pct: null
  off_flavor_result: not addressed
  target_protein_specificity: "ER (extractable RuBisCO, % dry matter) is one of the four core traits studied directly"
relevance: Medium
one_line_relevance_note: "not a process protocol - a genetics/breeding paper showing extractability is genetically controlled, heritable, and can be improved by cultivar selection independent of any process-parameter optimization; correctly stays out of the purity/yield frontier table"
---
Full text obtained and read (10 pages). This is a genetics/GWAS study, not a process-protocol paper, and correctly belongs in protocol_matrix.md's "Not yet classifiable / methodology papers" section, not the purity/yield frontier table - confirmed on full read.

**Key correlations between traits:** LPC-ELPC r=0.71, LPC-ER r=0.55, ELPC-ER r=0.39 - i.e. total leaf protein content is a moderately good but imperfect predictor of how much of that protein is actually extractable, and an even weaker predictor of how much RuBisCO specifically ends up extractable. This reinforces this review's recurring finding (also seen in sugarbeet_proteomics_pmc) that "% protein" and "% RuBisCO of that protein" are genuinely separate axes that must be measured independently, not inferred from each other - now shown to be true even at the genetic/varietal level, not just the process-method level.

**Heritability (H²):** LPC 0.65, ELPC 0.48, ER 0.61, PE (protein extractability ratio) only 0.26. High heritability for LPC and ER means breeding selection on these traits should be effective; the low heritability of PE (0.26) suggests the fraction of protein that is extractable is much more environmentally/processing-sensitive than the absolute amounts of protein or RuBisCO present - i.e., cultivar choice matters more for how MUCH RuBisCO is present than for how EASILY it comes out in extraction, which is more a process-design question (consistent with this review's overall framing that process choice is the primary lever, with genetics as a secondary lever).

**GWAS results:** 182 marker-trait associations collapsed into 48 distinct QTLs across the genome. Candidate genes identified: GDU3 (glutamine dumper, amino acid export - associated with LPC/ELPC/ER, i.e. a general nitrogen-partitioning gene affecting multiple protein-related traits at once), CA2 (carbonic anhydrase), NRT1.2 (nitrate transporter), TRXF/TIC20-II (chloroplast protein import machinery - specifically linked to ER/extractable RuBisCO, plausible mechanistically since RuBisCO's large subunit is chloroplast-encoded and its assembly depends on chloroplast import of the small subunit), TBL23/PG (cell wall modification genes - linked specifically to PE/protein extractability, consistent with cell-wall-loosening being the extractability-limiting step, mechanistically parallel to this review's enzyme-assisted extraction findings on radish where xylanase/cellulase cell-wall-degrading enzymes dramatically raised yield), and HPGT1 (plant growth-related gene, linked to leaf yield generally).

**No protein-yield vs. sugar-yield trade-off found:** the paper explicitly tests whether selecting for higher leaf-protein extractability would come at the cost of the crop's primary economic trait (root sugar yield) and finds no negative trade-off - if anything a slight POSITIVE correlation between the two traits across the 200 hybrids tested. This is a favorable finding for any "dual-purpose" breeding program (sugar beet grown for both root sugar AND leaf protein) and, by extension, encouraging for a similar dual-purpose argument for carrot (grown primarily for root, with leaf currently discarded as waste) - though this has NOT been tested on carrot itself in this review.

**Relevance to the cultivar-selection question already flagged in gaps_and_opportunities.md (#8):** this paper's authors explicitly propose that their high-throughput screening method (NIR for total protein content + a simple pressed-juice assay for extractable protein, applied to 25+ plants per plot) is directly transferable to other crops, and the companion paper sugarbeet_rijken2025 (already in this review) explicitly names carrot as a target crop for this transfer. This paper adds the genetic-architecture detail (heritability estimates, candidate genes, no yield trade-off) that strengthens the case for treating cultivar selection as a legitimate, low-cost lever worth raising with the user - not just a hypothesis but now backed by a specific, replicated (4 field trials, 200 hybrids), quantitative heritability estimate.
