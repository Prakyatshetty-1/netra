"""Person/phone/account intelligence and explainable evidence aggregation."""
from __future__ import annotations

from backend.db import query, query_one
from backend.services.xai_service import explain_association, identity_explanation, field_match


def _person(person_id: int) -> dict:
    p = query_one("""
        SELECT p.PersonID, p.FullName, p.SourceRole, p.SourceRecordID, p.CaseMasterID,
               p.AgeYear, cm.CrimeNo, cm.CaseNo, cm.CrimeRegisteredDate,
               u.UnitName, d.DistrictName, s.StateName
        FROM Person p
        LEFT JOIN CaseMaster cm ON cm.CaseMasterID=p.CaseMasterID
        LEFT JOIN Unit u ON u.UnitID=cm.PoliceStationID
        LEFT JOIN District d ON d.DistrictID=u.DistrictID
        LEFT JOIN State s ON s.StateID=d.StateID
        WHERE p.PersonID=?
    """, (person_id,))
    if not p:
        raise ValueError("Person not found")
    return p


def person_profile(person_id: int) -> dict:
    p = _person(person_id)
    phones = query("SELECT PhoneID, PhoneNumber, IsPrimary FROM PhoneNumber WHERE PersonID=? ORDER BY IsPrimary DESC, PhoneID", (person_id,))
    accounts = query("SELECT AccountID, AccountNumber, BankName FROM BankAccount WHERE PersonID=? ORDER BY AccountID", (person_id,))
    vehicles = query("SELECT VehicleID, RegistrationNumber, VehicleType FROM VehicleRegistration WHERE PersonID=?", (person_id,))
    cases = query("""
        SELECT DISTINCT cm.CaseMasterID AS case_id, cm.CrimeNo, cm.CaseNo, cm.CrimeRegisteredDate
        FROM GraphEdge ge JOIN CaseMaster cm ON cm.CaseMasterID=ge.CaseMasterID
        WHERE (ge.SourceEntityType='PERSON' AND ge.SourceEntityID=?) OR (ge.TargetEntityType='PERSON' AND ge.TargetEntityID=?)
        ORDER BY cm.CaseMasterID
    """, (person_id, person_id))
    edges = query("""
        SELECT EdgeID, SourceEntityType, SourceEntityID, TargetEntityType, TargetEntityID,
               RelationType, EventDateTime, SourceType, ConfidenceScore
        FROM GraphEdge
        WHERE (SourceEntityType='PERSON' AND SourceEntityID=?) OR (TargetEntityType='PERSON' AND TargetEntityID=?)
        ORDER BY EventDateTime DESC LIMIT 100
    """, (person_id, person_id))
    evidence = []
    if phones:
        evidence.append({"confidence": 0.80, "reason": f"{len(phones)} phone record(s) are explicitly linked to this PersonID."})
    if accounts:
        evidence.append({"confidence": 0.85, "reason": f"{len(accounts)} bank account record(s) are explicitly linked to this PersonID."})
    if vehicles:
        evidence.append({"confidence": 0.75, "reason": f"{len(vehicles)} vehicle registration(s) are explicitly linked to this PersonID."})
    if edges:
        evidence.append({"confidence": 0.70, "reason": f"{len(edges)} graph evidence edge(s) reference this PersonID."})
    association = explain_association("person_entity_resolution", evidence)
    return {"entity_type":"PERSON", "person":p, "phones":phones, "accounts":accounts,
            "vehicles":vehicles, "cases":cases, "evidence_edges":edges,
            "xai":{"association_signal":association,
                   "method":"Deterministic database linkage + graph evidence; no opaque identity decision is made here."}}


def phone_intelligence(case_id: int, phone_id: int) -> dict:
    phone = query_one("SELECT PhoneID, PersonID, PhoneNumber, IsPrimary FROM PhoneNumber WHERE PhoneID=?", (phone_id,))
    if not phone:
        raise ValueError("Phone not found")
    persons = query("""
        SELECT p.PersonID, p.FullName, p.SourceRole, p.AgeYear, p.CaseMasterID,
               CASE WHEN p.CaseMasterID=? THEN 1 ELSE 0 END AS in_selected_case
        FROM Person p WHERE p.PersonID=?
    """, (case_id, phone["PersonID"]))
    person_ids = [x["PersonID"] for x in persons]
    accounts = query("SELECT AccountID, AccountNumber, BankName FROM BankAccount WHERE PersonID=?", (phone["PersonID"],))
    vehicles = query("SELECT VehicleID, RegistrationNumber, VehicleType FROM VehicleRegistration WHERE PersonID=?", (phone["PersonID"],))
    comms = query("""
        SELECT CallID, CaseMasterID, CallerPersonID, CalleePersonID, CallDateTime, DurationSeconds, SourceType
        FROM CommunicationRecord WHERE CallerPersonID=? OR CalleePersonID=? ORDER BY CallDateTime DESC LIMIT 100
    """, (phone["PersonID"], phone["PersonID"]))
    evidence=[{"confidence":0.95,"reason":"The PhoneNumber table explicitly links this phone record to a PersonID."}]
    return {"entity_type":"PHONE", "phone":phone, "persons":persons, "accounts":accounts,
            "vehicles":vehicles, "communications":comms,
            "xai":{"association_signal":explain_association("phone_to_person", evidence),
                   "identity_warning":"Phone ownership/usage is an association signal and is not itself government identity proof.",
                   "method":"Direct PhoneNumber.PersonID linkage; downstream identity verification must be separately authorized."}}


def account_intelligence(case_id: int, account_id: int) -> dict:
    account = query_one("SELECT AccountID, PersonID, AccountNumber, BankName FROM BankAccount WHERE AccountID=?", (account_id,))
    if not account:
        raise ValueError("Bank account not found")
    person = _person(int(account["PersonID"]))
    transactions = query("""
        SELECT ft.TxnID, ft.FromAccountID, ft.ToAccountID, ft.Amount, ft.TxnDateTime, ft.TxnType, ft.HopSequence, ft.SourceType
        FROM FinancialTransaction ft WHERE ft.FromAccountID=? OR ft.ToAccountID=? ORDER BY ft.TxnDateTime DESC LIMIT 100
    """, (account_id, account_id))
    related_accounts = query("""
        SELECT DISTINCT ba.AccountID, ba.PersonID, ba.AccountNumber, ba.BankName
        FROM FinancialTransaction ft JOIN BankAccount ba
          ON ba.AccountID IN (ft.FromAccountID, ft.ToAccountID)
        WHERE ft.FromAccountID=? OR ft.ToAccountID=? ORDER BY ba.AccountID
    """, (account_id, account_id))
    evidence=[{"confidence":0.98,"reason":"The BankAccount table explicitly maps this account to PersonID."}]
    return {"entity_type":"ACCOUNT", "account":account, "person":person,
            "transactions":transactions, "related_accounts":related_accounts,
            "xai":{"association_signal":explain_association("account_to_person", evidence),
                   "identity_warning":"An account-holder association does not by itself prove who operated an account at a given time.",
                   "method":"Direct BankAccount.PersonID linkage plus transaction-network context."}}


def compare_identity(police: dict, government: dict, verified: bool) -> dict:
    fields=[]
    for f in ["name","date_of_birth","phone","place"]:
        fields.append(field_match(f, police.get(f), government.get(f)))
    xai=identity_explanation(fields, verified)
    return {"status":xai["status"], "confidence":xai["score"], "fields":fields, "xai":xai}
