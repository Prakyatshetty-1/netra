"""Rule-based contradiction search: two events, 30 minutes, >5 km apart."""

from __future__ import annotations

import math
from typing import Any

from backend.db import query
from backend.services.intelligence_service import _parse_dt

MAX_MINUTES = 30
MIN_KM = 5.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _events_for_person(case_id: int, person_id: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    calls = query(
        """
        SELECT CallID, CallDateTime, TowerLatitude, TowerLongitude, CallerPersonID, CalleePersonID, SourceType
        FROM CommunicationRecord
        WHERE CaseMasterID = ? AND (CallerPersonID = ? OR CalleePersonID = ?)
          AND TowerLatitude IS NOT NULL AND TowerLongitude IS NOT NULL
        """,
        (case_id, person_id, person_id),
    )
    for c in calls:
        dt = _parse_dt(c["CallDateTime"])
        if dt is None:
            continue
        events.append(
            {
                "kind": "CDR",
                "id": c["CallID"],
                "time": dt,
                "lat": float(c["TowerLatitude"]),
                "lon": float(c["TowerLongitude"]),
                "source_type": c["SourceType"] or "CDR",
            }
        )

    sightings = query(
        """
        SELECT vs.SightingID, vs.Latitude, vs.Longitude, vs.SightingDateTime, vs.SourceType,
               vr.RegistrationNumber
        FROM VehicleSighting vs
        JOIN VehicleRegistration vr ON vr.VehicleID = vs.VehicleID
        WHERE vs.CaseMasterID = ? AND vr.PersonID = ?
          AND vs.Latitude IS NOT NULL AND vs.Longitude IS NOT NULL
        """,
        (case_id, person_id),
    )
    for s in sightings:
        dt = _parse_dt(s["SightingDateTime"])
        if dt is None:
            continue
        events.append(
            {
                "kind": "ANPR",
                "id": s["SightingID"],
                "time": dt,
                "lat": float(s["Latitude"]),
                "lon": float(s["Longitude"]),
                "source_type": s["SourceType"] or "ANPR",
                "vehicle": s["RegistrationNumber"],
            }
        )
    events.sort(key=lambda e: e["time"])
    return events


def _serialize_event(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": e["kind"],
        "id": e["id"],
        "time": e["time"].strftime("%Y-%m-%d %H:%M:%S"),
        "lat": round(e["lat"], 6),
        "lon": round(e["lon"], 6),
        "source_type": e["source_type"],
        **({k: e[k] for k in ("vehicle",) if k in e}),
    }


def find_contradictions(case_id: int, person_id: int) -> list[dict]:
    events = _events_for_person(case_id, person_id)
    found: list[dict] = []
    for i, a in enumerate(events):
        for b in events[i + 1 :]:
            delta = abs((b["time"] - a["time"]).total_seconds()) / 60.0
            if delta > MAX_MINUTES:
                break
            dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
            if dist >= MIN_KM:
                found.append(
                    {
                        "person_id": person_id,
                        "description": (
                            f"Person {person_id} appears in two places {dist:.1f} km apart "
                            f"only {delta:.0f} minutes apart ({a['kind']} vs {b['kind']})."
                        ),
                        "event_a": _serialize_event(a),
                        "event_b": _serialize_event(b),
                        "distance_km": round(dist, 2),
                        "minutes_apart": round(delta, 1),
                    }
                )
    return found
