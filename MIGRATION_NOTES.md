# MIGRATION_NOTES — Leaf Literature Agent v2 knowledge-integration layer

**Date:** 2026-07-18
**Status:** ⏸️ **In working tree, NOT committed / NOT pushed. Awaiting review before merge.**
**Author:** Lead AI Architect (implementation pass following the two accepted reviews)
**Scope of this change:** turn "adding a paper = more rows" into "adding a paper = updated, normalized, validated knowledge," per the converged review findings — while preserving the existing architecture.

> ⚠️ This is a **cross-cutting** change (new modules + edits to `schema.sql`, `harmonize.py`, `extract.py`, `knowledge_engine.py`, `auto_ingest.py`, `dashboard/app.py`). It is intentionally presented for review before any commit. Nothing here has been run through Bedrock — this environment has no `boto3`/AWS creds, so **the real LLM path is unexercised**; everything was validated deterministically with `--mock`. See "Backward compatibility" and "Testing" per file.

---

## 0. TL;DR — what changed and why it matters

| Area | Before | After |
|---|---|---|
| Quantity vocabulary | 1,071 raw strings, 782 singletons; 16% mapped to ontology | canonical families; **~83% (2,557/3,078) rows carry an ontology `outcome_id`** |
| Species | 277 raw strings ("Pisum sativum" ≠ "Pisum sativum L." ≠ "soybean") | **211 canonical entities**, aliases preserved |
| Claim ↔ number | disconnected | **180 claims linked** (118 exact value matches) |
| Adding a paper | append rows + basic harmonize | **full incremental pipeline** that reuses entities and rebuilds derived knowledge |
| Trust state | `verified` bit only | `validation_state` (human/machine/extracted) as a derived column |
| Duplicate drop | new near-duplicate paper row | **deduped → updates the existing paper** |

All derived tables are rebuilt deterministically from the **immutable raw rows**; no raw value is mutated. Provenance is preserved and extended.

---

## 1. Files created (new modules — additive, zero risk to existing code)

### `agent/migrations.py` (NEW)
- **What:** central, idempotent `ensure(conn)` that runs `schema.sql` and adds the guarded `ALTER TABLE … ADD COLUMN` for v2 columns.
- **Why:** `CREATE TABLE IF NOT EXISTS` cannot add columns to existing tables; the repo already used scattered guarded ALTERs (`knowledge_engine.connect`, `harmonize.ensure_schema`, `store_extractions._ensure_provenance_col`). This centralizes them so every v2 module calls one function.
- **Recommendation implemented:** DD §"schema evolution" / Design Spec Part 3 (provenance/audit/validation columns).
- **Backward compatibility:** fully compatible — only *adds* nullable columns and new tables. Existing modules that `executescript(schema.sql)` simply also create the new (empty) tables.
- **Test:** `python3 agent/migrations.py` then `PRAGMA table_info(numeric_results)` shows the new columns; re-run is a no-op.

### `agent/ontology_match.py` (NEW)
- **What:** deterministic, stdlib-only mapping of any raw quantity string → (canonical quantity family, ontology `outcome_id`, canonical unit). Ordered regex rules over the 28-node `ontology_v1.json` outcome tree + unit normalization (µ/μ→u, DW, score scales).
- **Why:** the LLM invents 1,071 distinct quantity names (782 singletons); this is the root cause of "84% identity_only" and unreliable cross-study grouping.
- **Recommendation implemented:** DD "stronger ontology usage / entity normalization"; Codex "reduce quantity fragmentation."
- **Scientific capability:** connects the numeric layer to the same controlled vocabulary the claim layer uses → honest cross-study aggregation by outcome.
- **Design safety:** never guesses — an unrecognized quantity returns `outcome_id=None` (`match_type='unmapped'`), not a wrong bucket.
- **Backward compatibility:** pure function module, imported by `harmonize.py`/`entities.py`/`link_claims.py`; touches no data by itself.
- **Test:** `python3 agent/ontology_match.py` (self-test); measured coverage 16%→**81.7%** of rows mapped across the live DB.

### `agent/entities.py` (NEW)
- **What:** builds `canonical_entities` + `entity_mentions`; resolves `numeric_results.species` (and quantities) to canonical nodes. Deterministic (normalise → alias table → difflib fuzzy fallback ≥0.92). `resolve_new()` is incremental; `rebuild_all()` is a full idempotent rebuild.
- **Why:** the same species is stored under many strings; materials are re-created per claim (1,926 rows / 49 papers).
- **Recommendation implemented:** DD/Codex "entity normalization" (G7 / Design Spec Part 4).
- **Scientific capability:** "Glycine max" now aggregates 40 values that were 5 separate strings; enables valid cross-study means.
- **Backward compatibility:** additive tables + a new `species_entity_id` column (nullable). Raw `species` string is never altered; the mention row keeps it.
- **Test:** `python3 agent/entities.py --rebuild` → 277 raw species → **211 canonical**; consolidation examples printed; `PRAGMA integrity_check = ok`.

### `agent/link_claims.py` (NEW)
- **What:** populates `claim_number_link` and sets `evidence_claims.numeric_result_id` by matching, per paper, a claim's ontology `outcome_id` to a numeric row's ontology-mapped quantity, with value proximity (±1.0 abs or 2% rel) and source-overlap tiebreak.
- **Why:** the two knowledge layers were disconnected — "the numbers behind this DOE factor" was unanswerable.
- **Recommendation implemented:** DD/Codex "claim-number linking" (G2 / Design Spec I-2).
- **Backward compatibility:** additive bridge table + nullable FK column; never links across papers; never mutates values.
- **Test:** `python3 agent/link_claims.py` → **180 linked** (118 `value_outcome` exact, 62 `outcome_only`); sample matches verified (e.g. claim effect 61.0 ↔ `yield_pct` 61.0).

### `agent/integrate_paper.py` (NEW) — the incremental pipeline
- **What:** one command runs the full pipeline for a single paper: register (dedupe-aware) → extract numeric+claims (mock/real) → validate (quote audit + `validation_state`) → normalize (reuse-or-create entities, ontology harmonize) → link claims↔numbers → rebuild candidate matrix → write an `integration_runs` audit row + human summary. Modes: `--pdf`, `--paper-id`, `--inbox [--watch]`, `--reindex`.
- **Why:** the core review vision — dropping one paper should *update the body of knowledge*, not just append rows, without re-extracting the corpus.
- **Incrementality:** only the new paper is extracted (the expensive/billed step). All *derived* tables (harmonized, entities, links, candidate matrix) are recomputed deterministically from the immutable raw layer — fast at this scale (<1 s for 3k rows) and the correct way to propagate updated counts/contradictions/confidence.
- **Backward compatibility:** new module; does not change existing entrypoints' signatures. Uses existing modules (`extract`, `knowledge_engine`, `harmonize`, `auto_ingest`) as libraries.
- **Test:** exercised end-to-end with `--mock`:
  - `--reindex` over the whole corpus → 712 entities, 180 links, 635 candidates, integrity ok.
  - `--paper-id martin2014_spinach --mock` → pipeline runs, derived tables rebuild.
  - `--inbox --mock` with a duplicate PDF → **deduped to existing paper** (corpus stayed 93, mapping preserved).
  - `--inbox --mock` with a synthetic novel PDF → **new paper created** (93→94), then removed to leave the corpus clean.

---

## 2. Files modified

### `db/schema.sql` (MODIFIED — appended a v2 section)
- **What:** added `canonical_entities`, `entity_mentions`, `claim_number_link`, `integration_runs` (all `CREATE TABLE IF NOT EXISTS` + indexes). No existing table definition changed.
- **Why:** persist the new knowledge-integration objects.
- **Backward compatibility:** additive only; every existing `executescript(schema.sql)` caller keeps working and now also creates the (empty) new tables. New *columns* are added by `migrations.py`, not here (CREATE-IF-NOT-EXISTS can't alter existing tables).
- **Test:** covered by every module's run + `PRAGMA integrity_check = ok`.

### `agent/harmonize.py` (MODIFIED)
- **What:** (1) `import migrations, ontology_match`; (2) `ensure_schema` now calls `migrations.ensure`; (3) the unmapped fallback in `harmonize_value` now consults `ontology_match` to attach a real ontology outcome instead of a crude `*:unmapped` bucket, and uses `canonical_unit`; (4) new `write_canonical_columns()` fills `numeric_results.quantity_canonical/outcome_id/unit_canonical`, called at the end of `build()`.
- **Why:** connect the long tail of quantities to the ontology; expose canonical columns for grouping/dashboard.
- **Recommendation implemented:** DD "reduce identity_only / stronger ontology usage."
- **Backward compatibility:** **`harmonize_value`'s return tuple signature is unchanged** (positions relied on by `test_harmonize.py` preserved). Honest semantics kept: no unit conversion is fabricated — non-convertible rows remain `identity_only`; the win is the added `outcome_id` column, not a fake status upgrade. `numeric_results_harmonized` counts unchanged (497 exact / 2,581 identity_only).
- **Test:** `python3 agent/test_harmonize.py` → **4/4 pass**; `python3 agent/harmonize.py` → outcome_id coverage 2,557/3,078.

### `agent/extract.py` (MODIFIED — prompt only)
- **What:** strengthened `SYSTEM_PROMPT`: emit one row per (quantity × treatment_condition) instead of a single "best"; always fill `treatment_condition` + `method`; keep chemical vs sensory separate; record species as Latin binomial; capture SD/SEM/CI/n/p and Table/Figure refs; use an expanded controlled quantity vocabulary. `EXTRACTION_SCHEMA` and function signatures **unchanged**.
- **Why:** raise extraction completeness/consistency and downstream normalizability.
- **Recommendation implemented:** DD/Codex "better extraction prompts, uncertainty capture, granularity, SI handling."
- **Backward compatibility:** prompt text only — no schema/interface change. The regex **mock extractor is untouched**, so the deterministic tests/eval baseline are unaffected.
- **Test:** ⚠️ **Not verifiable here** (needs Bedrock). Recommended before merge: run `agent/eval_extract.py --real --pdf-only` and confirm the release gate (recall≥0.70, value_accuracy≥0.75) still passes and breadth improves. Prompt-hash cache means this re-bills only changed prompts.

### `agent/knowledge_engine.py` (MODIFIED — prompt only)
- **What:** appended two sentences to `system_prompt`: record species as Latin binomial (+cultivar field), and emit one claim per dose/time/temperature condition rather than a summary claim (so dose/order dependence isn't flattened into a false contradiction).
- **Why:** better material normalization + fewer spurious contradictions.
- **Recommendation implemented:** DD "contradiction = often dose/order dependence"; entity normalization.
- **Backward compatibility:** prompt text only; `CLAIM_SCHEMA`, validation, storage all unchanged.
- **Test:** ⚠️ Not verifiable here (needs Bedrock). Deterministic parts (`build-matrix`, `audit-quotes`) re-run clean via `--reindex`.

### `agent/auto_ingest.py` (MODIFIED)
- **What:** `ingest_one` now (1) dedupes by DOI/normalised title via `integrate_paper.find_duplicate` (re-drop updates instead of duplicating), and (2) delegates post-registration work to `integrate_paper.integrate_paper(... mock=True)` — i.e. the inbox watcher now runs the **full** pipeline (entities/harmonize/link/matrix), not just a mock numeric dump. `store_mock_results` retained (still used by `literature_search.py`).
- **Why:** make the existing "drop a PDF" path perform real knowledge integration.
- **Recommendation implemented:** the core incremental-integration vision.
- **Backward compatibility:** the CLI (`--watch/--interval/--no-push`) is unchanged; behavior is a **superset** (more integration per paper). One behavioral change to flag: a re-dropped known paper now **updates** rather than creating a suffixed duplicate — this is the intended fix but is a visible change. Lazy import of `integrate_paper` avoids a circular import.
- **Test:** `python3 agent/auto_ingest.py --no-push` with a duplicate PDF → deduped + full pipeline ran; inbox cleared; PDF mapping preserved.
- **Bug found & fixed during testing:** an earlier version of `integrate_paper.register_pdf` remapped a known paper's `pdf_sources.json` entry to the transient inbox file. Fixed: dropped PDFs are now copied to the durable article store and an existing valid mapping is never clobbered. (During testing this transiently broke `martin2014_spinach`'s mapping and overwrote its 2 rows with mock rows; both were **restored from the start-of-session backup** — see §4.)

### `dashboard/app.py` (MODIFIED — additive sidebar readout)
- **What:** added a defensive "Knowledge integration (v2)" sidebar block showing canonical-entity count, ontology-mapping coverage, linked-claim count, and the validation-state split. Wrapped in try/except and table/column existence checks so it **no-ops on a pre-v2 DB**.
- **Why:** the goal "dashboards automatically represent the updated knowledge." The rest of the dashboard already reflects updates (it reads the rebuilt `numeric_results`/`experiment_candidates`); this surfaces the *new* knowledge objects.
- **Backward compatibility:** additive, defensive; no existing tab/query changed. `ast.parse` clean. A dedicated Entities/Links tab is deliberately deferred (see §5).
- **Test:** ⚠️ not launched (Streamlit) here; `ast.parse` passes and the query is guarded. Recommend a manual `streamlit run` before merge.

---

## 3. New database objects (summary)

**Tables:** `canonical_entities`, `entity_mentions`, `claim_number_link`, `integration_runs`.
**Columns (via `migrations.py`):** `numeric_results.{quantity_canonical, outcome_id, unit_canonical, species_entity_id, validation_state, agreement_score}`; `evidence_claims.{numeric_result_id, outcome_entity_id}`.
All nullable/additive. `agreement_score` and `outcome_entity_id` are **reserved for the next milestone** (self-consistency; not yet populated) — flagged below as intentionally-inert.

---

## 4. Data-integrity notes (important for review)

- The working DB (`db/leaf_lit.db`) has been **enriched in place**: entities resolved, canonical columns filled, claims linked, `validation_state` set. Raw values are unchanged. `PRAGMA integrity_check = ok`. Current counts: 93 papers, 3,078 numeric rows, 820 claims, 635 candidates, 712 entities, 180 links.
- A **backup was taken at session start**: `db/leaf_lit.db.bak_20260718_200138` (plus the pre-existing `.bak_20260716`). Roll back by restoring the backup file.
- One paper (`martin2014_spinach`) was transiently damaged during testing (mock rows + a broken PDF mapping) and **restored from the backup**; `db/pdf_sources.json` was restored via `git checkout`. Verified back to the original 2 rows.
- Synthetic test paper (`kale_novel_2026`) was created to test the new-paper branch and then **fully removed** (paper, rows, mapping, files). Corpus is back to 93.

---

## 5. Known limitations / intentionally deferred (restraint)

1. **Real LLM path untested here** — no `boto3` in this environment. The prompt changes and the `--real` branches of `integrate_paper`/`store_extractions`/`knowledge_engine` compile and are wired, but must be run once with the `py_work` venv before trusting them. **This is the single most important pre-merge check.**
2. **`agreement_score` / self-consistency second pass** — column added, not populated. Deferred (Design Spec M1). No behavior depends on it yet.
3. **Bayesian evidence integration, mechanism graph, experiments/arms model** — **not implemented** on purpose (Design Spec Part 8 restraint: build the trustworthy base first). `experiment_candidates` still uses the existing heuristic scorer.
4. **Ontology coverage ~83%, not 100%** — the remaining tail (TEAA, EPR, niche volatiles) is genuinely ambiguous; left `unmapped` rather than mis-bucketed by design.
5. **Dashboard shows the new stats but has no dedicated Entities/Links tab yet** — deferred to avoid a large change to the 1,460-line app before review.
6. **`numeric_results_normalized` still empty** — unchanged; the ontology mapping went onto `numeric_results.outcome_id` + the harmonized layer instead, which serves grouping without fabricating conversions.

---

## 6. How to review / reproduce

```bash
# deterministic, no Bedrock required:
python3 agent/test_harmonize.py            # 4/4
python3 agent/test_evidence_pipeline.py    # 9/9
python3 agent/ontology_match.py            # self-test
python3 agent/integrate_paper.py --reindex # rebuild derived layers from raw
# integrity
python3 -c "import sqlite3;print(sqlite3.connect('db/leaf_lit.db').execute('PRAGMA integrity_check').fetchone())"

# before merge, WITH the py_work venv (boto3 + AWS):
py_work agent/eval_extract.py --real --pdf-only   # confirm release gate still passes
py_work agent/integrate_paper.py --paper-id <id> --real   # one real end-to-end paper
streamlit run dashboard/app.py                    # visual check of the v2 sidebar
```

## 7. Rollback
Restore `db/leaf_lit.db.bak_20260718_200138`, and `git checkout -- db/schema.sql agent/ dashboard/app.py` (nothing is committed, so `git checkout` reverts all code). The new module files can simply be deleted.

---

## 8. Recommendation to the reviewer
The **normalization + linking + incremental pipeline** (entities, ontology_match, link_claims, integrate_paper) are the high-value, low-risk core and are fully tested deterministically. The **prompt changes** are high-value but need one real Bedrock run to confirm the eval gate. The **new tables** are justified by demonstrated problems (1,071 quantities, 277 species, disconnected layers) and add no reasoning complexity — they are storage for normalization, not speculative machinery. Suggest: review → run the two `--real` checks → then commit/push. No commit or push has been performed.
