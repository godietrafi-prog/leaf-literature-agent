-- Leaf Literature Agent — SQLite schema
-- Implements docs/DB_SCHEMA.md. Idempotent: safe to re-run.
-- Engine: SQLite (single portable file db/leaf_lit.db, syncs via OneDrive).

PRAGMA foreign_keys = ON;

-- One row per study --------------------------------------------------------
CREATE TABLE IF NOT EXISTS papers (
    paper_id            TEXT PRIMARY KEY,      -- stable citekey, e.g. duckweed_pmc2023
    doi                 TEXT,                  -- nullable; unique when present
    title               TEXT,
    authors             TEXT,
    year                INTEGER,
    venue               TEXT,                  -- journal / preprint server
    source_type         TEXT,                  -- peer-reviewed / preprint / patent / thesis
    system              TEXT,                  -- species / feedstock
    extraction_method_family TEXT,             -- raw method string as recorded
    relevance           TEXT,                  -- High / Medium / Low
    verification_level  TEXT,                  -- abstract / full_text / full_text+SI
    access_status       TEXT,                  -- open / owner_supplied / queued
    si_status           TEXT,                  -- none / fetched / queued / not_applicable
    discovery           TEXT,                  -- snowball_ref / snowball_cite / keyword / owner / seed
    scientific_story    TEXT,                  -- concise narrative (LLM-gen, human-editable)
    key_findings        TEXT,                  -- bullet findings
    added_date          TEXT,
    last_updated        TEXT,
    llm_cache_key       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi) WHERE doi IS NOT NULL;

-- Many-to-many categorical tagging ----------------------------------------
CREATE TABLE IF NOT EXISTS paper_categories (
    paper_id  TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    category  TEXT NOT NULL,                   -- controlled vocab, e.g. mechanism:LOX
    PRIMARY KEY (paper_id, category)
);
CREATE INDEX IF NOT EXISTS idx_cat_category ON paper_categories(category);

-- The linked results table (many rows per paper) --------------------------
CREATE TABLE IF NOT EXISTS numeric_results (
    result_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id            TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    quantity            TEXT NOT NULL,         -- controlled vocab
    value               REAL,                  -- central value (mean / point estimate)
    unit                TEXT,
    sd_error            REAL,                  -- dispersion; nullable
    error_type          TEXT,                  -- SD / SEM / CI95 / range / null
    n_replicates        INTEGER,               -- sample size; nullable
    p_value             REAL,                  -- nullable
    method              TEXT,
    species             TEXT,
    treatment_condition TEXT,
    basis               TEXT,                  -- dry/wet; N-to-protein factor if a protein %
    source_location     TEXT,                  -- verbatim quote / table ref — traceability
    is_from_SI          INTEGER DEFAULT 0,     -- 0/1
    needs_human         INTEGER DEFAULT 0,     -- 0/1 — uncertain / parsed from narrative
    provenance          TEXT DEFAULT 'seed',   -- 'seed' (human-supplied review) | 'llm:<model>' (auto-extracted, UNVERIFIED)
    verified            INTEGER DEFAULT 0,     -- 0/1 — human confirmed via the dashboard verification workbench
    verified_value      REAL,                  -- human-corrected value (if the extracted one was wrong)
    verified_by         TEXT,                  -- person / process that performed validation
    confidence          TEXT,                  -- High / Medium / Low
    verified_note       TEXT,
    verified_date       TEXT,
    extracted_date      TEXT
);
CREATE INDEX IF NOT EXISTS idx_nr_paper     ON numeric_results(paper_id);
CREATE INDEX IF NOT EXISTS idx_nr_quantity  ON numeric_results(quantity);
CREATE INDEX IF NOT EXISTS idx_nr_needshuman ON numeric_results(needs_human);

-- Derived, never overwrites raw -------------------------------------------
CREATE TABLE IF NOT EXISTS numeric_results_normalized (
    result_id    INTEGER PRIMARY KEY REFERENCES numeric_results(result_id) ON DELETE CASCADE,
    quantity_std TEXT,
    value_std    REAL,
    unit_std     TEXT,
    norm_notes   TEXT
);

-- Auditable harmonization layer; raw numeric_results remains immutable -------
CREATE TABLE IF NOT EXISTS numeric_results_harmonized (
    result_id              INTEGER PRIMARY KEY REFERENCES numeric_results(result_id) ON DELETE CASCADE,
    quantity_std           TEXT NOT NULL,
    value_std              REAL,
    unit_std               TEXT,
    ontology_term          TEXT,
    harmonization_status   TEXT NOT NULL, -- exact / converted / identity_only / not_harmonizable / needs_mapping
    conversion_formula     TEXT,
    mapping_version        TEXT NOT NULL,
    harmonization_notes    TEXT,
    created_date           TEXT
);

-- Structured experimental descriptors parsed from treatment prose -----------
CREATE TABLE IF NOT EXISTS treatment_features (
    result_id          INTEGER PRIMARY KEY REFERENCES numeric_results(result_id) ON DELETE CASCADE,
    ph                 REAL,
    temperature_c      REAL,
    time_min           REAL,
    oxygen_control     INTEGER, -- 0/1/null
    sonication         INTEGER, -- 0/1/null
    heat_treatment     INTEGER, -- 0/1/null
    feature_status     TEXT NOT NULL,
    mapping_version    TEXT NOT NULL,
    mapping_notes      TEXT
);

-- Knowledge layer ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_materials (
    material_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    species           TEXT,
    cultivar          TEXT,
    plant_part        TEXT,
    material_form     TEXT,
    processing_state  TEXT,
    material_raw      TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_treatments (
    treatment_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    treatment_family   TEXT NOT NULL,
    description_raw    TEXT NOT NULL,
    atmosphere         TEXT,
    treatment_signature TEXT,
    ontology_version   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_treatment_steps (
    step_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    treatment_id     INTEGER NOT NULL REFERENCES knowledge_treatments(treatment_id) ON DELETE CASCADE,
    step_order       INTEGER NOT NULL,
    operation        TEXT NOT NULL,
    temperature_c    REAL,
    time_min         REAL,
    ph               REAL,
    pressure         TEXT,
    power            TEXT,
    frequency        TEXT,
    concentration    TEXT,
    atmosphere       TEXT,
    solvent          TEXT,
    solid_liquid_ratio TEXT,
    source_text      TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_outcomes (
    outcome_id        TEXT PRIMARY KEY,
    parent_outcome_id TEXT REFERENCES knowledge_outcomes(outcome_id),
    label             TEXT NOT NULL,
    ontology_version  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_paper_roles (
    paper_id            TEXT PRIMARY KEY REFERENCES papers(paper_id) ON DELETE CASCADE,
    source_scope        TEXT NOT NULL, -- scientific / patent
    study_role          TEXT NOT NULL, -- primary_experiment / review_synthesis / method_transfer
    evidence_domain     TEXT NOT NULL, -- core_leaf_process / transfer
    role_basis          TEXT,
    mapping_version     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_claims (
    claim_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id          TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    material_id       INTEGER REFERENCES knowledge_materials(material_id),
    treatment_id      INTEGER REFERENCES knowledge_treatments(treatment_id),
    outcome_id        TEXT REFERENCES knowledge_outcomes(outcome_id),
    comparator_type   TEXT,
    comparator_raw    TEXT,
    direction         TEXT NOT NULL,
    effect_type       TEXT NOT NULL,
    effect_value      REAL,
    effect_unit       TEXT,
    uncertainty       TEXT,
    p_value           REAL,
    qualitative_result TEXT,
    source_location   TEXT NOT NULL,
    source_quote      TEXT NOT NULL,
    quote_match       INTEGER,
    extraction_model  TEXT,
    extraction_cache_key TEXT,
    validation_status TEXT NOT NULL DEFAULT 'needs_review',
    confidence        TEXT,
    ontology_version  TEXT NOT NULL,
    created_date      TEXT
);

CREATE INDEX IF NOT EXISTS idx_claim_paper ON evidence_claims(paper_id);
CREATE INDEX IF NOT EXISTS idx_claim_treatment ON evidence_claims(treatment_id);
CREATE INDEX IF NOT EXISTS idx_claim_outcome ON evidence_claims(outcome_id);

CREATE TABLE IF NOT EXISTS experiment_candidates (
    candidate_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    treatment_family   TEXT NOT NULL,
    treatment_signature TEXT NOT NULL,
    aggregation_level   TEXT NOT NULL,
    source_scope       TEXT NOT NULL,
    evidence_domain    TEXT NOT NULL,
    outcome_id         TEXT NOT NULL,
    paper_count        INTEGER,
    species_count      INTEGER,
    positive_claims    INTEGER,
    neutral_claims     INTEGER,
    negative_claims    INTEGER,
    mixed_claims       INTEGER,
    contradiction_rate REAL,
    evidence_score     REAL,
    confidence         TEXT,
    parameter_ranges   TEXT,
    representative_papers TEXT,
    contradictions     TEXT,
    doe_role            TEXT,
    matrix_version      TEXT,
    created_date        TEXT,
    UNIQUE(source_scope, evidence_domain, aggregation_level, treatment_signature, outcome_id, matrix_version)
);

-- Mirrors the inaccessible_queue/ folder ----------------------------------
CREATE TABLE IF NOT EXISTS access_queue (
    paper_id       TEXT,
    doi            TEXT,
    missing        TEXT,                        -- main / SI / both
    link           TEXT,
    why_it_matters TEXT,
    requested_date TEXT,
    resolved_date  TEXT
);

-- Every scheduled search --------------------------------------------------
CREATE TABLE IF NOT EXISTS query_log (
    run_date TEXT,
    cluster  TEXT,
    query    TEXT,
    n_hits   INTEGER,
    n_new    INTEGER
);

-- Extraction eval runs (the LLM guardrail; docs §2a) ----------------------
CREATE TABLE IF NOT EXISTS eval_runs (
    run_date       TEXT,
    model          TEXT,
    prompt_version TEXT,
    recall         REAL,
    precision      REAL,
    value_accuracy REAL,
    notes          TEXT
);

-- Shared run state for run-on-demand + catch-up scheduling (docs §8) -------
CREATE TABLE IF NOT EXISTS run_state (
    key   TEXT PRIMARY KEY,                     -- e.g. 'last_run'
    value TEXT
);
