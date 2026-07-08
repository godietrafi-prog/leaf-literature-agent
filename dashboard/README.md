# Dashboard — Leaf Literature Agent

Two ways to view the corpus:

| | `preview.html` (Artifact) | `app.py` (Streamlit) |
|---|---|---|
| Data | **snapshot** baked in at build time | **live** — reads `db/leaf_lit.db` on every run |
| Sharing | one private link, zero infra | needs a running server (local or hosted) |
| AI/ML methods tab | — | ✅ |
| Best for | sending the team a look right now | day-to-day use as the corpus grows |

## Run the live app (local)
```bash
cd "Analysis_Workspace/Leaf_Literature_Agent"
pip install -r dashboard/requirements.txt   # first time only
streamlit run dashboard/app.py
```
Opens at http://localhost:8501. Tabs: **Overview** (cross-study purity/yield), **Corpus**
(filter/search + per-paper detail), **AI / ML methods** (ML/DL/digital-twin precedents in
analogous systems, each card stating why it transfers to leaf-protein purification), **Topic
coverage**. Sidebar includes a *Refresh from DB* button.

## Add new PDFs without command-line work
Drop new article PDFs into:

```text
inbox/pdfs/
```

Then run one of the BAT files from Windows Explorer:

- `run_ingest_once.bat` — ingest whatever PDFs are waiting, commit the updated DB/mapping,
  and push to GitHub.
- `run_ingest_watch.bat` — keep checking `inbox/pdfs/` every 5 minutes. Leave this running
  on the lab machine for a low-maintenance drop-folder workflow.

The automation moves PDFs into the local article store, updates `db/leaf_lit.db` and
`db/pdf_sources.json`, and marks auto-extracted values for review in the dashboard.

## Share the live app with the team (a real link)
Streamlit needs a host. Options, cheapest first:
1. **Streamlit Community Cloud** — free; point it at a GitHub repo containing `app.py` +
   `db/leaf_lit.db` + `requirements.txt`; you get a public `*.streamlit.app` URL.
2. **A small VM / internal server** — `streamlit run --server.port 8501 --server.address 0.0.0.0`
   behind the institution's network/VPN.
3. **Keep sending the Artifact** as the zero-infra snapshot and re-publish it when the corpus changes.

## Regenerate the Artifact snapshot after the DB changes
```bash
python3 agent/ingest_seed.py          # rebuild db/leaf_lit.db
# then re-dump JSON into dashboard/preview.html and re-publish the Artifact
```

## Sync note
`.py` does **not** sync via OneDrive (see `/pack`); `preview.html`, `requirements.txt`, and
`db/leaf_lit.db` do. Zip `dashboard/app.py` + `agent/*.py` for transport between machines.
