"""PDF text → entities → same-sentence relations (rule-based draft, not a trained RE model)."""

from __future__ import annotations

import io
import re
from datetime import datetime

from rapidfuzz import fuzz, process

from backend.db import get_write_conn, query

PHONE_RE = re.compile(r"\b[6-9]\d{9}\b")
PLATE_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}\b")

SPACY_LABELS = {"PERSON": "PERSON", "GPE": "LOC", "LOC": "LOC", "DATE": "DATE", "ORG": "ORG"}

RELATION_CONFIDENCE = 0.6  # naive same-sentence co-occurrence — not a trained model

FUZZY_PERSON_THRESHOLD = 85


def extract_text(pdf_bytes: bytes) -> tuple[str, bool, str | None]:
    """Return (text, ocr_required, error_msg). Empty extractable text → ocr_required True.
    Missing dependency → error_msg populated so caller can surface it."""
    try:
        import pdfplumber
    except ImportError as e:
        return "", True, f"Missing dependency: {e.name}. Install with: pip install pdfplumber"

    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\n".join(pages).strip()
    return text, (not bool(text)), None


def _load_nlp():
    try:
        import spacy

        return spacy.load("en_core_web_sm")
    except Exception:
        return None


def extract_entities(text: str) -> list[dict]:
    found: list[dict] = []
    seen: set[tuple[str, str, int]] = set()

    def add(raw: str, label: str, start: int):
        token = raw.strip()
        if not token:
            return
        key = (token.lower(), label, start)
        if key in seen:
            return
        seen.add(key)
        found.append({"text": token, "label": label, "start": start})

    nlp = _load_nlp()
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            mapped = SPACY_LABELS.get(ent.label_)
            if mapped:
                add(ent.text, mapped, ent.start_char)

    for m in PHONE_RE.finditer(text):
        add(m.group(0), "PHONE", m.start())
    for m in PLATE_RE.finditer(text):
        add(m.group(0), "VEHICLE", m.start())

    phones = {e["text"] for e in found if e["label"] == "PHONE"}
    plates = {e["text"] for e in found if e["label"] == "VEHICLE"}
    cleaned = []
    for e in found:
        if e["label"] == "DATE" and e["text"] in phones:
            continue
        if e["label"] == "PERSON" and any(p in e["text"] for p in plates):
            continue
        cleaned.append(e)
    return cleaned


def extract_relations(entities: list[dict], text: str) -> list[dict]:
    nlp = _load_nlp()
    if nlp is not None:
        sentences = [s.text.strip() for s in nlp(text).sents if s.text.strip()]
    else:
        sentences = [s.strip() for s in text.split(".") if s.strip()]

    relations: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add_rel(src: str, tgt: str, typ: str, sentence: str):
        key = (src.lower(), tgt.lower(), typ)
        if src.lower() == tgt.lower() or key in seen:
            return
        seen.add(key)
        relations.append(
            {
                "source": src,
                "target": tgt,
                "type": typ,
                "confidence": RELATION_CONFIDENCE,
                "sentence": sentence[:240],
            }
        )

    for sent in sentences:
        low = sent.lower()
        in_sent = [e for e in entities if e["text"] and e["text"].lower() in low]
        persons = [e for e in in_sent if e["label"] == "PERSON"]
        others = [e for e in in_sent if e["label"] != "PERSON"]

        for i, a in enumerate(persons):
            for b in persons[i + 1 :]:
                add_rel(a["text"], b["text"], "NAMED_TOGETHER", sent)
            for o in others:
                if o["label"] == "PHONE":
                    add_rel(a["text"], o["text"], "HAS_PHONE", sent)
                elif o["label"] == "VEHICLE":
                    add_rel(a["text"], o["text"], "ASSOCIATED_WITH_VEHICLE", sent)
                elif o["label"] == "LOC":
                    add_rel(a["text"], o["text"], "MENTIONED_AT_LOCATION", sent)
                elif o["label"] == "DATE":
                    add_rel(a["text"], o["text"], "MENTIONED_ON_DATE", sent)
                elif o["label"] == "ORG":
                    add_rel(a["text"], o["text"], "NAMED_TOGETHER", sent)

    return relations


def _match_or_create_person(cur, case_id: int, name: str) -> int:
    existing = query(
        "SELECT PersonID, FullName FROM Person WHERE CaseMasterID = ?",
        (case_id,),
    )
    if existing:
        choices = {str(r["PersonID"]): r["FullName"] for r in existing}
        match = process.extractOne(name, choices, scorer=fuzz.WRatio)
        if match and match[1] >= FUZZY_PERSON_THRESHOLD:
            return int(match[2])
    cur.execute(
        """
        INSERT INTO Person (FullName, SourceRole, SourceRecordID, CaseMasterID, AgeYear, GenderID)
        VALUES (?, 'EXTRACTED', 0, ?, NULL, NULL)
        """,
        (name, case_id),
    )
    return int(cur.lastrowid)


def _insert_group(cur, case_id: int, description: str) -> int:
    cur.execute(
        """
        INSERT INTO EvidenceIndependenceGroup (CaseMasterID, EventDescription, EventDateTime)
        VALUES (?, ?, ?)
        """,
        (case_id, description, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
    )
    return int(cur.lastrowid)


def confirm_extraction(case_id: int, entities: list[dict], relations: list[dict]) -> dict:
    """Persist investigator-approved entities/relations as Person + GraphEdge (SourceType=PDF_UPLOAD)."""
    included_e = [e for e in entities if e.get("included", True)]
    included_r = [r for r in relations if r.get("included", True)]

    name_to_node: dict[tuple[str, str], tuple[str, int]] = {}
    created = []

    conn = get_write_conn()
    try:
        cur = conn.cursor()
        for ent in included_e:
            label = (ent.get("label") or "PERSON").upper()
            text = (ent.get("text") or "").strip()
            if not text:
                continue
            key = (text.lower(), label)
            if key in name_to_node:
                continue
            if label == "PERSON":
                pid = _match_or_create_person(cur, case_id, text)
                name_to_node[key] = ("PERSON", pid)
                created.append({"text": text, "type": "PERSON", "id": pid})
            elif label == "PHONE":
                # Attach later if a HAS_PHONE relation exists; placeholder group node otherwise
                gid = _insert_group(cur, case_id, text)
                name_to_node[key] = ("PHONE", gid)
            elif label == "VEHICLE":
                gid = _insert_group(cur, case_id, text)
                name_to_node[key] = ("VEHICLE", gid)
            elif label in ("LOC", "LOCATION"):
                gid = _insert_group(cur, case_id, text)
                name_to_node[key] = ("LOCATION", gid)
            elif label == "DATE":
                gid = _insert_group(cur, case_id, text)
                name_to_node[key] = ("DATE", gid)
            else:
                gid = _insert_group(cur, case_id, text)
                name_to_node[key] = ("ORG", gid)

        def resolve(name: str, prefer: str | None = None) -> tuple[str, int] | None:
            name_l = name.lower()
            if prefer:
                hit = name_to_node.get((name_l, prefer))
                if hit:
                    return hit
            for (n, lab), node in name_to_node.items():
                if n == name_l:
                    return node
            # relation target might not be in included entities
            if prefer == "PERSON" or prefer is None:
                existing = query(
                    "SELECT PersonID, FullName FROM Person WHERE CaseMasterID = ?",
                    (case_id,),
                )
                if existing:
                    choices = {str(r["PersonID"]): r["FullName"] for r in existing}
                    match = process.extractOne(name, choices, scorer=fuzz.WRatio)
                    if match and match[1] >= FUZZY_PERSON_THRESHOLD:
                        return ("PERSON", int(match[2]))
            return None

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        edges_added = 0
        for rel in included_r:
            src_name = (rel.get("source") or "").strip()
            tgt_name = (rel.get("target") or "").strip()
            rtype = (rel.get("type") or "NAMED_TOGETHER")[:30]
            src = resolve(src_name, "PERSON")
            tgt_pref = {
                "HAS_PHONE": "PHONE",
                "ASSOCIATED_WITH_VEHICLE": "VEHICLE",
                "MENTIONED_AT_LOCATION": "LOCATION",
                "MENTIONED_ON_DATE": "DATE",
            }.get(rtype)
            tgt = resolve(tgt_name, tgt_pref)
            if not src or not tgt:
                continue
            if src == tgt:
                continue
            conf = float(rel.get("confidence") or RELATION_CONFIDENCE)
            cur.execute(
                """
                INSERT INTO GraphEdge (
                    CaseMasterID, SourceEntityType, SourceEntityID,
                    TargetEntityType, TargetEntityID, RelationType, EventDateTime,
                    SourceType, SourceRecordID, ConfidenceScore, IndependenceGroupID
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PDF_UPLOAD', NULL, ?, NULL)
                """,
                (case_id, src[0], src[1], tgt[0], tgt[1], rtype, now, conf),
            )
            edges_added += 1

            # Structured side tables when we have a person + phone/plate
            if rtype == "HAS_PHONE" and src[0] == "PERSON":
                cur.execute(
                    "INSERT INTO PhoneNumber (PersonID, PhoneNumber, IsPrimary) VALUES (?, ?, 1)",
                    (src[1], tgt_name),
                )
            if rtype == "ASSOCIATED_WITH_VEHICLE" and src[0] == "PERSON":
                cur.execute(
                    """
                    INSERT INTO VehicleRegistration (PersonID, RegistrationNumber, VehicleType)
                    VALUES (?, ?, 'Extracted')
                    """,
                    (src[1], tgt_name),
                )
                vid = int(cur.lastrowid)
                name_to_node[(tgt_name.lower(), "VEHICLE")] = ("VEHICLE", vid)

        conn.commit()
        return {"created": created, "edges_added": edges_added}
    finally:
        conn.close()
