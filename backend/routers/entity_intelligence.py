from fastapi import APIRouter, HTTPException

from backend.db import query_one

from backend.services.entity_intelligence_service import (
    person_profile,
    phone_intelligence,
    account_intelligence,
)

from backend.services.phone_resolution_service import (
    resolve_phone_node,
)

from backend.services.xai_service import (
    field_match,
)

from backend.identity_store import (
    get_latest_verification,
)


router = APIRouter(
    prefix="/cases",
    tags=["entity-intelligence"],
)


# ============================================================
# POLICE IDENTITY
# ============================================================

def _police_identity(
    person_id: int,
) -> dict:

    person = query_one(
        """
        SELECT
            p.PersonID,
            p.FullName,
            p.AgeYear,
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

    if not person:

        raise HTTPException(
            status_code=404,
            detail="Person not found.",
        )

    phone = query_one(
        """
        SELECT
            PhoneNumber
        FROM PhoneNumber
        WHERE PersonID = ?
        ORDER BY
            IsPrimary DESC,
            PhoneID
        LIMIT 1
        """,
        (person_id,),
    )

    return {
        "person_id": person["PersonID"],
        "name": person["FullName"],
        "date_of_birth": None,
        "phone": (
            phone["PhoneNumber"]
            if phone
            else None
        ),
        "place": (
            person["DistrictName"]
            or person["UnitName"]
            or person["StateName"]
        ),
        "age_year": person["AgeYear"],
        "case_id": person["CaseMasterID"],
        "source": "NETRA_POLICE_EVIDENCE",
    }


# ============================================================
# PERSON INTELLIGENCE
# ============================================================

@router.get(
    "/{case_id}/persons/{person_id}/intelligence"
)
def get_person_intelligence(
    case_id: int,
    person_id: int,
):

    try:

        data = person_profile(
            person_id
        )

        person_case_id = data[
            "person"
        ]["CaseMasterID"]

        connected_cases = data.get(
            "cases",
            [],
        )

        connected = any(
            int(item["case_id"])
            == int(case_id)
            for item in connected_cases
        )

        if (
            int(person_case_id)
            != int(case_id)
            and not connected
        ):

            raise HTTPException(
                status_code=404,
                detail=(
                    "Person is not connected "
                    "to this case."
                ),
            )

        return data

    except HTTPException:
        raise

    except ValueError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )


# ============================================================
# PHONE INTELLIGENCE
# ============================================================

@router.get(
    "/{case_id}/phones/{phone_id}/intelligence"
)
def get_phone_intelligence(
    case_id: int,
    phone_id: int,
):

    try:

        # ====================================================
        # DYNAMIC RESOLUTION
        # ====================================================

        resolution = resolve_phone_node(
            case_id=case_id,
            graph_phone_id=phone_id,
        )

        actual_phone_id = int(
            resolution["phone_id"]
        )

        # ====================================================
        # EXISTING INTELLIGENCE SERVICE
        # ====================================================

        data = phone_intelligence(
            case_id,
            actual_phone_id,
        )

        # ====================================================
        # ENTITY RESOLUTION METADATA
        # ====================================================

        data["entity_resolution"] = {
            "requested_graph_entity_id": int(
                phone_id
            ),
            "resolved_phone_id": actual_phone_id,
            "phone_number": resolution[
                "phone_number"
            ],
            "resolution_type": resolution[
                "resolution_type"
            ],
            "person_ids": resolution[
                "person_ids"
            ],
            "explainable_ai": {
                "summary": (
                    "NETRA dynamically resolved the "
                    "selected PHONE graph entity to "
                    "the corresponding phone-number "
                    "record before analysing its "
                    "associated people."
                ),
                "reason": (
                    "The graph identifier is treated "
                    "as an entity reference, not "
                    "automatically assumed to be a "
                    "PhoneNumber primary key."
                ),
            },
        }

        # ====================================================
        # PDF PROVENANCE
        # ====================================================

        if resolution[
            "resolution_type"
        ] == "PDF_EVIDENCE_TO_PHONE":

            data[
                "entity_resolution"
            ][
                "pdf_evidence"
            ] = resolution[
                "evidence"
            ]

            data[
                "entity_resolution"
            ][
                "explainable_ai"
            ][
                "pdf_resolution"
            ] = (
                "The selected PHONE node originated "
                "from PDF evidence. NETRA resolved "
                "its evidence-group identifier to "
                "the extracted phone number and then "
                "matched that number against the "
                "structured PhoneNumber records."
            )

        return data

    except ValueError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )


# ============================================================
# ACCOUNT INTELLIGENCE
# ============================================================

@router.get(
    "/{case_id}/accounts/{account_id}/intelligence"
)
def get_account_intelligence(
    case_id: int,
    account_id: int,
):

    try:

        return account_intelligence(
            case_id,
            account_id,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )


# ============================================================
# DIGILOCKER + XAI
# ============================================================

def _identity_comparison(
    case_id: int,
    person_id: int,
) -> dict:

    police = _police_identity(
        person_id
    )

    verification = get_latest_verification(
        case_id,
        person_id,
    )

    if not verification:

        return {
            "verified": False,
            "status": "NOT_VERIFIED",
            "police_evidence": police,
            "government_evidence": None,
            "field_comparison": [],
            "explainable_ai": {
                "summary": (
                    "No DigiLocker verification "
                    "is currently stored for this person."
                ),
                "reasons": [
                    (
                        "Government identity evidence "
                        "is not available."
                    ),
                    (
                        "Police-collected identity "
                        "remains unverified."
                    ),
                    (
                        "Run DigiLocker verification "
                        "after obtaining the required "
                        "authorization and consent."
                    ),
                ],
                "decision": (
                    "DO_NOT_TREAT_AS_GOVERNMENT_VERIFIED"
                ),
            },
        }

    verified_name = verification.get(
        "verified_name"
    )

    name_result = field_match(
        "name",
        police.get("name"),
        verified_name,
    )

    status = verification.get(
        "verification_status"
    )

    confidence = verification.get(
        "verification_confidence"
    )

    return {
        "verified": True,
        "status": status,
        "confidence": confidence,
        "police_evidence": police,
        "government_evidence": {
            "name": verified_name,
            "source": verification.get(
                "source"
            ),
            "verified_at": verification.get(
                "verified_at"
            ),
            "scope": verification.get(
                "scope"
            ),
            "consent_valid_till":
                verification.get(
                    "consent_valid_till"
                ),
        },
        "field_comparison": [
            name_result
        ],
        "explainable_ai": {
            "summary": (
                "The stored DigiLocker verification "
                "was compared with the police-collected "
                "identity record."
            ),
            "reasons": [
                (
                    "Name comparison uses the "
                    "government-verified name."
                ),
                (
                    "Verification confidence is "
                    "retained from the DigiLocker "
                    "verification process."
                ),
                (
                    "A DigiLocker verification is "
                    "an identity signal and must be "
                    "interpreted with the underlying "
                    "case evidence."
                ),
            ],
            "decision": (
                "REVIEW_WITH_CASE_EVIDENCE"
                if status != "VERIFIED"
                else
                "GOVERNMENT_IDENTITY_SIGNAL_AVAILABLE"
            ),
        },
    }


# ============================================================
# PERSON -> DIGILOCKER
# ============================================================

@router.get(
    "/{case_id}/persons/{person_id}/identity-comparison"
)
def compare_person_identity(
    case_id: int,
    person_id: int,
):

    return _identity_comparison(
        case_id,
        person_id,
    )


# ============================================================
# PHONE -> PERSON -> DIGILOCKER
# ============================================================

@router.get(
    "/{case_id}/phones/{phone_id}/identity-comparison/{person_id}"
)
def compare_phone_person_identity(
    case_id: int,
    phone_id: int,
    person_id: int,
):

    try:

        resolution = resolve_phone_node(
            case_id,
            phone_id,
        )

        actual_phone_id = int(
            resolution["phone_id"]
        )

        info = phone_intelligence(
            case_id,
            actual_phone_id,
        )

        persons = info.get(
            "persons",
            [],
        )

        if not any(
            int(person["PersonID"])
            == int(person_id)
            for person in persons
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "The selected person is not "
                    "associated with this phone."
                ),
            )

        result = _identity_comparison(
            case_id,
            person_id,
        )

        result[
            "entity_resolution"
        ] = {
            "entity_type": "PHONE",
            "requested_entity_id": phone_id,
            "resolved_phone_id": actual_phone_id,
            "phone_number": resolution[
                "phone_number"
            ],
            "resolved_person_id": person_id,
            "resolution_type": resolution[
                "resolution_type"
            ],
            "explainable_ai": {
                "summary": (
                    "The selected phone was dynamically "
                    "resolved to its phone-number record, "
                    "then to the selected NETRA Person. "
                    "DigiLocker verification is performed "
                    "against that person."
                ),
                "reason": (
                    "A phone number by itself is not "
                    "government identity proof."
                ),
            },
        }

        return result

    except HTTPException:
        raise

    except ValueError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )


# ============================================================
# ACCOUNT -> PERSON -> DIGILOCKER
# ============================================================

@router.get(
    "/{case_id}/accounts/{account_id}/identity-comparison/{person_id}"
)
def compare_account_person_identity(
    case_id: int,
    account_id: int,
    person_id: int,
):

    try:

        info = account_intelligence(
            case_id,
            account_id,
        )

        linked_person = info.get(
            "person"
        )

        if not linked_person:

            raise HTTPException(
                status_code=404,
                detail=(
                    "No person is linked to "
                    "this account."
                ),
            )

        if (
            int(linked_person["PersonID"])
            != int(person_id)
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "The selected person is not "
                    "the account's linked person."
                ),
            )

        result = _identity_comparison(
            case_id,
            person_id,
        )

        result[
            "entity_resolution"
        ] = {
            "entity_type": "ACCOUNT",
            "entity_id": account_id,
            "resolved_person_id": person_id,
            "explainable_ai": {
                "summary": (
                    "The bank account was first "
                    "resolved to its linked NETRA "
                    "Person entity. DigiLocker "
                    "verification is then performed "
                    "against that person."
                ),
                "reason": (
                    "A bank account association is "
                    "not by itself government "
                    "identity proof."
                ),
            },
        }

        return result

    except HTTPException:
        raise

    except ValueError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )