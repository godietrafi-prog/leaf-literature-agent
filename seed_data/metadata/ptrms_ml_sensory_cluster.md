---
citekey: ptrms_ml_sensory_cluster
title: "PTR-(To F)-MS + machine learning for sensory/VOC prediction (cluster): Deuscher et al. 2019 (dark chocolate); plant-based milk vs bovine milk VOC profiling"
authors: "Deuscher, V. et al. 2019 (chocolate); plant-based milk study authors unspecified"
year: 2019 (chocolate); unspecified (plant-based milk, PMC11858441)
doi: "chocolate: 10.1002/jms.4317, J. Mass Spectrom.; plant-based milk: PMC11858441"
source_type: "peer-reviewed, found via targeted web search (2026-07-05/06), abstract/summary level - not full text obtained"
system: "dark chocolate (organoleptic classification); plant-based milk vs bovine milk (VOC comparison) - NOT leaf protein"
extraction_method_family: not applicable - SENSING/AI methodology cluster
key_parameters: "PTR-ToF-MS headspace VOC profiling + PLS-DA (Partial Least Squares Discriminant Analysis) for sensory-category classification (chocolate); integrated PTR-ToF-MS + GC-MS approach (plant-based milk)"
outcomes:
  protein_purity_pct: null
  yield_pct: null
  chlorophyll_removal_pct: null
  off_flavor_result: "PTR-ToF-MS + PLS-DA classified dark chocolate into 4 distinct organoleptic (sensory) categories from VOC profile alone, at 97% correct prediction on the test set"
  target_protein_specificity: null
relevance: High
one_line_relevance_note: "proves real-time VOC-profile-to-sensory-category prediction via PTR-MS + multivariate/ML methods is established and highly accurate (97%) in a food system - directly the same shape of problem as predicting leaf-protein off-flavor severity from PTR-MS headspace data"
---
Found via targeted search after the project's owner asked whether adjacent AI/ML literature exists. The chocolate study is the strongest single precedent found for the specific pipeline this project's off-flavor axis would need: real-time, non-destructive VOC headspace measurement (PTR-ToF-MS) feeding directly into a classification/prediction model of a human-perceived sensory category, at high accuracy (97%), with no separate slow chemical identification step required for the prediction itself (though GC-MS-level identification remains useful for understanding WHICH compounds drive the classification). The plant-based-milk-vs-bovine-milk paper is a closer system analogy: plant-based dairy alternatives face a directly comparable "green"/"beany"/off-flavor problem to leaf protein, and this paper demonstrates PTR-ToF-MS + GC-MS jointly profiling that exact class of off-flavor compound. Neither paper uses leaf protein or deep learning specifically (PLS-DA is a classical multivariate method, not a neural network) - the project's proposed contribution would be to use a neural/deep architecture (given a genuinely large enough sample count, see ai_architecture_notes.md) rather than PLS-DA, and to apply it to leaf-protein off-flavor specifically via a real-time liquid-phase precursor signal (DGMA) rather than (or in addition to) headspace VOCs alone.
