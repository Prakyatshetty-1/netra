"""
NETRA DigiLocker integration service.

This service supports two modes:

1. mock
   Used for local development/demo.
   No real DigiLocker account is contacted.

2. production
   Uses the DigiLocker OAuth authorization-code flow.
   Real credentials must be supplied through environment variables.

The production integration must only be enabled after the organization
has completed the appropriate DigiLocker/API Setu Requester onboarding.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from rapidfuzz.fuzz import ratio

from backend.db import query
from backend.identity_store import (
    get_latest_verification,
    save_verification,
)


# ---------------------------------------------------------------------
# DigiLocker endpoints
# ---------------------------------------------------------------------

DIGILOCKER_AUTHORIZE_URL = (
    "https://api.digitallocker.gov.in/public/oauth2/1/authorize"
)

DIGILOCKER_TOKEN_URL = (
    "https://api.digitallocker.gov.in/public/oauth2/1/token"
)

DIGILOCKER_USER_URL = (
    "https://api.digitallocker.gov.in/public/oauth2/1/user"
)


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

def mode() -> str:
    """
    Return the configured DigiLocker mode.

    Default:
        mock

    This makes the project safe to run locally before real credentials
    are configured.
    """

    return os.getenv(
        "DIGILOCKER_MODE",
        "mock",
    ).lower()


def client_id() -> str:
    """
    Return the DigiLocker OAuth client ID.
    """

    return os.getenv(
        "DIGILOCKER_CLIENT_ID",
        "",
    )


def client_secret() -> str:
    """
    Return the DigiLocker OAuth client secret.
    """

    return os.getenv(
        "DIGILOCKER_CLIENT_SECRET",
        "",
    )


def redirect_uri() -> str:
    """
    OAuth callback URL.
    """

    return os.getenv(
        "DIGILOCKER_REDIRECT_URI",
        "http://localhost:8000/auth/digilocker/callback",
    )


def frontend_url() -> str:
    """
    NETRA frontend URL.
    """

    return os.getenv(
        "NETRA_FRONTEND_URL",
        "http://localhost:5173",
    )


def hmac_secret() -> bytes:
    """
    Secret used to derive a deterministic HMAC identity anchor.

    The raw DigiLocker identifier is never stored in the database.
    """

    secret = os.getenv(
        "NETRA_IDENTITY_HMAC_SECRET",
        "CHANGE_THIS_SECRET_BEFORE_PRODUCTION",
    )

    return secret.encode("utf-8")


# ---------------------------------------------------------------------
# Privacy-preserving identity anchor
# ---------------------------------------------------------------------

def hash_subject(digilocker_id: str) -> str:
    """
    Convert the DigiLocker subject identifier into a deterministic HMAC.

    The resulting value can be used to recognize the same DigiLocker
    identity without storing the raw identifier in this table.
    """

    return hmac.new(
        hmac_secret(),
        digilocker_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------
# OAuth PKCE
# ---------------------------------------------------------------------

def create_pkce_pair() -> tuple[str, str]:
    """
    Generate OAuth PKCE verifier and S256 challenge.
    """

    verifier = secrets.token_urlsafe(64)

    digest = hashlib.sha256(
        verifier.encode("utf-8")
    ).digest()

    challenge = (
        base64.urlsafe_b64encode(digest)
        .decode("utf-8")
        .rstrip("=")
    )

    return verifier, challenge


# ---------------------------------------------------------------------
# NETRA person lookup
# ---------------------------------------------------------------------

def get_person(
    case_id: int,
    person_id: int,
) -> dict | None:
    """
    Verify that the selected PERSON actually belongs to the selected
    NETRA case.
    """

    rows = query(
        """
        SELECT
            PersonID,
            FullName,
            SourceRole,
            CaseMasterID,
            AgeYear,
            GenderID
        FROM Person
        WHERE PersonID = ?
          AND CaseMasterID = ?
        """,
        (
            person_id,
            case_id,
        ),
    )

    if not rows:
        return None

    return rows[0]


# ---------------------------------------------------------------------
# OAuth authorization URL
# ---------------------------------------------------------------------

def build_authorization_url(
    *,
    case_id: int,
    person_id: int,
    state: str,
    code_challenge: str,
) -> str:
    """
    Construct the DigiLocker authorization URL.
    """

    params = {
        "response_type": "code",

        "client_id": client_id(),

        "redirect_uri": redirect_uri(),

        "state": state,

        "code_challenge": code_challenge,

        "code_challenge_method": "S256",

        "purpose": "verification",
    }

    return (
        f"{DIGILOCKER_AUTHORIZE_URL}"
        f"?{urlencode(params)}"
    )


# ---------------------------------------------------------------------
# OAuth token exchange
# ---------------------------------------------------------------------

async def exchange_code(
    code: str,
    code_verifier: str,
) -> dict:
    """
    Exchange the OAuth authorization code for an access token.
    """

    data = {
        "code": code,

        "grant_type": "authorization_code",

        "client_id": client_id(),

        "client_secret": client_secret(),

        "redirect_uri": redirect_uri(),

        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient(
        timeout=30
    ) as client:

        response = await client.post(
            DIGILOCKER_TOKEN_URL,
            data=data,
        )

    response.raise_for_status()

    return response.json()


# ---------------------------------------------------------------------
# DigiLocker user details
# ---------------------------------------------------------------------

async def get_user_details(
    access_token: str,
) -> dict:
    """
    Retrieve the authorized DigiLocker user details.
    """

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    async with httpx.AsyncClient(
        timeout=30
    ) as client:

        response = await client.get(
            DIGILOCKER_USER_URL,
            headers=headers,
        )

    response.raise_for_status()

    return response.json()


# ---------------------------------------------------------------------
# Identity comparison
# ---------------------------------------------------------------------

def compare_identity(
    local_person: dict,
    digilocker_user: dict,
) -> tuple[float, float]:
    """
    Compare the NETRA person's name with the verified DigiLocker name.

    Returns:

        name_similarity
        verification_confidence
    """

    local_name = (
        local_person.get("FullName") or ""
    ).strip()

    verified_name = (
        digilocker_user.get("name") or ""
    ).strip()

    if not local_name or not verified_name:

        return 0.0, 0.0

    name_similarity = (
        ratio(
            local_name.lower(),
            verified_name.lower(),
        )
        / 100.0
    )

    # Prototype scoring.
    #
    # Production should incorporate only additional attributes
    # that are legally authorized and actually available.
    #
    # DigiLocker verification is treated as strong evidence,
    # but not as an automatic criminal-person merge.

    if name_similarity >= 0.95:

        confidence = 0.99

    elif name_similarity >= 0.90:

        confidence = 0.96

    elif name_similarity >= 0.80:

        confidence = 0.90

    else:

        confidence = 0.60

    return (
        name_similarity,
        confidence,
    )


# ---------------------------------------------------------------------
# MOCK MODE
# ---------------------------------------------------------------------

def create_mock_verification(
    case_id: int,
    person_id: int,
) -> dict:
    """
    Create a local demonstration verification.

    IMPORTANT:

    This does NOT contact DigiLocker.

    It exists so that the complete NETRA UI/backend flow can be
    developed and demonstrated before official credentials are
    available.
    """

    person = get_person(
        case_id,
        person_id,
    )

    if not person:

        raise ValueError(
            "Person does not belong to this case."
        )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    # Deterministic fake identifier.
    #
    # This is deliberately marked as a demo identity and must never
    # be interpreted as a real DigiLocker identifier.

    fake_subject = (
        f"NETRA-DEMO-DIGILOCKER-{person_id}"
    )

    subject_hash = hash_subject(
        fake_subject
    )

    save_verification(
        case_id=case_id,

        person_id=person_id,

        subject_hash=subject_hash,

        verified_name=person["FullName"],

        name_similarity=1.0,

        verification_confidence=0.99,

        verification_status="VERIFIED_DEMO",

        consent_valid_till=None,

        scope="mock.identity",

        verified_at=now,

        source="DIGILOCKER_MOCK",
    )

    return {
        "case_id": case_id,

        "person_id": person_id,

        "status": "VERIFIED_DEMO",

        "verified_name": person["FullName"],

        "name_similarity": 1.0,

        "confidence": 0.99,

        "source": "DIGILOCKER_MOCK",

        "verified_at": now,

        "message": (
            "Demo verification only. "
            "No real DigiLocker account was accessed."
        ),
    }


# ---------------------------------------------------------------------
# REAL DigiLocker result processing
# ---------------------------------------------------------------------

def process_real_user(
    *,
    case_id: int,
    person_id: int,
    token_response: dict,
    user_response: dict,
) -> dict:
    """
    Process a real DigiLocker verification response.
    """

    person = get_person(
        case_id,
        person_id,
    )

    if not person:

        raise ValueError(
            "Person does not belong to this case."
        )

    digilocker_id = (
        user_response.get(
            "digilockerid"
        )
    )

    if not digilocker_id:

        raise ValueError(
            "DigiLocker response did not contain "
            "a DigiLocker identity identifier."
        )

    name_similarity, confidence = (
        compare_identity(
            person,
            user_response,
        )
    )

    if confidence >= 0.95:

        status = "VERIFIED"

    elif confidence >= 0.80:

        status = "PARTIAL_MATCH"

    else:

        status = "MISMATCH"

    now = datetime.now(
        timezone.utc
    ).isoformat()

    save_verification(
        case_id=case_id,

        person_id=person_id,

        subject_hash=hash_subject(
            digilocker_id
        ),

        verified_name=user_response.get(
            "name"
        ),

        name_similarity=name_similarity,

        verification_confidence=confidence,

        verification_status=status,

        consent_valid_till=token_response.get(
            "consent_valid_till"
        ),

        scope=token_response.get(
            "scope"
        ),

        verified_at=now,

        source="DIGILOCKER",
    )

    return {
        "case_id": case_id,

        "person_id": person_id,

        "status": status,

        "verified_name": user_response.get(
            "name"
        ),

        "name_similarity": round(
            name_similarity,
            3,
        ),

        "confidence": round(
            confidence,
            3,
        ),

        "consent_valid_till": token_response.get(
            "consent_valid_till"
        ),

        "scope": token_response.get(
            "scope"
        ),

        "verified_at": now,

        "source": "DIGILOCKER",
    }


# ---------------------------------------------------------------------
# Existing verification
# ---------------------------------------------------------------------

def get_verification(
    case_id: int,
    person_id: int,
) -> dict | None:
    """
    Return the most recent DigiLocker verification.
    """

    return get_latest_verification(
        case_id,
        person_id,
    )