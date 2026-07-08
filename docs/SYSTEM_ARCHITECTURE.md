# System Architecture — Leaf Literature Agent

**Status:** proposed design, for the build session to implement/adjust. Nothing here is built yet.

## 1. The daily loop (top level)

```
        ┌──────────────────────────────────────────────────────────────┐
        │  SCHEDULER (cron / task scheduler)  — daily (interval TBD)     │
        └───────────────┬──────────────────────────────────────────────┘
                        v
   (1) SEARCH ──> (2) DEDUPE ──> (3) TRIAGE ──> (4) ACQUIRE ──> (5) EXTRACT ──> (6) STORE ──> (7) NOTIFY
        │              │             │              │(main+SI)      │(LLM/Bedrock)  │(DB)          │
        │              │             │              │               │              │              v
        │              │             │              └── can't get?──┴──────────────┴──> INACCESSIBLE_QUEUE
        │              │             │                                                   (owner fills)
        └──────────────┴─────────────┴───────────────────────────────────────────────> DASHBOARD reads DB
```

The owner-supplied papers (from the inaccessible queue) re-enter the pipeline at stage (5) EXTRACT when dropped in.

## 2. Stage-by-stage

**(1) Search.** Query scholarly sources on the focus topics. Sources to consider (build session picks the mix by what has usable APIs/access): PubMed/Europe PMC (E-utilities — free API, good for biomed), Crossref (metadata/DOIs, free), Semantic Scholar API (free tier, good for topic search + citations), OpenAlex (free, excellent for topic + open-access status), bioRxiv/chemRxiv (preprints), and general web search as a fallback. Maintain a **query set** driven by the parent project's topic clusters: leaf protein extraction; off-odor/off-flavor removal; green-color/chlorophyll removal; and the mechanistic core — LOX / lipoxygenase / hydroperoxide lyase / green-leaf-volatile / hexanal-hexenal formation / dissolved-O2 kinetics of disruption. Log every query with date (mirror the parent project's `query_log.md` discipline).

> **Search strategy — start with citation-snowball, not broad keywords (added 2026-07-08).** Bare keyword search on "LOX" / "leaf protein" pulls enormous noise (LOX in oncology/immunology, "leaf" in unrelated botany). The **31 seed papers are a known-good nucleus** — expand outward through the citation graph first: their references (backward) and their citers (forward) via OpenAlex / Semantic Scholar. Signal-to-noise is far higher because every candidate is already one hop from a paper a human judged relevant. Broad keyword search becomes a *second* layer, run through the same triage, once the snowball is exhausted. Track for each candidate *how it was found* (`discovery = snowball_ref | snowball_cite | keyword | owner`) so precision per channel can be measured and the noisy channels down-weighted.

> **Boundary vs. the existing `lit-review` skill (added 2026-07-08).** The workspace already has a `lit-review` skill (`Analysis_Workspace/.claude/skills/lit-review`) for *human-driven, one-off* review passes. This agent is the *continuous, autonomous* infrastructure. They must not duplicate: the agent reuses the skill's source list, query clusters, and relevance rubric rather than reinventing them, and the skill can read this agent's DB as its backing store. Decide the shared layer explicitly in the build session — do not fork the search logic.

**(2) Dedupe.** Match new hits against the existing DB by DOI first, then by normalized title + first author + year. Never re-process a paper already in the DB (but do allow re-visiting to fetch SI or upgrade an abstract-level record to full-text — track a `verification_level` field, see schema).

**(3) Triage.** Score relevance High/Medium/Low against the focus (the parent project used exactly this). Only Medium+ proceeds to acquisition. The LLM (Bedrock) can do this scoring from title+abstract; keep a cheap rule-based pre-filter (keyword match) before spending an LLM call.

**(4) Acquire — main text AND supplementary.** Resolve the DOI; prefer open-access (OpenAlex/unpaywall flags OA location). Fetch the full text where legally accessible. **Then explicitly attempt the supplementary material** — SI often holds the numeric data tables the whole project cares about. If either the main text or the SI can't be obtained, write a record to `inaccessible_queue/` (title, DOI, what's missing: `main` / `SI` / `both`, direct link, one line on why it matters) and notify the owner. Never bypass paywalls or use pirate mirrors — the owner supplies gated papers via their institutional access (this rule is inherited from the parent project).

**(5) Extract — the LLM-assisted core (Bedrock).** For each acquired paper this stage produces: (a) categorical tags, (b) a concise scientific-story summary, (c) the findings, (d) **numeric results** with their units and experimental context. This is where an LLM call to **AWS Bedrock** does the heavy reading. Design notes:
  - Feed the LLM the main text + parsed SI tables; ask for a **structured JSON** output matching the DB schema (not free prose) so it drops straight into the DB.
  - Ask it to return, per numeric result: value, unit, what was measured, the treatment/condition it belongs to, the method (GC-MS / PTR-MS / DGMA / colorimeter / sensory / assay), and a verbatim quote or table-cell reference for traceability.
  - Instruct it to **flag uncertainty** and to return `null` + a `needs_human` flag rather than guessing — the parent project's hard-won rule after 7 data-quality corrections. Every extracted number should be auditable back to a location in the paper.
  - Keep the raw LLM response cached (like the parent MetaFlow project's `rescue_cache.db`) so re-runs don't re-bill Bedrock for the same paper.

**(2a) Extraction eval — the guardrail before trusting the LLM (added 2026-07-08).** The single biggest risk in this whole system is silent extraction error: an LLM confidently pulling a wrong number out of an SI table, which then pollutes the "learnable matrix" downstream. Before the extractor is trusted on new papers, and re-run whenever the prompt or model changes, it must be **scored against a gold standard**. We already have one: the **31 hand-curated seed records** (built by a human over multiple correction passes — see the 7 documented data-quality corrections). The eval harness re-runs stage (5) on the seed papers' source PDFs and compares the extractor's `numeric_results` to the seed rows:
  - **Recall** — did it find the numbers the human recorded?  **Precision** — did it invent numbers the human did not?  **Value accuracy** — for matched quantities, is the number right (within tolerance) and the unit/basis correct?
  - Track these metrics over time in a small `eval_runs` table/log. Set a **release gate**: no new-paper extraction is trusted (promoted past `needs_human`) until precision/recall clear a threshold the owner sets.
  - This is the operational form of the parent project's hard-won rule — *the LLM must never fabricate a number the paper does not report.* The eval measures exactly that failure mode instead of hoping it doesn't happen.

**(6) Store.** Write to the DB (see `DB_SCHEMA.md`): the `papers` record, its category tags, and each numeric result as a row in `numeric_results` linked by `paper_id`. Parsed SI tables stored too. Writes are **transactional per paper** (all-or-nothing) so a crash mid-run never leaves a half-ingested paper; the loop is resumable and idempotent (re-running skips papers already at their target `verification_level`).

**(7) Notify.** Daily digest to the owner: N new papers added, top new findings, and — importantly — the current `inaccessible_queue` (what to go fetch). Channel TBD (email / file / WhatsApp — note the owner already has a WhatsApp scheduler in the workspace that could be reused).

## 3. Normalization layer (toward learnable data)

A separate step (can run less often than daily) reads `numeric_results` and attempts to **normalize across studies** so numbers become comparable/analyzable:
- Unit harmonization (e.g., all aldehyde concentrations to µg/kg; all "protein %" to a stated dry/wet basis; record the N-to-protein factor used since it varies — the parent review found 5.4 / 5.8 / 6.25 across papers).
- Map each result to a controlled vocabulary of **measured quantities** (e.g., `hexanal_concentration`, `total_C6_aldehydes`, `chlorophyll_content`, `protein_purity_pct`, `sensory_offodor_score`, `LOX_activity`) and **method** and **matrix/species**.
- Flag which quantities have enough cross-study coverage to support later learning/meta-analysis (this is the bridge back to the parent project's modeling).
- Store normalized values in a view/table alongside the raw, never overwriting the raw source value.

## 4. Dashboard + smart chart generator

Reads the DB (read-only). Two modes:
- **Corpus view:** browse/filter the `papers` table by category, species, method, year, relevance, verification level; see coverage of each measured quantity.
- **Paper view:** click a paper → pull its `numeric_results` → **auto-select a chart**. Heuristic for "smart" chart choice: one numeric series across conditions → bar chart; two numerics → scatter; a time-series (e.g., DGMA/kinetic) → line; a distribution/replicates → box/violin; a composition (e.g., VOC class %) → stacked bar/donut; a cross-study comparison of the same quantity → forest-style dot plot. The chart-type decision can itself be a small rule engine, optionally LLM-assisted for ambiguous cases. (Reuse the parent workspace's `dataviz` skill conventions for palette/accessibility.)

Implementation options for the build session: Streamlit (fastest, matches the owner's existing dashboards) or a single self-contained HTML artifact. Streamlit recommended given the interactivity + DB access.

## 5. Components & suggested stack (build session decides)

| Component | Suggested |
|---|---|
| Scheduler | **run-on-demand + catch-up** (not a true daemon) — see §8 |
| Search APIs | OpenAlex + Europe PMC + Crossref + Semantic Scholar (all free); web fallback |
| OA detection | OpenAlex / Unpaywall |
| PDF + SI parsing | `pymupdf`/`pdfplumber` for text+tables; `grobid` optional for structure |
| LLM extraction | AWS Bedrock (owner's account) via `boto3`; cache responses |
| DB | SQLite (portable, single file, syncs — see schema); upgrade to Postgres only if needed |
| Normalization | pandas |
| Dashboard | Streamlit |
| Notify | reuse WhatsApp scheduler / email |

## 6. Sync / portability note (important for this workspace)
Per the workspace rule, **`.py` files do not sync via OneDrive** — the agent code must be zipped for transport between machines (the parent project uses a `setup_session.bat` extract pattern). The **DB (SQLite `.db`) and data files DO sync**. Plan the repo so code lives in `agent/` (zipped for transport) while the DB in `db/` and queue in `inaccessible_queue/` sync natively.

## 7. Seed & bootstrap
The build session should **ingest `seed_data/metadata/` first** (31 hand-built records from the parent review). This (a) bootstraps the DB with real content, (b) validates the schema against records a human already judged correct, and (c) gives the dashboard something to show on day one. Those files also serve as the **gold-standard example** of the extraction output the LLM stage should reproduce.

## 8. Scheduling model — run-on-demand + catch-up (revised 2026-07-08)
A true "daily autonomous daemon" is a poor fit for this environment: WSL/Windows are not always on, the owner works across **multiple machines**, and OneDrive syncs data but not `.py` code. A cron job that only fires when one specific machine happens to be awake will silently miss days and give a false sense of coverage. Instead:
- The agent is a **batch job runnable from any machine on demand** (`python -m agent.run`). On each run it reads `last_run` (from the DB), searches for everything new **since that timestamp**, processes it, and updates `last_run`. Missing a day just means the next run has more to catch up on — no coverage is lost.
- A light scheduler (Windows Task Scheduler / WSL cron / the workspace's existing patterns) can *trigger* that batch when a machine is on, but the batch's correctness never depends on the trigger firing on time — the `last_run` catch-up makes it self-healing.
- If genuinely unattended cadence is wanted later, a **cloud scheduled agent** (the workspace's `/schedule` routine) is the right tool, since it runs independently of any local machine's power state.
- The DB (`db/leaf_lit.db`) is the single source of truth for run state and syncs via OneDrive, so the "when did we last search" clock is shared across machines automatically.
