# Numeric evidence extraction

The extraction workflow is deliberately split into generation, review and
promotion. Generated candidates never enter `numeric_results` directly.

## Run a pilot

```bash
python3 agent/run_evidence_pipeline.py --paper-id corvino2025_plant_milk_ptrms --min-score 3
```

Generated files are under `db/evidence_staging/` and are ignored by Git:

- `table_manifest.jsonl` and `tables/*.csv`: native PDF table extraction;
- `figure_manifest.jsonl` and `figures/*.png`: figure crops requiring calibration;
- `numeric_review.jsonl`: numeric candidates, initially `needs_review`.

## Review table candidates

```bash
python3 agent/review_evidence_queue.py list --paper-id corvino2025_plant_milk_ptrms
python3 agent/review_evidence_queue.py show PROPOSAL_ID
python3 agent/review_evidence_queue.py approve PROPOSAL_ID \
  --set treatment_condition="commercial almond beverage" \
  --set method=PTR-ToF-MS \
  --set error_type=SD \
  --note="Checked against Table 1 and PDF page"
```

Approval is rejected unless unit, treatment condition and dispersion type are
resolved. Reject a false extraction with:

```bash
python3 agent/review_evidence_queue.py reject PROPOSAL_ID --note="m/z value, not concentration"
```

## Digitise a plot

Create a calibration JSON with two known pixel/value positions on each axis.
Create a point CSV with `pixel_x,pixel_y` and optional `condition,series`.

```bash
python3 agent/digitize_plot.py \
  --image db/evidence_staging/figures/PLOT.png \
  --calibration calibration.json \
  --points pixel_points.csv \
  --paper-id PAPER_ID --figure-label 4 --pdf-page 12 \
  --quantity yield_pct --unit % --estimated-error 0.5 \
  --output db/evidence_staging/graph_review.jsonl
```

The tool supports linear and log10 axes. It can alternatively trace a coloured
series using `--trace-rgb R,G,B --bounds x_min,x_max,y_min,y_max`. Colour tracing
is only a starting point and always requires visual review.

## Validate and promote

```bash
python3 agent/evidence_pipeline.py validate
python3 agent/evidence_pipeline.py promote --dry-run
python3 agent/evidence_pipeline.py promote
```

Only rows explicitly marked `approved` are considered. Promotion is idempotent
for the same paper, quantity, value and source location. Table-derived rows use
`provenance=evidence:table_native`; digitised rows use
`provenance=evidence:graph_digitized`.
