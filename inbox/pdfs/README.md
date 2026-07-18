Drop new article PDFs here.

## What happens (v2 knowledge-integration pipeline)

Run `run_integrate_once.bat` (or `run_integrate_watch.bat` to keep watching, or
`python agent/integrate_paper.py --inbox --mock`). For each dropped PDF the agent:

1. **registers** it — extracts text, infers metadata, copies the PDF into the
   durable article store, and maps it in `db/pdf_sources.json`;
2. **dedupes** by DOI / normalised title — a re-dropped paper **updates** the
   existing record instead of creating a duplicate;
3. **extracts** numeric results (+ evidence claims with `--real`);
4. **validates** — re-matches quotes against the physical PDF, sets
   `validation_state`;
5. **normalizes** — resolves species/quantities to existing **canonical
   entities** (reuse-or-create) and maps quantities onto the ontology outcome tree;
6. **links** claims to their numbers;
7. **rebuilds** the derived knowledge (harmonized layer, treatment features,
   candidate matrix) from the immutable raw rows, so the new paper **updates the
   body of knowledge** — counts, contradictions, confidence — rather than only
   adding rows;
8. writes an `integration_runs` audit row summarising what changed.

Only step 3 is per-paper/billed; the rest are deterministic rebuilds, so adding
one paper never re-extracts the corpus.

`--mock` uses the built-in regex extractor and needs no cloud access. Use
`--real` (with the `py_work` venv: boto3 + AWS) for Claude-on-Bedrock extraction.

The legacy `run_ingest_once.bat` / `auto_ingest.py` path now runs this same full
pipeline (and also dedupes). See `MIGRATION_NOTES.md` for details.

PDF files are intentionally ignored by Git; the deployed dashboard reads the
SQLite snapshot, not the source PDFs.
