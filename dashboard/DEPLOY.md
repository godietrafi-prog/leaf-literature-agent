# Deploying the dashboard as a live, shareable link (safely)

The Streamlit app can be hosted so the team opens it in a browser — **as a read-only
view that cannot damage the data.**

## The safety model (why the shared link can't corrupt your data)

Three layers, in order of importance:

1. **`LEAF_READONLY=1` → no write UI at all.** With this env var set, the Verify
   tab renders as a plain read-only table: no editable cells, no Save button. Every
   other feature (browse, charts, cross-study, query, CSV export) still works. This
   is the switch you set on the shared deployment.
2. **The hosted DB is a disposable copy, not your source of truth.** Streamlit
   Community Cloud runs from a *copy* of `db/leaf_lit.db` pulled from the GitHub
   repo. Nothing a visitor does can reach the real `leaf_lit.db` on your OneDrive.
   Even in the worst case, a redeploy resets the hosted copy from the repo.
3. **Restrict who can open it (optional).** Community Cloud lets you mark an app
   **private** and allow-list viewer emails, so only invited teammates can load it.
   On the free public tier the URL is open to anyone who has it (and to crawlers) —
   so keep it read-only (layer 1) and don't post the URL publicly.

**Verification (the write workflow) stays on your local instance** — run the app
without `LEAF_READONLY` on your own machine to confirm/correct values; the team's
shared link is read-only.

## The "Deploy" button (top-right of the Streamlit app)

That button is Streamlit's built-in shortcut to **Streamlit Community Cloud** — the
free hosting below. Clicking it opens the same flow. You can use it or the manual
steps; both need a GitHub repo.

## Steps — Streamlit Community Cloud (free)

1. **Put these files in a GitHub repo** (the app only needs the DB, not the PDFs):
   - `dashboard/app.py`
   - `dashboard/requirements.txt`
   - `dashboard/.streamlit/config.toml`
   - `db/leaf_lit.db`  ← the data snapshot the app reads
   - `db/pdf_sources.json`  ← for the Verify tab's "PDF to open" hint (optional)
   > `.py` files don't sync via OneDrive, so push from the local copy. The repo can
   > be **private** — Community Cloud connects to private repos.
2. Go to **share.streamlit.io** → sign in with GitHub → **New app** → pick the repo
   and set the main file to `dashboard/app.py`.
3. **Advanced settings → Secrets / environment**, add:
   ```
   LEAF_READONLY = "1"
   ```
   (this is what makes the shared instance read-only — do not skip it).
4. Deploy. You get a `https://<name>.streamlit.app` URL to send the team.
5. **To refresh the data** the team sees: rebuild `db/leaf_lit.db` locally
   (`ingest_seed.py` + `store_extractions.py`), commit it to the repo, and the app
   auto-redeploys.

## Alternative: institutional server / VPN
`streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8501` behind
Tel-Hai's network. Set `LEAF_READONLY=1` in the environment for the shared instance.

## Note on the data copy
The hosted DB is a point-in-time snapshot. Treat the OneDrive `leaf_lit.db` as the
source of truth; the deployed copy is downstream and disposable.
