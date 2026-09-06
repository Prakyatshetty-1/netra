"""
Dynamic PHONE entity resolution for NETRA.

A PHONE graph node may come from:

1. Structured PhoneNumber.PhoneID
2. Older PDF-upload graph data where the graph ID was
   incorrectly stored as an EvidenceIndependenceGroup.GroupID

This module resolves either representation dynamically
for ANY case.
"""

from __future__ import annotations

import re
from typing import Any

from backend.db import query, query_one


PHONE_RE = re.compile(r"\b[6-9]\d{9}\b")


def normalize_phone(value: Any) -> str:
    """
    Normalize an Indian phone number to its last 10 digits.

    Handles:
        9880134567
        +919880134567
        919880134567
        spaces / hyphens / parentheses
    """

    if value is None:
        return ""

    digits = re.sub(
        r"\D",
        "",
        str(value),
    )

    if len(digits) > 10 and digits.endswith(
        digits[-10:]
    ):
        digits = digits[-10:]

    if len(digits) == 10:
        return digits

    return digits


def _is_phone_number(value: Any) -> bool:
    normalized = normalize_phone(value)

    return bool(
        PHONE_RE.fullmatch(normalized)
    )


def _find_structured_phone(
    phone_id: int,
) -> dict[str, Any] | None:
    """
    Direct lookup in the structured PhoneNumber table.
    """

    row = query_one(
        """
        SELECT
            PhoneID,
            PersonID,
            PhoneNumber,
            IsPrimary
        FROM PhoneNumber
        WHERE PhoneID = ?
        """,
        (phone_id,),
    )

    if not row:
        return None

    return dict(row)


def _find_pdf_phone_evidence(
    case_id: int,
    graph_phone_id: int,
) -> list[dict[str, Any]]:
    """
    Resolve a legacy PDF PHONE graph ID.

    Older extraction data used:

        GraphEdge.TargetEntityID
            =
        EvidenceIndependenceGroup.GroupID

    The actual phone number is stored in:

        EvidenceIndependenceGroup.EventDescription
    """

    rows = query(
        """
        SELECT
            ge.EdgeID,
            ge.SourceEntityID AS PersonID,
            ge.TargetEntityID AS GraphPhoneID,
            ge.RelationType,
            ge.SourceType,
            eig.GroupID,
            eig.EventDescription AS PhoneNumber
        FROM GraphEdge ge
        INNER JOIN EvidenceIndependenceGroup eig
            ON eig.GroupID = ge.TargetEntityID
        WHERE ge.CaseMasterID = ?
          AND ge.TargetEntityType = 'PHONE'
          AND ge.TargetEntityID = ?
          AND ge.RelationType = 'HAS_PHONE'
          AND eig.EventDescription IS NOT NULL
        ORDER BY ge.EdgeID
        """,
        (
            case_id,
            graph_phone_id,
        ),
    )

    result = []

    for row in rows:

        phone_number = str(
            row["PhoneNumber"] or ""
        ).strip()

        if not _is_phone_number(
            phone_number
        ):
            continue

        result.append(
            dict(row)
        )

    return result


def _find_phone_records_by_number(
    phone_number: str,
) -> list[dict[str, Any]]:
    """
    Find every structured PhoneNumber record carrying
    the same normalized phone number.
    """

    normalized = normalize_phone(
        phone_number
    )

    if not normalized:
        return []

    rows = query(
        """
        SELECT
            PhoneID,
            PersonID,
            PhoneNumber,
            IsPrimary
        FROM PhoneNumber
        """,
    )

    matches = []

    for row in rows:

        row_number = normalize_phone(
            row["PhoneNumber"]
        )

        if row_number == normalized:

            matches.append(
                dict(row)
            )

    return matches


def resolve_phone_node(
    case_id: int,
    graph_phone_id: int,
) -> dict[str, Any]:
    """
    Dynamically resolve ANY PHONE graph node.

    Resolution order:

    1. Treat graph_phone_id as a real PhoneID.
    2. If not found, treat it as a legacy PDF evidence ID.
    3. Extract the actual phone number from evidence.
    4. Find matching structured PhoneNumber records.
    5. Return all linked people.

    No case ID or phone ID is hardcoded.
    """

    graph_phone_id = int(
        graph_phone_id
    )

    # ========================================================
    # 1. NORMAL STRUCTURED PHONE
    # ========================================================

    direct = _find_structured_phone(
        graph_phone_id
    )

    if direct:

        phone_number = str(
            direct["PhoneNumber"]
        )

        records = _find_phone_records_by_number(
            phone_number
        )

        if not records:
            records = [direct]

        person_ids = sorted(
            {
                int(row["PersonID"])
                for row in records
                if row.get("PersonID") is not None
            }
        )

        return {
            "graph_phone_id": graph_phone_id,
            "resolved": True,
            "resolution_type": "STRUCTURED_PHONE_ID",
            "phone_id": int(
                direct["PhoneID"]
            ),
            "phone_number": phone_number,
            "normalized_phone": normalize_phone(
                phone_number
            ),
            "records": records,
            "person_ids": person_ids,
            "evidence": [],
        }

    # ========================================================
    # 2. LEGACY / PDF PHONE
    # ========================================================

    evidence = _find_pdf_phone_evidence(
        case_id,
        graph_phone_id,
    )

    if not evidence:

        raise ValueError(
            f"PHONE graph entity {graph_phone_id} "
            f"could not be resolved for case {case_id}."
        )

    # Multiple graph edges can point to the same
    # PDF phone entity. Deduplicate the numbers.
    numbers = []

    seen_numbers = set()

    for item in evidence:

        normalized = normalize_phone(
            item["PhoneNumber"]
        )

        if (
            normalized
            and normalized not in seen_numbers
        ):

            seen_numbers.add(
                normalized
            )

            numbers.append(
                item["PhoneNumber"]
            )

    if not numbers:

        raise ValueError(
            f"PHONE graph entity {graph_phone_id} "
            "contains no valid phone number evidence."
        )

    # ========================================================
    # 3. FIND STRUCTURED PHONE RECORDS
    # ========================================================

    all_records = []

    for number in numbers:

        matches = _find_phone_records_by_number(
            number
        )

        for match in matches:

            if not any(
                int(existing["PhoneID"])
                == int(match["PhoneID"])
                for existing in all_records
            ):

                all_records.append(
                    match
                )

    # ========================================================
    # 4. PERSON-AWARE FALLBACK
    # ========================================================

    evidence_person_ids = sorted(
        {
            int(item["PersonID"])
            for item in evidence
            if item.get("PersonID") is not None
        }
    )

    # If the same phone number exists for multiple
    # people, prefer records associated with the
    # person(s) appearing in the selected case.
    preferred_records = [
        record
        for record in all_records
        if int(record["PersonID"])
        in evidence_person_ids
    ]

    if preferred_records:

        records = preferred_records

    else:

        records = all_records

    if not records:

        raise ValueError(
            "The PDF contains the phone number, but "
            "no structured PhoneNumber record exists "
            "for that number yet."
        )

    # ========================================================
    # 5. ACTUAL PHONE ID
    # ========================================================

    phone_id = int(
        records[0]["PhoneID"]
    )

    phone_number = str(
        records[0]["PhoneNumber"]
    )

    person_ids = sorted(
        {
            int(record["PersonID"])
            for record in records
            if record.get("PersonID") is not None
        }
    )

    return {
        "graph_phone_id": graph_phone_id,
        "resolved": True,
        "resolution_type": "PDF_EVIDENCE_TO_PHONE",
        "phone_id": phone_id,
        "phone_number": phone_number,
        "normalized_phone": normalize_phone(
            phone_number
        ),
        "records": records,
        "person_ids": person_ids,
        "evidence": evidence,
    }