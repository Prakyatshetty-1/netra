"""GET /cases and GET /cases/{id}. POST /cases to create a stub from PDF extraction."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db import get_write_conn, query, query_one

router = APIRouter(tags=["cases"])


class NewCaseBody(BaseModel):
    crime_no: str | None = None
    case_no: str | None = None
    brief_facts: str | None = None


@router.get("/cases")
def list_cases():
    rows = query(
        """
        SELECT c.CaseMasterID, c.CrimeNo, c.CaseNo,
               ch.CrimeGroupName, csh.CrimeHeadName, cs.CaseStatusName,
               o.IncidentFromDate, o.BriefFacts,
               (SELECT COUNT(*) FROM Person p WHERE p.CaseMasterID = c.CaseMasterID) AS PersonCount,
               (SELECT COUNT(*) FROM GraphEdge g WHERE g.CaseMasterID = c.CaseMasterID) AS EdgeCount
        FROM CaseMaster c
        LEFT JOIN CrimeHead ch ON ch.CrimeHeadID = c.CrimeMajorHeadID
        LEFT JOIN CrimeSubHead csh ON csh.CrimeSubHeadID = c.CrimeMinorHeadID
        LEFT JOIN CaseStatusMaster cs ON cs.CaseStatusID = c.CaseStatusID
        LEFT JOIN Inv_OccuranceTime o ON o.CaseMasterID = c.CaseMasterID
        ORDER BY EdgeCount DESC, c.CaseMasterID
        """
    )
    return [
        {
            "case_id": r["CaseMasterID"],
            "crime_no": r["CrimeNo"],
            "case_no": r["CaseNo"],
            "crime_group": r["CrimeGroupName"],
            "crime_head": r["CrimeHeadName"],
            "status": r["CaseStatusName"],
            "incident_from": str(r["IncidentFromDate"]) if r["IncidentFromDate"] else None,
            "brief_facts": (r["BriefFacts"] or "")[:280],
            "person_count": r["PersonCount"],
            "edge_count": r["EdgeCount"],
        }
        for r in rows
    ]


@router.get("/cases/{case_id}")
def get_case(case_id: int):
    r = query_one(
        """
        SELECT c.CaseMasterID, c.CrimeNo, c.CaseNo,
               ch.CrimeGroupName, csh.CrimeHeadName, cs.CaseStatusName,
               o.IncidentFromDate, o.BriefFacts, o.latitude, o.longitude,
               (SELECT COUNT(*) FROM Person p WHERE p.CaseMasterID = c.CaseMasterID) AS PersonCount,
               (SELECT COUNT(*) FROM GraphEdge g WHERE g.CaseMasterID = c.CaseMasterID) AS EdgeCount
        FROM CaseMaster c
        LEFT JOIN CrimeHead ch ON ch.CrimeHeadID = c.CrimeMajorHeadID
        LEFT JOIN CrimeSubHead csh ON csh.CrimeSubHeadID = c.CrimeMinorHeadID
        LEFT JOIN CaseStatusMaster cs ON cs.CaseStatusID = c.CaseStatusID
        LEFT JOIN Inv_OccuranceTime o ON o.CaseMasterID = c.CaseMasterID
        WHERE c.CaseMasterID = ?
        """,
        (case_id,),
    )
    if not r:
        raise HTTPException(404, "Case not found")
    persons = query(
        """
        SELECT PersonID, FullName, SourceRole, AgeYear
        FROM Person WHERE CaseMasterID = ? ORDER BY SourceRole, FullName
        """,
        (case_id,),
    )
    return {
        "case_id": r["CaseMasterID"],
        "crime_no": r["CrimeNo"],
        "case_no": r["CaseNo"],
        "crime_group": r["CrimeGroupName"],
        "crime_head": r["CrimeHeadName"],
        "status": r["CaseStatusName"],
        "incident_from": str(r["IncidentFromDate"]) if r["IncidentFromDate"] else None,
        "brief_facts": r["BriefFacts"],
        "person_count": r["PersonCount"],
        "edge_count": r["EdgeCount"],
        "latitude": float(r["latitude"]) if r["latitude"] is not None else None,
        "longitude": float(r["longitude"]) if r["longitude"] is not None else None,
        "persons": [
            {
                "person_id": p["PersonID"],
                "full_name": p["FullName"],
                "source_role": p["SourceRole"],
                "age": p["AgeYear"],
            }
            for p in persons
        ],
    }


@router.post("/cases")
def create_case(body: NewCaseBody):
    """Create a minimal stub case — used when a PDF extraction should live on its own canvas."""
    conn = get_write_conn()
    try:
        cur = conn.cursor()

        today = datetime.utcnow().strftime("%Y-%m-%d")
        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        crime_no = body.crime_no or f"PDF-{stamp}"
        case_no = body.case_no or f"PDF-CASE-{stamp}"

        defaults = query_one(
            """
            SELECT PolicePersonID, PoliceStationID, CaseCategoryID,
                   GravityOffenceID, CrimeMajorHeadID, CrimeMinorHeadID, CourtID
            FROM CaseMaster ORDER BY CaseMasterID LIMIT 1
            """
        )
        if not defaults:
            raise HTTPException(500, "Cannot seed new case — no existing cases")

        cur.execute(
            """
            INSERT INTO CaseMaster (
                CrimeNo, CaseNo, CrimeRegisteredDate,
                PolicePersonID, PoliceStationID, CaseCategoryID, GravityOffenceID,
                CrimeMajorHeadID, CrimeMinorHeadID, CaseStatusID, CourtID
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                crime_no,
                case_no,
                today,
                defaults["PolicePersonID"],
                defaults["PoliceStationID"],
                defaults["CaseCategoryID"],
                defaults["GravityOffenceID"],
                defaults["CrimeMajorHeadID"],
                defaults["CrimeMinorHeadID"],
                defaults["CourtID"],
            ),
        )
        new_id = int(cur.lastrowid)

        if body.brief_facts:
            cur.execute(
                "INSERT INTO Inv_OccuranceTime (CaseMasterID, BriefFacts) VALUES (?, ?)",
                (new_id, body.brief_facts),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return get_case(new_id)
