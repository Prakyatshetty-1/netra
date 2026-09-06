"""
NETRA DigiLocker service.

Supports:
- MOCK mode for local development / hackathon demonstration
- PRODUCTION mode through an authorized DigiLocker Requester OAuth flow

IMPORTANT:
Mock mode uses synthetic data only.
It must never be presented as a real government verification.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.db import query_one
from backend.identity_store import (
    save_verification,
    get_latest_verification,
)


# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

DIGILOCKER_MODE = os.getenv(
    "DIGILOCKER_MODE",
    "mock",
).lower()


def mode() -> str:
    """Return the active DigiLocker mode."""
    return DIGILOCKER_MODE


def frontend_url() -> str:
    """Return the frontend URL used after OAuth completion."""
    return os.getenv(
        "FRONTEND_URL",
        "http://localhost:5173",
    ).rstrip("/")


# ---------------------------------------------------------------------
# REAL DIGILOCKER CONFIGURATION
# ---------------------------------------------------------------------

DIGILOCKER_AUTH_URL = os.getenv(
    "DIGILOCKER_AUTH_URL",
    "",
).strip()

DIGILOCKER_TOKEN_URL = os.getenv(
    "DIGILOCKER_TOKEN_URL",
    "",
).strip()

DIGILOCKER_USERINFO_URL = os.getenv(
    "DIGILOCKER_USERINFO_URL",
    "",
).strip()

DIGILOCKER_CLIENT_ID = os.getenv(
    "DIGILOCKER_CLIENT_ID",
    "",
).strip()

DIGILOCKER_CLIENT_SECRET = os.getenv(
    "DIGILOCKER_CLIENT_SECRET",
    "",
).strip()

DIGILOCKER_REDIRECT_URI = os.getenv(
    "DIGILOCKER_REDIRECT_URI",
    "http://127.0.0.1:8000/auth/digilocker/callback",
).strip()

DIGILOCKER_SCOPE = os.getenv(
    "DIGILOCKER_SCOPE",
    "openid",
).strip()


# ---------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------

def create_pkce_pair() -> tuple[str, str]:
    """
    Create OAuth PKCE verifier and challenge.
    """

    code_verifier = (
        secrets.token_urlsafe(64)
        .replace("=", "")
    )

    digest = hashlib.sha256(
        code_verifier.encode("ascii")
    ).digest()

    code_challenge = (
        base64.urlsafe_b64encode(digest)
        .decode("ascii")
        .rstrip("=")
    )

    return code_verifier, code_challenge


# ---------------------------------------------------------------------
# REAL OAUTH AUTHORIZATION URL
# ---------------------------------------------------------------------

def build_authorization_url(
    *,
    case_id: int,
    person_id: int,
    state: str,
    code_challenge: str,
) -> str:
    """
    Build the DigiLocker OAuth authorization URL.

    case_id and person_id remain inside NETRA's server-side OAuth
    session. They are not used as DigiLocker identity claims.
    """

    if not DIGILOCKER_AUTH_URL:
        raise RuntimeError(
            "DigiLocker production mode is enabled but "
            "DIGILOCKER_AUTH_URL is not configured."
        )

    if not DIGILOCKER_CLIENT_ID:
        raise RuntimeError(
            "DigiLocker production mode is enabled but "
            "DIGILOCKER_CLIENT_ID is not configured."
        )

    params = {
        "response_type": "code",
        "client_id": DIGILOCKER_CLIENT_ID,
        "redirect_uri": DIGILOCKER_REDIRECT_URI,
        "scope": DIGILOCKER_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    return (
        DIGILOCKER_AUTH_URL
        + "?"
        + urlencode(params)
    )


# ---------------------------------------------------------------------
# REAL TOKEN EXCHANGE
# ---------------------------------------------------------------------

async def exchange_code(
    *,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    """Exchange DigiLocker OAuth authorization code for tokens."""

    if mode() != "production":
        raise RuntimeError(
            "Real DigiLocker OAuth is unavailable in mock mode."
        )

    if not DIGILOCKER_TOKEN_URL:
        raise RuntimeError(
            "DIGILOCKER_TOKEN_URL is not configured."
        )

    if not DIGILOCKER_CLIENT_ID:
        raise RuntimeError(
            "DIGILOCKER_CLIENT_ID is not configured."
        )

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DIGILOCKER_REDIRECT_URI,
        "client_id": DIGILOCKER_CLIENT_ID,
        "code_verifier": code_verifier,
    }

    auth = None

    if DIGILOCKER_CLIENT_SECRET:
        auth = (
            DIGILOCKER_CLIENT_ID,
            DIGILOCKER_CLIENT_SECRET,
        )

    async with httpx.AsyncClient(
        timeout=30.0
    ) as client:

        response = await client.post(
            DIGILOCKER_TOKEN_URL,
            data=payload,
            auth=auth,
            headers={
                "Accept": "application/json",
            },
        )

        response.raise_for_status()

        return response.json()


# ---------------------------------------------------------------------
# REAL USER DETAILS
# ---------------------------------------------------------------------

async def get_user_details(
    access_token: str,
) -> dict[str, Any]:
    """
    Retrieve identity information from the authorized provider.

    The exact fields depend on the authorized DigiLocker API contract.
    """

    if mode() != "production":
        raise RuntimeError(
            "Real DigiLocker user lookup is unavailable in mock mode."
        )

    if not DIGILOCKER_USERINFO_URL:
        raise RuntimeError(
            "DIGILOCKER_USERINFO_URL is not configured."
        )

    async with httpx.AsyncClient(
        timeout=30.0
    ) as client:

        response = await client.get(
            DIGILOCKER_USERINFO_URL,
            headers={
                "Authorization": (
                    f"Bearer {access_token}"
                ),
                "Accept": "application/json",
            },
        )

        response.raise_for_status()

        return response.json()


# ---------------------------------------------------------------------
# PERSON LOOKUP
# ---------------------------------------------------------------------

def _get_person(
    person_id: int,
) -> dict[str, Any] | None:

    return query_one(
        """
        SELECT
            p.PersonID,
            p.FullName,
            p.AgeYear,
            p.GenderID,
            p.CaseMasterID,
            u.UnitName,
            d.DistrictName,
            s.StateName
        FROM Person p
        LEFT JOIN CaseMaster cm
            ON cm.CaseMasterID = p.CaseMasterID
        LEFT JOIN Unit u
            ON u.UnitID = cm.PoliceStationID
        LEFT JOIN District d
            ON d.DistrictID = u.DistrictID
        LEFT JOIN State s
            ON s.StateID = d.StateID
        WHERE p.PersonID = ?
        """,
        (person_id,),
    )


# ---------------------------------------------------------------------
# SYNTHETIC DEMO DOCUMENT
# ---------------------------------------------------------------------

def _synthetic_document(
    person: dict[str, Any],
) -> dict[str, Any]:
    """
    Create deterministic synthetic DigiLocker-shaped data.

    This is NOT a real government document.
    """

    age = person.get("AgeYear")

    year = (
        int(age)
        if age
        else None
    )

    dob = (
        f"{year}-05-14"
        if year and 1900 < year < 2100
        else None
    )

    return {
        "document_type": "DEMO_GOVERNMENT_ID",
        "issuer": "DEMO-GOVERNMENT-ISSUER",
        "document_id": (
            f"DEMO-DL-{int(person['PersonID']):06d}"
        ),
        "name": person.get("FullName"),
        "date_of_birth": dob,
        "phone": None,
        "place": (
            person.get("DistrictName")
            or person.get("UnitName")
        ),
        "verified": True,
        "synthetic": True,
        "verification_note": (
            "Synthetic DigiLocker-shaped data for "
            "local demonstration only; not a real "
            "government record."
        ),
    }


# ---------------------------------------------------------------------
# MOCK VERIFICATION
# ---------------------------------------------------------------------

def create_mock_verification(
    case_id: int,
    person_id: int,
) -> dict[str, Any]:

    person = _get_person(person_id)

    if not person:
        raise ValueError(
            "Person not found"
        )

    document = _synthetic_document(
        person
    )

    now = datetime.now(
        timezone.utc
    )

    verified_at = now.isoformat()

    subject_hash = hashlib.sha256(
        f"NETRA-DEMO-DIGILOCKER:{person_id}".encode(
            "utf-8"
        )
    ).hexdigest()

    # Store metadata using the EXISTING identity_store API.
    save_verification(
        case_id=case_id,
        person_id=person_id,
        subject_hash=subject_hash,
        verified_name=document.get("name"),
        name_similarity=1.0,
        verification_confidence=1.0,
        verification_status="VERIFIED_HIGH_CONFIDENCE",
        consent_valid_till=None,
        scope="demo",
        verified_at=verified_at,
        source="DIGILOCKER_MOCK",
    )

    verification = get_latest_verification(
        case_id,
        person_id,
    )

    return {
        "provider": "DigiLocker",
        "mode": "mock",
        "authorization": "DEMO_AUTHORIZED",
        "case_id": case_id,
        "person_id": person_id,
        "status": "VERIFIED_HIGH_CONFIDENCE",
        "verified": True,
        "document": document,
        "verification": verification,
        "audit": {
            "event": "DEMO_VERIFICATION_COMPLETED",
            "person_id": person_id,
            "case_id": case_id,
            "timestamp": verified_at,
        },
        "xai": {
            "conclusion": (
                "Synthetic identity fields match the "
                "NETRA person record in demo mode."
            ),
            "evidence_source": (
                "Local NETRA prototype database plus "
                "synthetic DigiLocker-shaped data."
            ),
            "field_comparisons": [
                {
                    "field": "FullName",
                    "police_value": person.get("FullName"),
                    "digilocker_value": document.get("name"),
                    "similarity": 1.0,
                    "matched": True,
                },
            ],
            "limitations": [
                "This is not a live DigiLocker lookup.",
                "The document is synthetic.",
                "No government record was queried.",
                "Production verification requires "
                "authorized DigiLocker Requester access "
                "and user consent.",
            ],
        },
    }


# ---------------------------------------------------------------------
# REAL USER PROCESSING
# ---------------------------------------------------------------------

def _first_value(
    data: dict[str, Any],
    keys: tuple[str, ...],
) -> Any:

    for key in keys:

        value = data.get(key)

        if value not in (
            None,
            "",
        ):
            return value

    return None


def _normalize_name(
    value: Any,
) -> str:

    if value is None:
        return ""

    return " ".join(
        str(value)
        .strip()
        .lower()
        .split()
    )


def _name_similarity(
    left: Any,
    right: Any,
) -> float:

    a = _normalize_name(left)
    b = _normalize_name(right)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    a_tokens = set(a.split())
    b_tokens = set(b.split())

    intersection = len(
        a_tokens & b_tokens
    )

    union = len(
        a_tokens | b_tokens
    )

    if union == 0:
        return 0.0

    return intersection / union


def process_real_user(
    *,
    case_id: int,
    person_id: int,
    token_response: dict[str, Any],
    user_response: dict[str, Any],
) -> dict[str, Any]:

    person = _get_person(person_id)

    if not person:
        raise ValueError(
            "Person not found"
        )

    police_name = person.get(
        "FullName"
    )

    verified_name = _first_value(
        user_response,
        (
            "name",
            "full_name",
            "fullname",
            "FullName",
        ),
    )

    similarity = _name_similarity(
        police_name,
        verified_name,
    )

    if verified_name and similarity >= 0.95:

        status = (
            "VERIFIED_HIGH_CONFIDENCE"
        )

    elif verified_name and similarity >= 0.75:

        status = (
            "VERIFIED_WITH_PARTIAL_MATCH"
        )

    elif verified_name:

        status = "MISMATCH"

    else:

        status = "REVIEW_REQUIRED"

    subject = (
        user_response.get("sub")
        or user_response.get("id")
        or user_response.get("user_id")
    )

    subject_hash = None

    if subject:

        subject_hash = hashlib.sha256(
            str(subject).encode("utf-8")
        ).hexdigest()

    scope = token_response.get(
        "scope",
        DIGILOCKER_SCOPE,
    )

    consent_valid_till = None

    expires_in = token_response.get(
        "expires_in"
    )

    if expires_in:

        try:

            consent_valid_till = int(
                datetime.now(
                    timezone.utc
                ).timestamp()
            ) + int(expires_in)

        except (
            TypeError,
            ValueError,
        ):

            consent_valid_till = None

    verification_confidence = similarity

    save_verification(
        case_id=case_id,
        person_id=person_id,
        subject_hash=(
            subject_hash
            or hashlib.sha256(
                f"NO-SUBJECT:{case_id}:{person_id}".encode(
                    "utf-8"
                )
            ).hexdigest()
        ),
        verified_name=verified_name,
        name_similarity=similarity,
        verification_confidence=verification_confidence,
        verification_status=status,
        consent_valid_till=consent_valid_till,
        scope=scope,
        verified_at=datetime.now(
            timezone.utc
        ).isoformat(),
        source="DIGILOCKER_OAUTH",
    )

    verification = get_latest_verification(
        case_id,
        person_id,
    )

    return {
        "provider": "DigiLocker",
        "mode": "production",
        "case_id": case_id,
        "person_id": person_id,
        "status": status,
        "verified": status in {
            "VERIFIED_HIGH_CONFIDENCE",
            "VERIFIED_WITH_PARTIAL_MATCH",
        },
        "verification": verification,
        "verified_identity": {
            "name": verified_name,
        },
        "xai": {
            "conclusion": (
                "Identity assessment was derived by "
                "comparing the authorized DigiLocker "
                "identity response with the NETRA person."
            ),
            "field_comparisons": [
                {
                    "field": "FullName",
                    "police_value": police_name,
                    "digilocker_value": verified_name,
                    "similarity": similarity,
                    "matched": (
                        bool(verified_name)
                        and similarity >= 0.95
                    ),
                }
            ],
            "limitations": [
                "Only fields actually returned by the "
                "authorized DigiLocker response are compared.",
                "No identity field is fabricated when the "
                "provider does not return it.",
                "A name match alone does not prove that two "
                "people are the same person.",
            ],
        },
    }


# ---------------------------------------------------------------------
# STORED VERIFICATION
# ---------------------------------------------------------------------

def get_verification(
    case_id: int,
    person_id: int,
) -> dict[str, Any] | None:

    return get_latest_verification(
        case_id,
        person_id,
    )


# ---------------------------------------------------------------------
# LEGACY DEMO FUNCTION
# ---------------------------------------------------------------------

def verify_demo(
    person_id: int,
) -> dict[str, Any]:

    person = _get_person(person_id)

    if not person:
        raise ValueError(
            "Person not found"
        )

    return {
        "provider": "DigiLocker",
        "mode": mode(),
        "authorization": "DEMO_AUTHORIZED",
        "document": _synthetic_document(
            person
        ),
        "audit": {
            "event": "DEMO_VERIFICATION_COMPLETED",
            "person_id": person_id,
        },
    }