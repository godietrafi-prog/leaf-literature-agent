# Leaf Literature Agent — Goals & Charter

**Owner:** Rafi Steckler | **Created:** 2026-07-07 | **Status:** scaffolding — to be built out in a dedicated session
**Spin-off of:** `Analysis_Workspace/Leaf_Protein_Extraction` (which supplied the seed data and the scientific focus)

## What this project is

An **autonomous literature-mining agent** that continuously scans, retrieves, structures, and analyzes the scientific literature on **leaf-protein extraction and the elimination of off-odor, off-flavor, and green color** — with special emphasis on the underlying driver of all three: **lipoxygenase (LOX) activity** and the enzymatic/biochemical changes at the moment of leaf disruption.

It is a research-intelligence system, not a one-off review. The one-off review already done (in the parent project) is its seed; this agent keeps it alive and growing.

## The goals, as specified by the owner (2026-07-07)

1. **Scheduled autonomous search.** Run on a fixed cadence (initially ~daily; interval configurable, to be tuned later) to find new studies matching the focus: leaf-protein extraction; removal of off-odor / off-flavor / color; and especially the LOX-driven mechanisms behind those sensory defects.
2. **Human-in-the-loop for access.** The agent reports which papers (and which **supplementary files**) it cannot access; the owner supplies those, and the agent ingests them. The agent may also ask the owner to fill any other gaps it can't resolve.
3. **Structured, growing database.** Every paper becomes a record with: categorical tags (what it is about), a concise scientific-story summary, its findings, and — wherever possible — **extracted numeric results**.
4. **Linked numeric-results table.** Numeric results live in a separate table, **indexed back to the source paper**, so the numbers are queryable/analyzable as data while remaining traceable to their origin.
5. **Supplementary-material mining.** Much real data hides in supplementary files (SI). The agent tries to obtain and parse the SI, not just the main text.
6. **Toward learnable data.** From the linked numeric table, assess what can be **normalized** across studies and fed into downstream learning/analysis (the eventual bridge back to the parent project's modeling ambitions).
7. **Smart dashboard + chart generator.** A dashboard presents the DB; clicking a paper pulls its reported results and **automatically decides how to visualize them** (the chart type is chosen intelligently from the shape of the data).
8. **LLM-assisted pipeline via AWS Bedrock.** The per-paper pipeline (find → access-check → acquire incl. SI → extract → summarize → structure → store) can "consult" an LLM through the owner's **Bedrock** account for the hard steps (reading, extraction, categorization, summary).

## What this scaffolding contains (starting point for the build session)

- `README_GOALS.md` — this file.
- `docs/SYSTEM_ARCHITECTURE.md` — the proposed system design: pipeline stages, components, the daily loop, the human-in-the-loop path, and where Bedrock plugs in.
- `docs/DB_SCHEMA.md` — the database design: the `papers` table, the linked `numeric_results` table, categorical taxonomies, access-status tracking, and the normalization strategy.
- `seed_data/metadata/` — **31 structured per-paper records already built in the parent project.** These are the agent's starting corpus and a concrete example of the target output format (YAML front-matter + narrative). The build should ingest these first, both to bootstrap the DB and to validate the schema against real hand-made records.
- `db/` — where the built database (SQLite recommended, see schema doc) will live.
- `inaccessible_queue/` — drop-folder + manifest for papers/SI the agent couldn't fetch; the owner fills these.
- `agent/` — the agent code (to be written in the build session).
- `dashboard/` — the smart dashboard + chart generator (to be written).

## Relationship to the parent project

The parent project (`Leaf_Protein_Extraction`) defines the **science** (the H1/H2 hypotheses, the LOX-off-flavor focus, the DGMA sensing concept) and produced the **seed corpus**. This agent is the **infrastructure** that scales that literature work from a one-time human review into a continuously-updated, queryable, analyzable knowledge base — which in turn feeds better priors and training data back to the parent project's models. Keep the two linked but distinct: science lives there, literature-intelligence infrastructure lives here.

## Design refinements layered on the owner's spec (2026-07-08)
Reviewed the spec and added four things that de-risk the build; details in the two `docs/` files:
1. **Extraction eval loop** (`SYSTEM_ARCHITECTURE §2a`) — the 31 seed records are the gold standard; score the LLM extractor against them (precision/recall/value-accuracy) and gate new-paper extraction on clearing a threshold. This is the operational form of "never fabricate a number."
2. **Uncertainty columns in `numeric_results`** (`DB_SCHEMA`) — `sd_error`, `error_type`, `n_replicates`, `p_value`. Without variance + n you cannot meta-analyse; capturing them at extraction is free, back-filling later is not.
3. **Citation-snowball search first** (`SYSTEM_ARCHITECTURE §2`) — expand from the seed nucleus through the citation graph before broad keyword search; far higher signal-to-noise.
4. **Run-on-demand + catch-up scheduling** (`SYSTEM_ARCHITECTURE §8`) — not a daily daemon; a batch runnable from any machine that catches up since `last_run`, self-healing across power-offs and multiple machines.

**Build-order recommendation:** de-risk the hard core first, defer the shiny/low-ROI last — (1) DB + seed ingest ✅ → (2) extraction + eval → (3) acquire + SI + queue → (4) search (snowball then keyword) → (5) normalization → (6) dashboard (corpus view first; the *auto-chart-selector is explicitly last and optional* — it is the lowest-ROI, most fragile piece and must not block the queryable DB that is the real deliverable).

## Explicit non-goals (for now)
- Not building the predictive models here (that's the parent project).
- Not fabricating or inferring numeric results the papers don't report — the DB records only what is actually in the paper/SI, with the source paper's index attached, and flags gaps for the owner rather than guessing.
