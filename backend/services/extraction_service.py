"""
PDF text -> entities -> same-sentence relations -> investigator confirmation.

Important:
- This module is dynamic and case-independent.
- PERSON nodes use Person.PersonID.
- PHONE nodes use PhoneNumber.PhoneID.
- VEHICLE nodes use VehicleRegistration.VehicleID when linked to a person.
- LOCATION / DATE / ORG remain evidence-group-backed graph entities.
- No case IDs, phone IDs, or person IDs are hardcoded.
- PHONE graph nodes created from HAS_PHONE relations always point to
  the real PhoneNumber.PhoneID, not EvidenceIndependenceGroup.GroupID.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

from rapidfuzz import fuzz, process

from backend.db import get_write_conn, query


# ---------------------------------------------------------------------------
# Extraction patterns
# ---------------------------------------------------------------------------

# Supports:
#   9880134567
#   +91 9880134567
#   +919880134567
#   91-9880134567
#   91 9880134567
#
# We normalize the value before saving it to PhoneNumber.
PHONE_RE = re.compile(
    r"(?<!\d)(?:(?:\+?91)[\s\-]?)?[6-9]\d{9}(?!\d)"
)

# Indian vehicle registration examples:
# KA01AB1234
# KA01A1234
PLATE_RE = re.compile(
    r"\b[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}\b",
    re.IGNORECASE,
)


# spaCy entity -> NETRA entity labels
SPACY_LABELS = {
    "PERSON": "PERSON",
    "GPE": "LOC",
    "LOC": "LOC",
    "DATE": "DATE",
    "ORG": "ORG",
}


# Same-sentence co-occurrence is only a draft relation signal.
# It is NOT a trained relation-extraction model.
RELATION_CONFIDENCE = 0.6

# Minimum fuzzy score for matching extracted names to an existing
# person belonging to the same case.
FUZZY_PERSON_THRESHOLD = 85


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    """
    Return a consistent UTC timestamp string for SQLite.
    """
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def normalize_phone_number(value: str | None) -> str:
    """
    Normalize an Indian phone number to a 10-digit representation.

    Examples:
        9880134567       -> 9880134567
        +91 9880134567   -> 9880134567
        +919880134567    -> 9880134567
        91-9880134567    -> 9880134567
        09880134567      -> 9880134567

    If the input cannot be confidently normalized to a valid Indian
    10-digit mobile number, the digits are returned as-is.
    """
    if not value:
        return ""

    raw = str(value).strip()

    # Remove common separators but retain digits.
    digits = re.sub(r"\D", "", raw)

    # +91 / 91 country-code form.
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]

    # Local number with leading zero.
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    # Return canonical 10-digit number if valid.
    if len(digits) == 10 and digits[0] in "6789":
        return digits

    return digits


def _phone_is_valid(value: str | None) -> bool:
    """
    Check whether a normalized value is a valid Indian mobile number.
    """
    normalized = normalize_phone_number(value)

    return bool(
        re.fullmatch(r"[6-9]\d{9}", normalized)
    )


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_text(pdf_bytes: bytes) -> tuple[str, bool, str | None]:
    """
    Return:
        (text, ocr_required, error_msg)

    Empty extractable text means OCR is required.

    OCR itself is intentionally not performed here. The existing application
    can use the ocr_required flag to route the document through an OCR layer.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        return (
            "",
            True,
            (
                f"Missing dependency: {exc.name}. "
                "Install with: pip install pdfplumber"
            ),
        )

    try:
        pages: list[str] = []

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                pages.append(page_text)

        text = "\n".join(pages).strip()

        return (
            text,
            not bool(text),
            None,
        )

    except Exception as exc:
        return (
            "",
            True,
            f"Unable to extract PDF text: {exc}",
        )


# ---------------------------------------------------------------------------
# NLP
# ---------------------------------------------------------------------------

def _load_nlp():
    """
    Load spaCy English model if available.

    The application still works without spaCy because the code falls back
    to lightweight rule-based extraction.
    """
    try:
        import spacy

        return spacy.load("en_core_web_sm")

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

def extract_entities(text: str) -> list[dict]:
    """
    Extract entities from PDF text.

    Supported entities:
        PERSON
        PHONE
        VEHICLE
        LOC
        DATE
        ORG

    spaCy provides the general NER layer while phone numbers and vehicle
    registrations are extracted with deterministic regex rules.
    """

    if not text:
        return []

    found: list[dict] = []

    # Avoid exact duplicate entity occurrences at the same location.
    seen: set[tuple[str, str, int]] = set()

    def add(
        raw: str,
        label: str,
        start: int,
    ) -> None:
        token = str(raw or "").strip()

        if not token:
            return

        key = (
            token.lower(),
            label,
            int(start),
        )

        if key in seen:
            return

        seen.add(key)

        found.append(
            {
                "text": token,
                "label": label,
                "start": int(start),
            }
        )

    # ---------------------------------------------------------------
    # spaCy entities
    # ---------------------------------------------------------------

    nlp = _load_nlp()

    if nlp is not None:
        try:
            doc = nlp(text)

            for ent in doc.ents:
                mapped = SPACY_LABELS.get(ent.label_)

                if mapped:
                    add(
                        ent.text,
                        mapped,
                        ent.start_char,
                    )

        except Exception:
            # Rule-based extraction below should still work.
            pass

    # ---------------------------------------------------------------
    # Phone numbers
    # ---------------------------------------------------------------

    for match in PHONE_RE.finditer(text):
        raw_phone = match.group(0)

        normalized_phone = normalize_phone_number(
            raw_phone
        )

        if _phone_is_valid(normalized_phone):
            add(
                normalized_phone,
                "PHONE",
                match.start(),
            )

    # ---------------------------------------------------------------
    # Vehicle registration numbers
    # ---------------------------------------------------------------

    for match in PLATE_RE.finditer(text):
        add(
            match.group(0).upper(),
            "VEHICLE",
            match.start(),
        )

    # ---------------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------------

    phones = {
        normalize_phone_number(e["text"])
        for e in found
        if e["label"] == "PHONE"
    }

    plates = {
        str(e["text"]).upper()
        for e in found
        if e["label"] == "VEHICLE"
    }

    cleaned: list[dict] = []

    for entity in found:

        # Avoid treating a phone number as a DATE if spaCy incorrectly
        # classified it as one.
        if entity["label"] == "DATE":
            normalized_date_candidate = normalize_phone_number(
                entity["text"]
            )

            if normalized_date_candidate in phones:
                continue

        # Avoid a PERSON entity that actually contains a vehicle number.
        if entity["label"] == "PERSON":
            entity_text_upper = entity["text"].upper()

            if any(
                plate in entity_text_upper
                for plate in plates
            ):
                continue

        cleaned.append(entity)

    return cleaned


# ---------------------------------------------------------------------------
# Relation extraction
# ---------------------------------------------------------------------------

def extract_relations(
    entities: list[dict],
    text: str,
) -> list[dict]:
    """
    Extract draft relations using same-sentence co-occurrence.

    Current relation types:
        NAMED_TOGETHER
        HAS_PHONE
        ASSOCIATED_WITH_VEHICLE
        MENTIONED_AT_LOCATION
        MENTIONED_ON_DATE

    These are investigator-reviewable draft relations.
    """

    if not text or not entities:
        return []

    nlp = _load_nlp()

    if nlp is not None:
        try:
            sentences = [
                sentence.text.strip()
                for sentence in nlp(text).sents
                if sentence.text.strip()
            ]
        except Exception:
            sentences = [
                part.strip()
                for part in re.split(
                    r"[.!?;\n]+",
                    text,
                )
                if part.strip()
            ]
    else:
        sentences = [
            part.strip()
            for part in re.split(
                r"[.!?;\n]+",
                text,
            )
            if part.strip()
        ]

    relations: list[dict] = []

    seen: set[
        tuple[str, str, str]
    ] = set()

    def add_rel(
        source: str,
        target: str,
        relation_type: str,
        sentence: str,
    ) -> None:

        source_clean = str(source or "").strip()
        target_clean = str(target or "").strip()

        if not source_clean or not target_clean:
            return

        key = (
            source_clean.lower(),
            target_clean.lower(),
            relation_type,
        )

        if (
            source_clean.lower()
            == target_clean.lower()
        ):
            return

        if key in seen:
            return

        seen.add(key)

        relations.append(
            {
                "source": source_clean,
                "target": target_clean,
                "type": relation_type,
                "confidence": RELATION_CONFIDENCE,
                "sentence": sentence[:240],
            }
        )

    for sentence in sentences:

        sentence_lower = sentence.lower()

        # Entities whose text appears in this sentence.
        in_sentence = [
            entity
            for entity in entities
            if entity.get("text")
            and entity["text"].lower()
            in sentence_lower
        ]

        persons = [
            entity
            for entity in in_sentence
            if entity.get("label") == "PERSON"
        ]

        others = [
            entity
            for entity in in_sentence
            if entity.get("label") != "PERSON"
        ]

        # -----------------------------------------------------------
        # PERSON -> PERSON
        # -----------------------------------------------------------

        for i, person_a in enumerate(persons):

            for person_b in persons[i + 1:]:

                add_rel(
                    person_a["text"],
                    person_b["text"],
                    "NAMED_TOGETHER",
                    sentence,
                )

            # -------------------------------------------------------
            # PERSON -> other entity
            # -------------------------------------------------------

            for other in others:

                label = other.get("label")

                if label == "PHONE":

                    add_rel(
                        person_a["text"],
                        normalize_phone_number(
                            other["text"]
                        ),
                        "HAS_PHONE",
                        sentence,
                    )

                elif label == "VEHICLE":

                    add_rel(
                        person_a["text"],
                        other["text"].upper(),
                        "ASSOCIATED_WITH_VEHICLE",
                        sentence,
                    )

                elif label == "LOC":

                    add_rel(
                        person_a["text"],
                        other["text"],
                        "MENTIONED_AT_LOCATION",
                        sentence,
                    )

                elif label == "DATE":

                    add_rel(
                        person_a["text"],
                        other["text"],
                        "MENTIONED_ON_DATE",
                        sentence,
                    )

                elif label == "ORG":

                    add_rel(
                        person_a["text"],
                        other["text"],
                        "NAMED_TOGETHER",
                        sentence,
                    )

    return relations


# ---------------------------------------------------------------------------
# Person resolution
# ---------------------------------------------------------------------------

def _match_or_create_person(
    cur,
    case_id: int,
    name: str,
) -> int:
    """
    Resolve an extracted person to an existing person in the same case.

    Resolution strategy:
        1. Exact case-local name.
        2. Fuzzy case-local name.
        3. Create a new Person row.

    No global person matching is performed here.
    """

    clean_name = str(name or "").strip()

    if not clean_name:
        raise ValueError(
            "Cannot create or resolve a person with an empty name."
        )

    # IMPORTANT:
    # Use the SAME write cursor instead of the global query() helper.
    # This avoids opening another SQLite connection while the transaction
    # is in progress.
    rows = cur.execute(
        """
        SELECT
            PersonID,
            FullName
        FROM Person
        WHERE CaseMasterID = ?
        """,
        (case_id,),
    ).fetchall()

    # ---------------------------------------------------------------
    # Exact match first
    # ---------------------------------------------------------------

    clean_lower = clean_name.lower()

    for row in rows:

        existing_name = str(
            row["FullName"] or ""
        ).strip()

        if existing_name.lower() == clean_lower:
            return int(row["PersonID"])

    # ---------------------------------------------------------------
    # Fuzzy match
    # ---------------------------------------------------------------

    if rows:

        choices = {
            str(row["PersonID"]): row["FullName"]
            for row in rows
            if row["FullName"]
        }

        if choices:

            match = process.extractOne(
                clean_name,
                choices,
                scorer=fuzz.WRatio,
            )

            if match:

                score = float(match[1])

                if score >= FUZZY_PERSON_THRESHOLD:
                    return int(match[2])

    # ---------------------------------------------------------------
    # Create new person
    # ---------------------------------------------------------------

    cur.execute(
        """
        INSERT INTO Person (
            FullName,
            SourceRole,
            SourceRecordID,
            CaseMasterID,
            AgeYear,
            GenderID
        )
        VALUES (
            ?,
            'EXTRACTED',
            0,
            ?,
            NULL,
            NULL
        )
        """,
        (
            clean_name,
            case_id,
        ),
    )

    return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# Evidence independence groups
# ---------------------------------------------------------------------------

def _insert_group(
    cur,
    case_id: int,
    description: str,
) -> int:
    """
    Create an EvidenceIndependenceGroup record.

    These groups are used for evidence provenance for entities that do not
    have a structured master-table ID.
    """

    cur.execute(
        """
        INSERT INTO EvidenceIndependenceGroup (
            CaseMasterID,
            EventDescription,
            EventDateTime
        )
        VALUES (
            ?,
            ?,
            ?
        )
        """,
        (
            case_id,
            str(description or "").strip(),
            _utc_now(),
        ),
    )

    return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# PHONE resolution / creation
# ---------------------------------------------------------------------------

def _find_person_phone(
    cur,
    person_id: int,
    phone_number: str,
):
    """
    Find a phone belonging specifically to this person.

    This is the preferred lookup because the same phone number may appear
    in multiple police records/person profiles.
    """

    normalized = normalize_phone_number(
        phone_number
    )

    rows = cur.execute(
        """
        SELECT
            PhoneID,
            PersonID,
            PhoneNumber,
            IsPrimary
        FROM PhoneNumber
        WHERE PersonID = ?
        """,
        (person_id,),
    ).fetchall()

    for row in rows:

        existing = normalize_phone_number(
            row["PhoneNumber"]
        )

        if existing == normalized:
            return row

    return None


def _create_or_get_phone_for_person(
    cur,
    person_id: int,
    phone_number: str,
) -> int:
    """
    Create/reuse a structured PhoneNumber record for a person.

    CRITICAL:
    The returned ID is PhoneNumber.PhoneID.

    This ID is what must be stored in GraphEdge.TargetEntityID for a PHONE
    node.

    We deliberately do NOT use EvidenceIndependenceGroup.GroupID here.
    """

    normalized = normalize_phone_number(
        phone_number
    )

    if not _phone_is_valid(normalized):
        raise ValueError(
            f"Invalid Indian phone number: {phone_number}"
        )

    # ---------------------------------------------------------------
    # First: phone already linked to this person?
    # ---------------------------------------------------------------

    existing = _find_person_phone(
        cur,
        person_id,
        normalized,
    )

    if existing:

        return int(
            existing["PhoneID"]
        )

    # ---------------------------------------------------------------
    # Second: same number may already exist for another person.
    #
    # We DO NOT blindly reuse another person's PhoneID because the
    # PhoneNumber table is person-linked and the graph association
    # should remain semantically correct.
    #
    # Therefore we create a person-specific PhoneNumber row.
    # ---------------------------------------------------------------

    cur.execute(
        """
        INSERT INTO PhoneNumber (
            PersonID,
            PhoneNumber,
            IsPrimary
        )
        VALUES (
            ?,
            ?,
            ?
        )
        """,
        (
            person_id,
            normalized,
            1,
        ),
    )

    return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# VEHICLE resolution / creation
# ---------------------------------------------------------------------------

def _create_or_get_vehicle_for_person(
    cur,
    person_id: int,
    registration_number: str,
) -> int:
    """
    Create/reuse a structured VehicleRegistration record.

    Returns VehicleRegistration.VehicleID.
    """

    registration = str(
        registration_number or ""
    ).strip().upper()

    if not registration:
        raise ValueError(
            "Cannot create a vehicle with an empty registration number."
        )

    # First try person-specific match.
    rows = cur.execute(
        """
        SELECT
            VehicleID,
            PersonID,
            RegistrationNumber,
            VehicleType
        FROM VehicleRegistration
        WHERE PersonID = ?
        """,
        (person_id,),
    ).fetchall()

    for row in rows:

        existing = str(
            row["RegistrationNumber"] or ""
        ).strip().upper()

        if existing == registration:
            return int(row["VehicleID"])

    # Create structured vehicle record.
    cur.execute(
        """
        INSERT INTO VehicleRegistration (
            PersonID,
            RegistrationNumber,
            VehicleType
        )
        VALUES (
            ?,
            ?,
            'Extracted'
        )
        """,
        (
            person_id,
            registration,
        ),
    )

    return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# Investigator confirmation / persistence
# ---------------------------------------------------------------------------

def confirm_extraction(
    case_id: int,
    entities: list[dict],
    relations: list[dict],
) -> dict:
    """
    Persist investigator-approved entities and relations.

    Dynamic entity mapping:

        PERSON
            -> Person.PersonID

        PHONE
            -> PhoneNumber.PhoneID

        VEHICLE
            -> VehicleRegistration.VehicleID

        LOCATION / DATE / ORG
            -> EvidenceIndependenceGroup.GroupID

    The most important rule is that HAS_PHONE relations are resolved
    through PhoneNumber before GraphEdge is inserted.

    This means new PDF uploads will NOT create:

        PERSON -> PHONE: EvidenceIndependenceGroup.GroupID

    Instead they create:

        PERSON -> PHONE: PhoneNumber.PhoneID
    """

    included_entities = [
        entity
        for entity in entities
        if entity.get("included", True)
    ]

    included_relations = [
        relation
        for relation in relations
        if relation.get("included", True)
    ]

    name_to_node: dict[
        tuple[str, str],
        tuple[str, int],
    ] = {}

    created: list[dict[str, Any]] = []

    conn = get_write_conn()

    try:

        cur = conn.cursor()

        # ===========================================================
        # PHASE 1
        # Create/resolve entity records.
        # ===========================================================

        for entity in included_entities:

            label = (
                str(
                    entity.get("label")
                    or "PERSON"
                )
                .strip()
                .upper()
            )

            text = str(
                entity.get("text")
                or ""
            ).strip()

            if not text:
                continue

            # Normalize phone text immediately.
            if label == "PHONE":
                text = normalize_phone_number(text)

                if not _phone_is_valid(text):
                    continue

            if label == "VEHICLE":
                text = text.upper()

            key = (
                text.lower(),
                label,
            )

            if key in name_to_node:
                continue

            # -------------------------------------------------------
            # PERSON
            # -------------------------------------------------------

            if label == "PERSON":

                person_id = _match_or_create_person(
                    cur,
                    case_id,
                    text,
                )

                name_to_node[key] = (
                    "PERSON",
                    person_id,
                )

                created.append(
                    {
                        "text": text,
                        "type": "PERSON",
                        "id": person_id,
                    }
                )

            # -------------------------------------------------------
            # PHONE
            #
            # IMPORTANT:
            # We cannot attach a PHONE to a person until HAS_PHONE
            # is processed because one phone entity may be associated
            # with one or more people.
            #
            # Therefore we temporarily store it as PHONE_PENDING.
            # -------------------------------------------------------

            elif label == "PHONE":

                name_to_node[key] = (
                    "PHONE_PENDING",
                    0,
                )

            # -------------------------------------------------------
            # VEHICLE
            #
            # Similar to PHONE, the person association is established
            # by ASSOCIATED_WITH_VEHICLE.
            # -------------------------------------------------------

            elif label == "VEHICLE":

                group_id = _insert_group(
                    cur,
                    case_id,
                    text,
                )

                name_to_node[key] = (
                    "VEHICLE_PENDING",
                    group_id,
                )

            # -------------------------------------------------------
            # LOCATION
            # -------------------------------------------------------

            elif label in (
                "LOC",
                "LOCATION",
            ):

                group_id = _insert_group(
                    cur,
                    case_id,
                    text,
                )

                name_to_node[key] = (
                    "LOCATION",
                    group_id,
                )

            # -------------------------------------------------------
            # DATE
            # -------------------------------------------------------

            elif label == "DATE":

                group_id = _insert_group(
                    cur,
                    case_id,
                    text,
                )

                name_to_node[key] = (
                    "DATE",
                    group_id,
                )

            # -------------------------------------------------------
            # ORG / unknown entity
            # -------------------------------------------------------

            else:

                group_id = _insert_group(
                    cur,
                    case_id,
                    text,
                )

                name_to_node[key] = (
                    "ORG",
                    group_id,
                )

        # ===========================================================
        # Entity resolver
        # ===========================================================

        def resolve(
            name: str,
            prefer: str | None = None,
        ) -> tuple[str, int] | None:

            clean_name = str(
                name or ""
            ).strip()

            if not clean_name:
                return None

            # Normalize phone before lookup.
            if prefer == "PHONE":
                clean_name = normalize_phone_number(
                    clean_name
                )

            name_lower = clean_name.lower()

            # -------------------------------------------------------
            # Preferred exact label match.
            # -------------------------------------------------------

            if prefer:

                hit = name_to_node.get(
                    (
                        name_lower,
                        prefer,
                    )
                )

                if hit:
                    return hit

                # Pending PHONE / VEHICLE entities are expected.
                if prefer == "PHONE":

                    pending = name_to_node.get(
                        (
                            name_lower,
                            "PHONE",
                        )
                    )

                    if pending:
                        return pending

                if prefer == "VEHICLE":

                    pending = name_to_node.get(
                        (
                            name_lower,
                            "VEHICLE",
                        )
                    )

                    if pending:
                        return pending

            # -------------------------------------------------------
            # Exact name match independent of label.
            # -------------------------------------------------------

            for (
                stored_name,
                stored_label,
            ), node in name_to_node.items():

                if stored_name == name_lower:

                    if prefer == "PHONE":
                        if stored_label in (
                            "PHONE",
                            "PHONE_PENDING",
                        ):
                            return node

                    elif prefer == "VEHICLE":
                        if stored_label in (
                            "VEHICLE",
                            "VEHICLE_PENDING",
                        ):
                            return node

                    else:
                        return node

            # -------------------------------------------------------
            # Existing person fallback.
            #
            # Only PERSON gets fuzzy matching because fuzzy matching
            # phone numbers/accounts would be unsafe.
            # -------------------------------------------------------

            if prefer == "PERSON" or prefer is None:

                existing_people = cur.execute(
                    """
                    SELECT
                        PersonID,
                        FullName
                    FROM Person
                    WHERE CaseMasterID = ?
                    """,
                    (case_id,),
                ).fetchall()

                if existing_people:

                    choices = {
                        str(row["PersonID"]): row["FullName"]
                        for row in existing_people
                        if row["FullName"]
                    }

                    if choices:

                        match = process.extractOne(
                            clean_name,
                            choices,
                            scorer=fuzz.WRatio,
                        )

                        if match:

                            score = float(match[1])

                            if score >= FUZZY_PERSON_THRESHOLD:

                                return (
                                    "PERSON",
                                    int(match[2]),
                                )

            return None

        # ===========================================================
        # PHASE 2
        # Persist relations.
        # ===========================================================

        now = _utc_now()

        edges_added = 0

        phone_edges_added = 0
        vehicle_edges_added = 0

        unresolved_relations: list[dict[str, Any]] = []

        for relation in included_relations:

            source_name = str(
                relation.get("source")
                or ""
            ).strip()

            target_name = str(
                relation.get("target")
                or ""
            ).strip()

            relation_type = str(
                relation.get("type")
                or "NAMED_TOGETHER"
            ).strip().upper()[:30]

            if not source_name or not target_name:
                unresolved_relations.append(
                    {
                        "relation": relation,
                        "reason": "Missing source or target",
                    }
                )
                continue

            # -------------------------------------------------------
            # PERSON source
            # -------------------------------------------------------

            source = resolve(
                source_name,
                "PERSON",
            )

            if not source:

                unresolved_relations.append(
                    {
                        "relation": relation,
                        "reason": (
                            f"Source person could not be resolved: "
                            f"{source_name}"
                        ),
                    }
                )

                continue

            # =======================================================
            # HAS_PHONE
            #
            # THIS IS THE CRITICAL FIX.
            #
            # We do NOT resolve the PHONE entity to an EvidenceGroup.
            # Instead:
            #
            #   1. normalize phone
            #   2. use source PersonID
            #   3. create/reuse PhoneNumber
            #   4. obtain PhoneNumber.PhoneID
            #   5. create GraphEdge using that PhoneID
            # =======================================================

            if relation_type == "HAS_PHONE":

                if source[0] != "PERSON":

                    unresolved_relations.append(
                        {
                            "relation": relation,
                            "reason": (
                                "HAS_PHONE source must be PERSON"
                            ),
                        }
                    )

                    continue

                normalized_phone = normalize_phone_number(
                    target_name
                )

                if not _phone_is_valid(
                    normalized_phone
                ):

                    unresolved_relations.append(
                        {
                            "relation": relation,
                            "reason": (
                                "Invalid phone number: "
                                f"{target_name}"
                            ),
                        }
                    )

                    continue

                # Create/reuse the REAL PhoneNumber row.
                phone_id = _create_or_get_phone_for_person(
                    cur,
                    int(source[1]),
                    normalized_phone,
                )

                # Update the entity map so subsequent references to
                # this phone resolve to the real PhoneID.
                name_to_node[
                    (
                        normalized_phone.lower(),
                        "PHONE",
                    )
                ] = (
                    "PHONE",
                    phone_id,
                )

                # Also update the original target text if necessary.
                name_to_node[
                    (
                        target_name.lower(),
                        "PHONE",
                    )
                ] = (
                    "PHONE",
                    phone_id,
                )

                target = (
                    "PHONE",
                    phone_id,
                )

            # =======================================================
            # ASSOCIATED_WITH_VEHICLE
            #
            # Similar structured resolution for vehicles.
            # =======================================================

            elif relation_type == "ASSOCIATED_WITH_VEHICLE":

                if source[0] != "PERSON":

                    unresolved_relations.append(
                        {
                            "relation": relation,
                            "reason": (
                                "Vehicle association source "
                                "must be PERSON"
                            ),
                        }
                    )

                    continue

                registration = (
                    target_name.strip().upper()
                )

                if not registration:

                    unresolved_relations.append(
                        {
                            "relation": relation,
                            "reason": (
                                "Empty vehicle registration"
                            ),
                        }
                    )

                    continue

                vehicle_id = _create_or_get_vehicle_for_person(
                    cur,
                    int(source[1]),
                    registration,
                )

                name_to_node[
                    (
                        registration.lower(),
                        "VEHICLE",
                    )
                ] = (
                    "VEHICLE",
                    vehicle_id,
                )

                target = (
                    "VEHICLE",
                    vehicle_id,
                )

            # =======================================================
            # LOCATION
            # =======================================================

            else:

                target_preference = {
                    "MENTIONED_AT_LOCATION": "LOCATION",
                    "MENTIONED_ON_DATE": "DATE",
                }.get(
                    relation_type
                )

                target = resolve(
                    target_name,
                    target_preference,
                )

                if not target:

                    unresolved_relations.append(
                        {
                            "relation": relation,
                            "reason": (
                                f"Target could not be resolved: "
                                f"{target_name}"
                            ),
                        }
                    )

                    continue

                # Convert pending vehicle nodes if encountered.
                if (
                    target[0] == "VEHICLE_PENDING"
                    and target_preference == "VEHICLE"
                ):
                    target = (
                        "VEHICLE",
                        target[1],
                    )

            # -------------------------------------------------------
            # Prevent self-relation.
            # -------------------------------------------------------

            if source == target:
                continue

            # -------------------------------------------------------
            # Confidence
            # -------------------------------------------------------

            try:
                confidence = float(
                    relation.get("confidence")
                    or RELATION_CONFIDENCE
                )
            except (
                TypeError,
                ValueError,
            ):
                confidence = RELATION_CONFIDENCE

            # Keep confidence within valid range.
            confidence = max(
                0.0,
                min(
                    1.0,
                    confidence,
                ),
            )

            # =======================================================
            # Insert GraphEdge
            # =======================================================

            cur.execute(
                """
                INSERT INTO GraphEdge (
                    CaseMasterID,
                    SourceEntityType,
                    SourceEntityID,
                    TargetEntityType,
                    TargetEntityID,
                    RelationType,
                    EventDateTime,
                    SourceType,
                    SourceRecordID,
                    ConfidenceScore,
                    IndependenceGroupID
                )
                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    'PDF_UPLOAD',
                    NULL,
                    ?,
                    NULL
                )
                """,
                (
                    case_id,
                    source[0],
                    source[1],
                    target[0],
                    target[1],
                    relation_type,
                    now,
                    confidence,
                ),
            )

            edges_added += 1

            if relation_type == "HAS_PHONE":
                phone_edges_added += 1

            if relation_type == "ASSOCIATED_WITH_VEHICLE":
                vehicle_edges_added += 1

        # ===========================================================
        # Commit
        # ===========================================================

        conn.commit()

        return {
            "created": created,
            "edges_added": edges_added,
            "phone_edges_added": phone_edges_added,
            "vehicle_edges_added": vehicle_edges_added,
            "unresolved_relations": unresolved_relations,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()