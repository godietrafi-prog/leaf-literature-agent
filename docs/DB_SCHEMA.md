# Database Schema — Leaf Literature Agent

**Engine:** SQLite recommended (single portable file in `db/leaf_lit.db`, syncs via OneDrive, no server). Migrate to Postgres only if concurrency/scale demands it.

> **v2 knowledge-integration layer (2026-07-18, pending review).** Additive tables
> `canonical_entities`, `entity_mentions`, `claim_number_link`, `integration_runs`
> and additive columns on `numeric_results`
> (`quantity_canonical`, `outcome_id`, `unit_canonical`, `species_entity_id`,
> `validation_state`, `agreement_score`) and `evidence_claims`
> (`numeric_result_id`, `outcome_entity_id`) turn "more rows" into normalized,
> linked, validated knowledge. See `db/schema.sql`, `agent/migrations.py`, and
> `MIGRATION_NOTES.md` for the full rationale, backward-compatibility analysis,
> and test procedure. Nothing below is removed or repurposed by v2.

## Design principle
Two linked tables are the heart of the whole system, exactly as the owner specified: a **`papers`** table (one row per study, with categorical sorting + summary) and a **`numeric_results`** table (many rows per study, each a single extracted number) **linked by `paper_id`**, so numbers are analyzable as data while staying traceable to their source. Everything else supports these two.

## Tables

### `papers` — one row per study
| column | type | notes |
|---|---|---|
| `paper_id` | TEXT PK | stable citekey, e.g. `duckweed_pmc2023` (matches seed_data naming) |
| `doi` | TEXT | nullable; unique when present |
| `title` | TEXT | |
| `authors` | TEXT | |
| `year` | INTEGER | |
| `venue` | TEXT | journal/preprint server |
| `source_type` | TEXT | peer-reviewed / preprint / patent / thesis |
| `system` | TEXT | species / feedstock (carrot, moringa, duckweed, …) |
| `relevance` | TEXT | High / Medium / Low |
| `verification_level` | TEXT | `abstract` / `full_text` / `full_text+SI` — critical: the parent project learned that abstract-level numbers are provisional |
| `access_status` | TEXT | `open` / `owner_supplied` / `queued` (see `inaccessible_queue`) |
| `si_status` | TEXT | `none` / `fetched` / `queued` / `not_applicable` |
| `scientific_story` | TEXT | concise narrative summary (LLM-generated, human-editable) |
| `key_findings` | TEXT | bullet findings |
| `added_date` | TEXT | ISO date |
| `last_updated` | TEXT | ISO date |
| `llm_cache_key` | TEXT | pointer to cached Bedrock response for auditability |

### `paper_categories` — many-to-many categorical tagging
| column | type | notes |
|---|---|---|
| `paper_id` | TEXT FK → papers | |
| `category` | TEXT | from controlled vocab (below) |
A paper can carry several categories (e.g. `extraction_method:membrane`, `mechanism:LOX`, `outcome:off_odor`).

### `numeric_results` — the linked results table (many rows per paper)
| column | type | notes |
|---|---|---|
| `result_id` | INTEGER PK autoincrement | |
| `paper_id` | TEXT FK → papers | **the index back to the source paper** |
| `quantity` | TEXT | controlled vocab, e.g. `total_C6_aldehydes`, `hexanal_conc`, `protein_purity_pct`, `yield_pct`, `chlorophyll_content`, `LOX_activity`, `sensory_offodor_score`, `color_L`, `color_a`, `color_b` |
| `value` | REAL | the reported central value (mean/point estimate) |
| `unit` | TEXT | as reported (e.g. µg/kg, %, mg/100g, AU) |
| `sd_error` | REAL | reported dispersion (SD / SEM / CI half-width); **nullable** — required for meta-analysis weighting |
| `error_type` | TEXT | what `sd_error` is: `SD` / `SEM` / `CI95` / `range` / `null` |
| `n_replicates` | INTEGER | sample size behind the value; **nullable** — needed to weight/pool studies |
| `p_value` | REAL | reported significance where applicable; nullable |
| `method` | TEXT | GC-MS / PTR-MS / DGMA / colorimeter / sensory / Kjeldahl / assay … |
| `species` | TEXT | |
| `treatment_condition` | TEXT | the process condition this number belongs to (pH, temp, method, etc.) |
| `basis` | TEXT | e.g. dry/wet basis; N-to-protein factor if a protein % |
| `source_location` | TEXT | verbatim quote or table/figure reference — **traceability, non-negotiable** |
| `is_from_SI` | INTEGER | 0/1 — was this pulled from supplementary material |
| `needs_human` | INTEGER | 0/1 — LLM flagged as uncertain / to verify (also set when a value was parsed out of a narrative string) |
| `extracted_date` | TEXT | |

> **Why the uncertainty columns (`sd_error`, `error_type`, `n_replicates`, `p_value`) are in the raw table, added 2026-07-08:** the project's end goal is a *learnable / meta-analysable* matrix. A proper cross-study pool weights each value by its variance and sample size — a point value alone cannot be meta-analysed correctly. Capturing these at extraction time is nearly free; back-filling them across the whole corpus later means re-reading every paper. They are nullable because many papers report only a point value.

### `numeric_results_normalized` — derived, never overwrites raw
| column | type | notes |
|---|---|---|
| `result_id` | INTEGER FK → numeric_results | 1:1 with raw |
| `quantity_std` | TEXT | mapped to controlled quantity |
| `value_std` | REAL | unit-harmonized value |
| `unit_std` | TEXT | canonical unit for that quantity |
| `norm_notes` | TEXT | how it was converted / assumptions |

### Harmonization and analysis layers

`numeric_results_harmonized` stores the canonical quantity, value/unit,
ontology term, conversion formula, mapping version and an explicit status
(`exact`, `converted`, `identity_only`, `not_harmonizable`, `needs_mapping`).
`identity_only` preserves the value/unit without claiming cross-unit equivalence;
analysis-wide columns therefore include quantity + unit + basis. It references the
immutable raw `result_id`; it never replaces `numeric_results.value`.

`treatment_features` parses comparable experimental descriptors such as pH,
temperature, time, oxygen control, sonication and heat treatment. Rule-derived
features remain `parsed_needs_review` until audited.

During the current planning phase, dashboard exports include all rows under the
explicit label `assumed_validated_pending_audit`. This is an inclusion policy,
not a mutation of the historical `verified` flag. The coverage manifest records
that policy with every export.

### `access_queue` — mirrors `inaccessible_queue/` folder
| column | type | notes |
|---|---|---|
| `paper_id` | TEXT | |
| `doi` | TEXT | |
| `missing` | TEXT | `main` / `SI` / `both` |
| `link` | TEXT | direct link for the owner |
| `why_it_matters` | TEXT | |
| `requested_date` | TEXT | |
| `resolved_date` | TEXT | nullable |

### `query_log` — every scheduled search
| column | type | notes |
|---|---|---|
| `run_date` | TEXT | |
| `cluster` | TEXT | topic cluster |
| `query` | TEXT | |
| `n_hits` / `n_new` | INTEGER | |

## Controlled vocabularies (starter — extend as the corpus grows)

**Categories (`category`):**
- `extraction_method:` heat_coagulation | pH_shift_IEP | membrane_UF | ultrasound | PEF | enzymatic | combined
- `mechanism:` LOX | hydroperoxide_lyase | chlorophyll_binding | phenolic_oxidation | Maillard
- `outcome:` off_odor | off_flavor | color | protein_purity | yield | functional_properties | RuBisCO_specificity
- `sensing:` GC_MS | PTR_MS | DGMA | e_nose | e_tongue | colorimeter | sensory_panel
- `analysis:` DOE_RSM | ML | deep_learning | digital_twin | proteomics
- `species:` carrot | moringa | duckweed | alfalfa | sugar_beet | spinach | cassava | nettle | clover_grass | cauliflower | other

**Quantities (`quantity`):** see `numeric_results.quantity` examples above; keep a canonical list so the same physical quantity from different papers lands under one name (the whole point of enabling later cross-study learning).

## Why this shape serves the end goal
The `numeric_results` → `numeric_results_normalized` path is exactly what converts scattered paper numbers into a **matrix a model can learn from** — the bridge back to the parent project. A query like *"give me every reported `total_C6_aldehydes` value with its species, method, and treatment, normalized to µg/kg"* returns a tidy analyzable table, each row traceable to a paper via `paper_id`. That query is the deliverable that makes the corpus learnable rather than just readable.

## Seed ingestion
The 31 files in `seed_data/metadata/` already contain most of these fields in YAML front-matter (`citekey`, `title`, `year`, `doi`, `system`, `extraction_method_family`, `outcomes.{protein_purity_pct,yield_pct,chlorophyll_removal_pct,off_flavor_result,target_protein_specificity}`, `relevance`). The bootstrap script maps that YAML → `papers` + `numeric_results` directly, giving an instant working DB and a schema validated against human-curated records.

**Reality of the seed values (important for the ingester):** the `outcomes.*` fields are *not* clean numbers. They range from a bare float (`protein_purity_pct: 95`) to a number buried in narrative (`"57.6 (chosen/best-balance condition, pH4, 2% conc); purity actually PEAKS higher at pH4.5..."`) to `null (not measured)` / `not addressed`. The ingester therefore: (a) tries to parse a **leading numeric token**; (b) stores the **entire original string** in `source_location` for traceability; (c) sets `needs_human = 1` whenever the value was parsed out of narrative rather than being a clean scalar; (d) writes **no `numeric_results` row** for `null` / "not measured" / "not addressed". `off_flavor_result` and `target_protein_specificity` are largely textual → they feed `key_findings` and `paper_categories`, not `numeric_results` (except a clean RuBisCO-% when present).

**These 31 records double as the extraction gold-standard.** The eval loop (see `SYSTEM_ARCHITECTURE.md §2a`) re-runs the LLM extractor against the source PDFs of the seed papers and scores its output against these hand-curated rows before any new-paper extraction is trusted.
