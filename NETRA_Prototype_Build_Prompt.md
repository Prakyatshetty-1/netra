# NETRA Grand Finale — Prototype Build Prompt

Paste everything below the line into Claude Code / Cursor / any coding
agent, in a fresh project folder that also contains `netra_sim.db`
(from the earlier NETRA-Sim database). It builds a small, fully working,
demoable prototype — not a production system.

---

## FILE STRUCTURE (what will be created)

```
netra-prototype/
├── netra_sim.db                     # (you already have this — copy it in)
├── requirements.txt                 # Python deps
├── README.md                        # setup + run instructions
├── backend/
│   ├── main.py                      # FastAPI app entrypoint, mounts all routers
│   ├── db.py                        # SQLite connection helper for netra_sim.db
│   ├── models.py                    # Pydantic response schemas
│   ├── services/
│   │   ├── graph_service.py         # builds a NetworkX graph from GraphEdge per case
│   │   ├── identity_service.py      # fuzzy-match scoring over IdentityCandidate
│   │   ├── intelligence_service.py  # centrality, community detection, anomaly (call-burst) detection
│   │   ├── casedna_service.py       # 4-channel feature vector + cosine similarity across cases
│   │   ├── hypothesis_service.py    # scores H1-H4 for a candidate using graph + CompetingHypothesis
│   │   ├── contradiction_service.py # rule-based conflict check (e.g. two co-located edges same time, diff place)
│   │   ├── counterfactual_service.py# removes a node, recomputes centrality/connectivity delta
│   │   ├── copilot_service.py       # template-grounded Q&A: claim -> source -> timestamp -> confidence
│   │   └── provenance_service.py    # SHA-256 hash + append-only JSON-lines audit log
│   └── routers/
│       ├── cases.py                 # GET /cases, GET /cases/{id}
│       ├── graph.py                 # GET /cases/{id}/graph, GET /cases/{id}/graph/search?name=
│       ├── identity.py              # GET /cases/{id}/identity-candidates
│       ├── casedna.py               # GET /cases/{id}/related-cases
│       ├── hypothesis.py            # GET /cases/{id}/hypotheses/{person_id}
│       ├── contradiction.py         # GET /cases/{id}/contradictions/{person_id}
│       ├── counterfactual.py        # POST /cases/{id}/counterfactual/{person_id}
│       ├── copilot.py               # POST /cases/{id}/ask  {question: str}
│       └── decisions.py             # POST /cases/{id}/decisions  (accept/reject/request-more)
└── frontend/
    ├── index.html                   # single-page dashboard shell
    ├── style.css                    # dark navy/amber theme matching the pitch deck
    └── app.js                       # fetch calls + Cytoscape.js graph rendering + panel logic
```

---

## THE PROMPT

You are building a small, working, demoable prototype of **NETRA** — an
evidence-centric criminal-network-analysis investigator dashboard for
Smart India Hackathon PS 26189. This is a 36-hour hackathon prototype, not
production software: prioritize a working end-to-end demo over completeness,
scale, or real ML training. Use simple, explainable heuristics everywhere a
full ML model would normally go — the goal is a system that behaves
correctly and explainably on the provided dataset, not a trained model.

### Data source
Use the SQLite file `netra_sim.db` exactly as-is (do not modify its schema).
Key tables you'll query:
- `CaseMaster`, `Inv_OccuranceTime` (has `BriefFacts` narrative text, lat/long)
- `Person` (unified accused/victim/complainant graph nodes, has `CaseMasterID`)
- `PhoneNumber`, `VehicleRegistration`, `BankAccount`
- `GraphEdge` — the single source of truth for relationships: `SourceEntityType`,
  `SourceEntityID`, `TargetEntityType`, `TargetEntityID`, `RelationType`,
  `EventDateTime`, `SourceType`, `ConfidenceScore`, `IndependenceGroupID`
- `IdentityCandidate` — labeled entity-resolution pairs (`GroundTruthIsSamePerson`)
- `CompetingHypothesis` — labeled H1-H4 rows per case (`GroundTruthLabel`)
- `EvidenceIndependenceGroup` — groups correlated observations of one event

### Backend — FastAPI, Python 3.11+

Build every module below as a small, readable service, each backed by a
router. Keep functions short and commented — a judge or teammate should be
able to open any file and understand what it does in under a minute.

**1. Graph Service (`graph_service.py` + `routers/graph.py`)**
- `GET /cases/{id}/graph` → build a NetworkX graph from `GraphEdge` rows
  for that case, return nodes (id, type, label, centrality) and edges
  (source, target, relation, time, source_type, confidence) as JSON.
- `GET /cases/{id}/graph/search?name=` → fuzzy-match the name against
  `Person.FullName` in that case, find the matching node, run a BFS/
  shortest-path traversal, and return the same graph JSON with a
  `highlighted: true/false` flag per node/edge (matched node + everything
  reachable from it = true, everything else = false). This powers the
  "search a name → darken connected nodes" feature.

**2. Identity Service (`identity_service.py` + `routers/identity.py`)**
- `GET /cases/{id}/identity-candidates` → pull `IdentityCandidate` rows
  touching any person in this case, return them with `ModelConfidence`,
  and a computed status: `"RESOLVED"` if confidence > 0.85, else
  `"UNRESOLVED — Candidate A/B"`. Never auto-merge below threshold — return
  both candidate identities separately, exactly as NETRA's design requires.

**3. Intelligence Service (`intelligence_service.py`)**
- Compute betweenness centrality and simple Louvain-style community
  detection (use `networkx.algorithms.community`) on the case graph.
- Anomaly/burst detection: group `GraphEdge` rows of type `CALLED` by day;
  flag any person-pair with ≥5 calls within a 72-hour window as a "burst."
  Expose this via the graph endpoint as a `burst: true` flag on the
  relevant edges — this is what "Temporal Analysis" surfaces.

**4. Case DNA Service (`casedna_service.py` + `routers/casedna.py`)**
- For a given case, compute a simple 4-channel feature vector (this is
  the interpretable "Case DNA", NOT a trained embedding):
  - `topology`: [node count, edge count, max betweenness centrality]
  - `temporal`: [max calls in any 72h window, days from first edge to incident]
  - `financial`: [number of transaction hops, total amount] (0s if none)
  - `roles`: [count of PERSON nodes, count of ACCOUNT/VEHICLE nodes]
  Concatenate and min-max normalize into one vector per case.
- `GET /cases/{id}/related-cases` → compute cosine similarity between this
  case's vector and every other case's vector, return top 5 with an
  **overall score** AND a **per-channel breakdown** (topology/temporal/
  financial/roles), so the frontend can show the similarity decomposition
  bar chart from the pitch deck.

**5. Hypothesis Service (`hypothesis_service.py` + `routers/hypothesis.py`)**
- `GET /cases/{id}/hypotheses/{person_id}` → if `CompetingHypothesis` rows
  exist for this case/person, return them directly (type, narrative,
  score, ground truth). If none exist, generate a plausible H1-H4 set on
  the fly using simple heuristics (e.g. call-burst presence → boosts
  INTERMEDIARY score; shared employer/family text in BriefFacts → boosts
  LEGITIMATE; low degree → boosts COINCIDENCE). Always return all four
  hypotheses together, ranked, never just the top one.

**6. Contradiction Service (`contradiction_service.py` + `routers/contradiction.py`)**
- `GET /cases/{id}/contradictions/{person_id}` → simple rule-based check:
  look for two `GraphEdge` rows for this person within the same 30-minute
  window but with tower/sighting coordinates more than ~5km apart (compute
  haversine distance). If found, return a contradiction object describing
  the conflict; otherwise return `{"contradictions": []}`. This demonstrates
  the Contradiction Search Engine concept even without real CCTV data.

**7. Counterfactual Service (`counterfactual_service.py` + `routers/counterfactual.py`)**
- `POST /cases/{id}/counterfactual/{person_id}` → build the case graph,
  compute connectivity/path-count baseline, remove the given node, recompute
  the same metrics, return the before/after values and the percentage
  change. This is a live, real computation — not mocked.

**8. Copilot Service (`copilot_service.py` + `routers/copilot.py`)**
- `POST /cases/{id}/ask` with `{"question": "..."}` → NO external LLM call
  required for the base prototype (keep it offline-runnable). Implement a
  small template-based responder: parse simple question patterns like "why
  is X flagged" or "why does this case match Y", look up the relevant
  `GraphEdge`/`CompetingHypothesis`/related-case rows, and return an answer
  string built from a template: `"<claim> — <STATUS> (Source: <SourceType>,
  confidence <ConfidenceScore>, <EventDateTime>)"`. Tag every claim
  DIRECTLY_OBSERVED (came straight from a GraphEdge row) or INFERRED (came
  from the hypothesis/related-case service). If you have an API key
  available and want a nicer natural-language wrapper, you may optionally
  call an LLM to phrase the final sentence — but it must only phrase facts
  already retrieved by this function, never invent new ones.

**9. Provenance Service (`provenance_service.py` + `routers/decisions.py`)**
- `POST /cases/{id}/decisions` with `{"decision": "ACCEPT|REJECT|REQUEST_MORE",
  "reviewer": "...", "rationale": "..."}` → compute a SHA-256 hash of the
  decision payload + current timestamp, append as one JSON line to a local
  `audit_log.jsonl` file (this is your "permissioned ledger" — a simple
  signed append-only log, not a real blockchain, matching the Grand Finale
  positioning). Return the logged record including its hash.

### Frontend — plain HTML/CSS/JS, no build step

Single page (`frontend/index.html`) styled with a dark navy (#0f2038) /
amber (#e8952e) theme matching the pitch deck. Use **Cytoscape.js** (via
CDN) for graph rendering — no React needed for a prototype this size.

Layout (mirror the dashboard wireframe from the deck):
- Left sidebar: case picker (dropdown from `GET /cases`) + nav sections
  (Graph, Identity, Case DNA, Hypotheses, Copilot).
- Center: Cytoscape graph canvas + a search box wired to
  `/graph/search?name=` — matched node and connected nodes render in red,
  everything else fades to light grey (opacity 0.25).
- Right panel, stacked cards: Identity Candidates, Related Cases (with
  per-channel similarity bars), Competing Hypotheses (four cards with
  scores), Contradictions (if any), Counterfactual test button + result.
- Bottom strip: Copilot input box + conversation log; each answer shows
  its DIRECTLY_OBSERVED / INFERRED tag and source.
- A small "Decision" bar: Accept / Reject / Request More Evidence buttons
  that POST to `/decisions` and show the returned hash + timestamp.

### Non-goals for this prototype (explicitly skip)
- No real Neo4j — NetworkX in-memory per request is enough for this data size.
- No real GNN/Node2Vec training — the hand-built 4-channel vector is the
  "Case DNA" for this prototype; note in the README that a learned
  embedding would replace it in production.
- No real blockchain — the JSON-lines hash log is the full provenance
  layer.
- No authentication/RBAC implementation — note it as a documented gap in
  the README, not built.
- No file upload / OCR pipeline — the prototype reads directly from
  `netra_sim.db`, which already contains structured case data; mention in
  the README that a PDF-to-structured-data ingestion step would sit in
  front of this in a full build.

### Deliverables
1. All files listed in the FILE STRUCTURE section above, fully working.
2. `requirements.txt` (fastapi, uvicorn, networkx, rapidfuzz, numpy).
3. `README.md` with: setup steps (`pip install -r requirements.txt`,
   `uvicorn backend.main:app --reload`, open `frontend/index.html`), a
   one-line summary of each module, and an explicit "Known Simplifications"
   section listing the non-goals above so it's honest in front of judges.
4. Everything should run **fully offline** with zero paid API keys required.

---

*This prompt assumes `netra_sim.db` sits at the project root. If it's
missing, regenerate it from `NETRA_Sim_Data_Generation_Prompt.md` first.*
