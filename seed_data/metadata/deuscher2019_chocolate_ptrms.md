---
citekey: deuscher2019_chocolate_ptrms
title: "Volatile compounds profiling by using proton transfer reaction-time of flight-mass spectrometry (PTR-ToF-MS). The case study of dark chocolates organoleptic differences"
authors: "Deuscher, Z.; Andriot, I.; Sémon, E.; Repoux, M.; Preys, S.; Roger, J.-M.; Boulanger, R.; Labouré, H.; Le Quéré, J.-L."
year: 2019
venue: "Journal of Mass Spectrometry 54:92-119"
doi: "10.1002/jms.4317"
source_type: "peer-reviewed; owner-supplied full text + supplementary figures verified 2026-07-12"
si_status: fetched
system: "206 dark-chocolate samples assigned by sensory evaluation to four organoleptic categories; NOT leaf protein"
extraction_method_family: "not applicable - PTR-ToF-MS sensing + chemometric classification (PLS-DA/PLS-LDA and CovSel feature selection)"
key_parameters: "PTR-ToF-MS headspace fingerprints; 143 retained ions; 144-sample calibration set; independent 62-sample test set; PLS-DA/PLS-LDA; 10 repeated two-fold cross-validations for tuning; CovSel feature selection"
outcomes:
  protein_purity_pct: null
  yield_pct: null
  chlorophyll_removal_pct: null
  off_flavor_result: "Full 143-ion model correctly assigned 60/62 independent test samples (96.8%, reported as nearly 97%) to four sensory poles. A 22-ion selected model correctly assigned 56/62 (90.3%); a 10-ion CovSel model correctly assigned 57/62 (91.9%)."
  target_protein_specificity: null
numeric_results:
  - quantity: sensory_classification_accuracy
    value: 96.7742
    unit: "%"
    n_replicates: 62
    method: "PTR-ToF-MS + PLS-DA/PLS-LDA"
    treatment_condition: "full 143-ion model; independent test set"
    source_location: "Table 2: confusion matrix totals 60 correct of 62 test samples; text reports nearly 97%"
  - quantity: sensory_classification_accuracy
    value: 90.3226
    unit: "%"
    n_replicates: 62
    method: "PTR-ToF-MS + PLS-DA/PLS-LDA"
    treatment_condition: "22 ions selected by joint VIP/coefficient method"
    source_location: "Table 5: confusion matrix totals 56 correct of 62 test samples"
  - quantity: sensory_classification_accuracy
    value: 91.9355
    unit: "%"
    n_replicates: 62
    method: "PTR-ToF-MS + CovSel + LDA"
    treatment_condition: "10 CovSel-selected ions"
    source_location: "Table 6: confusion matrix totals 57 correct of 62 test samples"
relevance: High
one_line_relevance_note: "Strong transfer precedent for supervised mapping of PTR-ToF-MS VOC fingerprints to sensory categories, but it is classical chemometrics on chocolate, not deep learning, leaf protein, off-flavor severity regression, or continuous real-time process monitoring."
---
Full text and the three-page Supporting Information were checked directly. The four sensory categories were established from quantitative descriptive analysis of 36 flavour descriptors. Each chocolate was prepared in triplicate; 1 g chocolate plus 1 mL artificial saliva was equilibrated under stirring at 36.2 C for 2 h. PTR-ToF-MS acquisition then took 5 min per vial and the setup allowed successive samples every 10 min. Calling the demonstrated workflow "real-time prediction" is therefore misleading despite the fast direct-injection measurement.

The final matrix used the triplicate means for 206 samples and 143 retained ions. The supervised model used 144 calibration samples and a genuinely held-out 62-sample test set. The full model misclassified two samples (Table 2: 60/62 = 96.8%). Feature-selection experiments retained useful performance with fewer predictors: Table 5 gives 56/62 correct with 22 VIP/coefficient-selected ions, and Table 6 gives 57/62 correct with 10 CovSel-selected ions. The supplementary file contains only Figures S1-S2 (sensory-PCA and PLS-DA loading plots); it adds graphical interpretation but no additional numeric table.

Data-quality boundaries: the category labels are sensory poles, not a scalar off-flavor score; the study does not involve leaf protein; PLS-DA/PLS-LDA and CovSel are chemometric/statistical learning methods rather than neural or deep learning. Tentative ion identities remain uncertain where isomers or fragments share a formula.
