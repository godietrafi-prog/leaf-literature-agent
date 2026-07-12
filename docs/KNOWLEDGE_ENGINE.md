# Knowledge Engine and Experiment Candidate Matrix

## Hard evidence boundary

Only physically mapped full-text PDFs enter claim extraction. Abstract-only
records are discovery metadata and are excluded from the Candidate Matrix and
DOE. Run `python3 agent/audit_fulltext.py` to rebuild the owner's fetch list.

## Ontology

`db/ontology_v1.json` is the manually controlled, versioned ontology. It
defines treatment families, a hierarchical outcome vocabulary, comparator
types, directions and effect types. The model must select from these values;
unknown values are rejected rather than silently added.

## Pipeline

```bash
python3 agent/knowledge_engine.py init
python3 agent/knowledge_engine.py select-pilot
~/.virtualenvs/test_project_env/bin/python agent/knowledge_engine.py extract --pilot
python3 agent/knowledge_engine.py audit-quotes
python3 agent/knowledge_engine.py build-matrix
```

After the pilot gate passes:

```bash
~/.virtualenvs/test_project_env/bin/python agent/knowledge_engine.py extract --all
python3 agent/knowledge_engine.py audit-quotes
python3 agent/knowledge_engine.py build-matrix
```

Bedrock responses are cached. Re-running does not re-bill unchanged prompts and
PDF text.

## Guardrails

- Every claim requires a source location and source quotation.
- A directional claim requires an explicit comparator.
- Treatment steps preserve their reported order.
- Quotes must match the physical PDF before claims enter the matrix.
- Reviews are `review_synthesis` and do not count as experimental replication.
- Scientific evidence and patents have separate `source_scope` values and
  separate Candidate Matrix rows.
- Core leaf/process evidence and transfer evidence are also scored separately.

## Two candidate resolutions

`family` rows identify possible DOE factors and replication across papers.
`signature` rows preserve the ordered process sequence and parameters. A
contradiction at family level may represent dose/order dependence; it is not
automatically treated as a failed treatment.

The dashboard Knowledge / DOE tab exposes both resolutions and traces every
candidate back to its source claims and quotations.
