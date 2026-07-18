#!/usr/bin/env python3
"""Idempotent schema migrations for the v2 knowledge-integration layer.

`CREATE TABLE IF NOT EXISTS` in db/schema.sql creates the new *tables*, but it
cannot add *columns* to tables that already exist. This module centralises the
guarded `ALTER TABLE ... ADD COLUMN` calls so every v2 module can call one
function and be sure the columns it needs are present. Safe to run repeatedly.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# table -> [(column, ddl)] additive columns not expressible via CREATE IF NOT EXISTS
NEW_COLUMNS = {
    "numeric_results": [
        # canonical quantity family + the ontology outcome the quantity rolls up to,
        # so the 1000+ raw quantity strings collapse onto the 28-node outcome tree.
        ("quantity_canonical", "TEXT"),
        ("outcome_id", "TEXT"),
        ("unit_canonical", "TEXT"),
        # resolved species entity (entity_mentions holds the audit trail).
        ("species_entity_id", "INTEGER"),
        # derived trust state: extracted / machine_verified / human_verified / rejected.
        ("validation_state", "TEXT"),
    ],
    "evidence_claims": [
        # the number this claim asserts (bridge into numeric_results).
        ("numeric_result_id", "INTEGER"),
    ],
}


def ensure(conn: sqlite3.Connection) -> None:
    """Create v2 tables (via schema.sql) and add v2 columns (guarded ALTERs)."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    for table, columns in NEW_COLUMNS.items():
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    conn.commit()


if __name__ == "__main__":
    c = sqlite3.connect(ROOT / "db" / "leaf_lit.db")
    c.execute("PRAGMA foreign_keys = ON")
    ensure(c)
    print("Migrations applied: v2 knowledge-integration tables + columns present.")
    c.close()
