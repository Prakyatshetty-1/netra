"""SQLite helper for the read-only netra_sim.db dataset."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

# Prototype root (parent of backend/) holds netra_sim.db
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "netra_sim.db"
AUDIT_LOG_PATH = ROOT / "audit_log.jsonl"
DOCUMENTS_DIR = ROOT / "uploads" / "documents"
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Expected database at {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_write_conn() -> sqlite3.Connection:
    """Writable connection — used only by PDF confirm (human-validated inserts)."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Expected database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_one(sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def node_key(entity_type: str, entity_id: int) -> str:
    return f"{entity_type}:{entity_id}"


def parse_node_key(key: str) -> tuple[str, int]:
    kind, _, rest = key.partition(":")
    return kind, int(rest)
