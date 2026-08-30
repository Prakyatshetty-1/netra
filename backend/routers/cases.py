"""GET /cases and GET /cases/{id}."""

from fastapi import APIRouter, HTTPException

from backend.db import query, query_one

router = APIRouter(tags=["cases"])


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
