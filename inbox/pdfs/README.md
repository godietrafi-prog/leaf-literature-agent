Drop new article PDFs here.

The automation scripts move each PDF into the local article store, add it to
`db/pdf_sources.json`, create/update the paper row in `db/leaf_lit.db`, extract
basic numeric values, commit the DB/mapping changes, and push them to GitHub.

PDF files are intentionally ignored by Git; the deployed dashboard reads the
SQLite snapshot, not the source PDFs.
