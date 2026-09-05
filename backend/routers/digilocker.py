"""
NETRA DigiLocker API routes.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from backend.services.digilocker_service import (
    build_authorization_url,
    create_mock_verification,
    create_pkce_pair,
    exchange_code,
    frontend_url,
    get_verification,
    get_user_details,
    mode,
    process_real_user,
)


router = APIRouter(
    tags=["digilocker"]
)


# ---------------------------------------------------------------------
# Temporary OAuth session storage
# ---------------------------------------------------------------------
#
# This is acceptable for local development.
#
# For production, replace this with a short-lived server-side session
# store such as Redis or another secure session mechanism.
#

oauth_sessions: dict[str, dict] = {}


# ---------------------------------------------------------------------
# START VERIFICATION
# ---------------------------------------------------------------------

@router.get(
    "/cases/{case_id}/persons/{person_id}/digilocker/start"
)
def start_digilocker(
    case_id: int,
    person_id: int,
):
    """
    Start DigiLocker verification.

    In mock mode this tells the frontend to use the local demo flow.

    In production mode this returns the real DigiLocker authorization
    URL.
    """

    # -------------------------------------------------------------
    # MOCK MODE
    # -------------------------------------------------------------

    if mode() == "mock":

        return {
            "mode": "mock",

            "authorization_url": None,

            "case_id": case_id,

            "person_id": person_id,
        }

    # -------------------------------------------------------------
    # PRODUCTION MODE
    # -------------------------------------------------------------

    state = secrets.token_urlsafe(
        32
    )

    code_verifier, code_challenge = (
        create_pkce_pair()
    )

    oauth_sessions[state] = {
        "case_id": case_id,

        "person_id": person_id,

        "code_verifier": code_verifier,
    }

    authorization_url = (
        build_authorization_url(
            case_id=case_id,

            person_id=person_id,

            state=state,

            code_challenge=code_challenge,
        )
    )

    return {
        "mode": "production",

        "authorization_url":
            authorization_url,

        "case_id": case_id,

        "person_id": person_id,
    }


# ---------------------------------------------------------------------
# OAUTH CALLBACK
# ---------------------------------------------------------------------

@router.get(
    "/auth/digilocker/callback"
)
async def digilocker_callback(
    code: str | None = None,

    state: str | None = None,

    error: str | None = None,

    error_description: str | None = None,
):
    """
    DigiLocker OAuth callback.

    DigiLocker redirects the browser here after authorization.
    """

    # -------------------------------------------------------------
    # USER DENIED / AUTHORIZATION ERROR
    # -------------------------------------------------------------

    if error:

        return HTMLResponse(
            f"""
<!DOCTYPE html>
<html>
<head>
    <title>NETRA DigiLocker</title>
</head>

<body>

    <p>
        DigiLocker authorization was not completed.
    </p>

    <script>

        if (window.opener) {{

            window.opener.postMessage(
                {{
                    type: "DIGILOCKER_ERROR",

                    error: {error!r},

                    description:
                        {error_description!r}
                }},

                "*"
            );

            window.close();

        }}

    </script>

</body>
</html>
"""
        )

    # -------------------------------------------------------------
    # MISSING CALLBACK PARAMETERS
    # -------------------------------------------------------------

    if not code or not state:

        raise HTTPException(
            status_code=400,

            detail=(
                "Missing DigiLocker authorization "
                "code or state."
            ),
        )

    # -------------------------------------------------------------
    # VALIDATE OAUTH STATE
    # -------------------------------------------------------------

    session = oauth_sessions.pop(
        state,
        None,
    )

    if not session:

        raise HTTPException(
            status_code=400,

            detail=(
                "Invalid or expired DigiLocker "
                "OAuth state."
            ),
        )

    # -------------------------------------------------------------
    # EXCHANGE AUTHORIZATION CODE
    # -------------------------------------------------------------

    token_response = (
        await exchange_code(
            code=code,

            code_verifier=session[
                "code_verifier"
            ],
        )
    )

    access_token = (
        token_response.get(
            "access_token"
        )
    )

    if not access_token:

        raise HTTPException(
            status_code=502,

            detail=(
                "DigiLocker did not return "
                "an access token."
            ),
        )

    # -------------------------------------------------------------
    # GET VERIFIED USER INFORMATION
    # -------------------------------------------------------------

    user_response = (
        await get_user_details(
            access_token
        )
    )

    # -------------------------------------------------------------
    # PROCESS IDENTITY
    # -------------------------------------------------------------

    result = process_real_user(
        case_id=session["case_id"],

        person_id=session["person_id"],

        token_response=token_response,

        user_response=user_response,
    )

    # -------------------------------------------------------------
    # SEND RESULT BACK TO FRONTEND
    # -------------------------------------------------------------

    payload = urlencode(
        {
            "case_id":
                result["case_id"],

            "person_id":
                result["person_id"],

            "status":
                result["status"],
        }
    )

    return HTMLResponse(
        f"""
<!DOCTYPE html>

<html>

<head>

    <title>
        NETRA DigiLocker Verification
    </title>

</head>

<body>

    <p>
        DigiLocker verification completed.
        You may close this window.
    </p>

    <script>

        const result = {result!r};

        if (window.opener) {{

            window.opener.postMessage(
                {{
                    type:
                        "DIGILOCKER_SUCCESS",

                    result:
                        result
                }},

                "*"
            );

            window.close();

        }} else {{

            window.location.href =
                "{frontend_url()}/?digilocker={payload}";

        }}

    </script>

</body>

</html>
"""
    )


# ---------------------------------------------------------------------
# MOCK VERIFICATION
# ---------------------------------------------------------------------

@router.post(
    "/cases/{case_id}/persons/{person_id}/digilocker/mock-verify"
)
def mock_verify(
    case_id: int,
    person_id: int,
):
    """
    Perform a fake local DigiLocker verification.

    This endpoint is available ONLY in mock mode.
    """

    if mode() != "mock":

        raise HTTPException(
            status_code=403,

            detail=(
                "Mock DigiLocker verification "
                "is disabled."
            ),
        )

    try:

        return create_mock_verification(
            case_id,

            person_id,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=404,

            detail=str(exc),
        )


# ---------------------------------------------------------------------
# GET STORED VERIFICATION
# ---------------------------------------------------------------------

@router.get(
    "/cases/{case_id}/persons/{person_id}/digilocker"
)
def get_digilocker_verification(
    case_id: int,
    person_id: int,
):
    """
    Return the latest DigiLocker verification
    for a NETRA person.
    """

    result = get_verification(
        case_id,

        person_id,
    )

    if not result:

        return {
            "verified": False,

            "verification": None,
        }

    return {
        "verified": True,

        "verification": result,
    }