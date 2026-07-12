---
citekey: corvino2025_plant_milk_ptrms
title: "Rapid Profiling of Volatile Organic Compounds Associated with Plant-Based Milks Versus Bovine Milk Using an Integrated PTR-ToF-MS and GC-MS Approach"
authors: "Corvino, A.; Khomenko, I.; Betta, E.; Brigante, F. I.; Bontempo, L.; Biasioli, F.; Capozzi, V."
year: 2025
venue: "Molecules 30(4):761"
doi: "10.3390/molecules30040761"
source_type: "peer-reviewed open-access; owner-supplied full text verified 2026-07-12"
si_status: queued
system: "commercial almond, soy and oat beverages compared with bovine milk; NOT leaf protein"
extraction_method_family: "not applicable - PTR-ToF-MS VOC profiling complemented by HS-SPME-GC-MS identification; PCA/ANOVA/Fisher post-hoc analysis, no supervised sensory-prediction model"
key_parameters: "3 mL beverage headspace; PTR-ToF-MS; 269 extracted peaks; 188 retained after blank ANOVA and removal of clusters/isotopes; 118 formula assignments; 48 tentative PTR identifications; 50 compounds identified by GC-MS; PCA"
outcomes:
  protein_purity_pct: null
  yield_pct: null
  chlorophyll_removal_pct: null
  off_flavor_result: "The study distinguished beverage VOC profiles but did not collect sensory labels or train an ML prediction model. Table 1 reports ppbv means, dispersion and ANOVA/post-hoc results for VOCs including hexanal and 2-pentyl furan."
  target_protein_specificity: null
numeric_results:
  - quantity: hexanal_conc
    value: 1.84
    unit: ppbv
    sd_error: 0.48
    error_type: SD
    p_value: 7.35e-11
    method: PTR-ToF-MS
    treatment_condition: "commercial almond beverage"
    source_location: "Table 1, m/z 101.09, tentative identification hexanal; Fisher group a"
  - quantity: hexanal_conc
    value: 0.43
    unit: ppbv
    sd_error: 0.09
    error_type: SD
    p_value: 7.35e-11
    method: PTR-ToF-MS
    treatment_condition: "commercial soy beverage"
    source_location: "Table 1, m/z 101.09, tentative identification hexanal; Fisher group b"
  - quantity: hexanal_conc
    value: 0.14
    unit: ppbv
    sd_error: 0.03
    error_type: SD
    p_value: 7.35e-11
    method: PTR-ToF-MS
    treatment_condition: "commercial oat beverage"
    source_location: "Table 1, m/z 101.09, tentative identification hexanal; Fisher group b"
  - quantity: hexanal_conc
    value: 0.04
    unit: ppbv
    sd_error: 0.03
    error_type: SD
    p_value: 7.35e-11
    method: PTR-ToF-MS
    treatment_condition: "commercial bovine milk"
    source_location: "Table 1, m/z 101.09, tentative identification hexanal; Fisher group c"
relevance: Medium
one_line_relevance_note: "Useful plant-beverage VOC and off-flavor-chemistry transfer evidence, including numeric PTR-ToF-MS concentrations, but not an AI/ML experiment and not evidence of sensory prediction."
---
Full text verified. PTR-ToF-MS detected 269 mass peaks and retained 188 after comparison with blanks; 118 received sum-formula assignments and 48 were tentatively identified. Complementary HS-SPME-GC-MS identified 50 compounds. PCA separated bovine milk from the plant beverages and described compositional patterns, but the paper contains no sensory panel labels, train/test split, supervised classifier, or prediction accuracy. It must not be counted as an AI/ML paper.

Table 1 is a high-value numeric source because it reports concentration (ppbv), dispersion, p-values and Fisher post-hoc group letters across almond, soy, oat and bovine milk. For example, the tentatively identified hexanal ion m/z 101.09 was 1.84 +/- 0.48 ppbv in almond, 0.43 +/- 0.09 in soy, 0.14 +/- 0.03 in oat and 0.04 +/- 0.03 in bovine milk (p = 7.35e-11). These are VOC-profile measurements, not measured sensory intensities. The paper discusses literature linking hexanal and 2-pentyl furan with green/beany off-flavours, but explicitly recommends future work to examine sensory impacts.

The paper points to a supplementary Table S1 containing all 188 retained peaks. That SI was not among the three files supplied on 2026-07-12 and remains worth fetching because it is likely the largest machine-readable numeric payload associated with this study.
