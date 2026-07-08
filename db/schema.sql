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
