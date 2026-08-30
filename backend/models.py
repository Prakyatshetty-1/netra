"""Pydantic response schemas for the NETRA prototype API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    centrality: float = 0.0
    community: int | None = None
    highlighted: bool = False


class GraphEdgeOut(BaseModel):
    id: int
    source: str
    target: str
    relation: str
    time: str | None = None
    source_type: str | None = None
    confidence: float | None = None
    burst: bool = False
    highlighted: bool = False


class GraphResponse(BaseModel):
    case_id: int
    nodes: list[GraphNode]
    edges: list[GraphEdgeOut]
    matched_node: str | None = None


class CaseSummary(BaseModel):
    case_id: int
    crime_no: str
    case_no: str
    crime_group: str | None = None
    crime_head: str | None = None
    status: str | None = None
    incident_from: str | None = None
    brief_facts: str | None = None
    person_count: int = 0
    edge_count: int = 0


class PersonOut(BaseModel):
    person_id: int
    full_name: str
    source_role: str
    age: int | None = None


class CaseDetail(CaseSummary):
    latitude: float | None = None
    longitude: float | None = None
    persons: list[PersonOut] = Field(default_factory=list)


class IdentityCandidateOut(BaseModel):
    candidate_id: int
    raw_name_variant: str
    person_id_a: int
    person_id_b: int
    name_a: str
    name_b: str
    case_a: int
    case_b: int
    name_similarity: float | None = None
    model_confidence: float
    status: str
    ground_truth_same: bool | None = None


class ChannelScores(BaseModel):
    topology: float
    temporal: float
    financial: float
    roles: float


class RelatedCase(BaseModel):
    case_id: int
    crime_no: str
    crime_head: str | None = None
    overall: float
    channels: ChannelScores


class HypothesisOut(BaseModel):
    type: str
    narrative: str
    score: float
    ground_truth: bool | None = None
    generated: bool = False


class ContradictionOut(BaseModel):
    person_id: int
    description: str
    event_a: dict[str, Any]
    event_b: dict[str, Any]
    distance_km: float
    minutes_apart: float


class CounterfactualResult(BaseModel):
    person_id: int
    person_label: str
    before: dict[str, float]
    after: dict[str, float]
    percent_change: dict[str, float]


class CopilotClaim(BaseModel):
    claim: str
    tag: Literal["DIRECTLY_OBSERVED", "INFERRED"]
    source_type: str
    confidence: float | None = None
    timestamp: str | None = None
    formatted: str


class CopilotResponse(BaseModel):
    answer: str
    claims: list[CopilotClaim]


class AskBody(BaseModel):
    question: str


class DecisionBody(BaseModel):
    decision: Literal["ACCEPT", "REJECT", "REQUEST_MORE"]
    reviewer: str = "demo-investigator"
    rationale: str = ""


class DecisionRecord(BaseModel):
    case_id: int
    decision: str
    reviewer: str
    rationale: str
    timestamp: str
    hash: str
