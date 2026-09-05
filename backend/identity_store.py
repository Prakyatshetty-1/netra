"""
NETRA identity verification storage.

This database stores DigiLocker verification metadata separately
from the existing NETRA simulation database.

Important:
- We do NOT store the raw DigiLocker identity identifier.
- We store an HMAC-derived subject hash instead.
- The existing netra_sim.db remains untouched.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent

IDENTITY_DB = ROOT / "netra_identity.db"


def get_conn() -> sqlite3.Connection:
    """
    Create a connection to the separate identity database.
    """

    conn = sqlite3.connect(IDENTITY_DB)

    conn.row_factory = sqlite3.Row

    return conn


def init_identity_db() -> None:
    """
    Create the identity verification table if it does not already exist.
    """

    conn = get_conn()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS digilocker_verification (
            verification_id INTEGER PRIMARY KEY AUTOINCREMENT,

            case_id INTEGER NOT NULL,

            person_id INTEGER NOT NULL,

            subject_hash TEXT NOT NULL,

            verified_name TEXT,

            name_similarity REAL,

            verification_confidence REAL NOT NULL,

            verification_status TEXT NOT NULL,

            consent_valid_till INTEGER,

            scope TEXT,

            verified_at TEXT NOT NULL,

            source TEXT NOT NULL
        )
        """
    )

    conn.commit()

    conn.close()


def save_verification(
    *,
    case_id: int,
    person_id: int,
    subject_hash: str,
    verified_name: str | None,
    name_similarity: float | None,
    verification_confidence: float,
    verification_status: str,
    consent_valid_till: int | None,
    scope: str | None,
    verified_at: str,
    source: str,
) -> None:
    """
    Store one DigiLocker verification event.
    """

    conn = get_conn()

    conn.execute(
        """
        INSERT INTO digilocker_verification (
            case_id,
            person_id,
            subject_hash,
            verified_name,
            name_similarity,
            verification_confidence,
            verification_status,
            consent_valid_till,
            scope,
            verified_at,
            source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            person_id,
            subject_hash,
            verified_name,
            name_similarity,
            verification_confidence,
            verification_status,
            consent_valid_till,
            scope,
            verified_at,
            source,
        ),
    )

    conn.commit()

    conn.close()


def get_latest_verification(
    case_id: int,
    person_id: int,
) -> dict[str, Any] | None:
    """
    Return the most recent verification for a person in a case.
    """

    conn = get_conn()

    row = conn.execute(
        """
        SELECT *
        FROM digilocker_verification
        WHERE case_id = ?
          AND person_id = ?
        ORDER BY verification_id DESC
        LIMIT 1
        """,
        (
            case_id,
            person_id,
        ),
    ).fetchone()

    conn.close()

    if row is None:
        return None

    return dict(row)