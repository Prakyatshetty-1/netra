# NETRA Prototype

Evidence-centric criminal-network investigator dashboard for Smart India Hackathon PS 26189. Built to run fully offline against `netra_sim.db`.

## Setup

**Backend**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn backend.main:app --reload --port 8000
```

**Frontend** (Vite + React, from `frontend/`)

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open **http://localhost:5173**. The API must already be on port 8000 (or the URL in `VITE_API_BASE_URL`).

`netra_sim.db` must sit in the project root next to `requirements.txt`.

## Demo flow

1. Pick a high-edge case from the left dropdown (sorted by graph size).
2. Search a person name — matched node plus BFS-reachable neighbours stay bright; the rest fade.
3. Click a person for H1–H4 scores, contradiction search, and a live counterfactual (node removal).
4. Read Case DNA similarity bars and identity candidates (no auto-merge below 0.85).
5. Ask the copilot a grounded question; Accept / Reject / Request More writes a SHA-256 line to `audit_log.jsonl`.
6. **Upload Document**: extract a text PDF → review entities/relations → Confirm to insert `PDF_UPLOAD` edges (dashed on the graph). Scanned PDFs return `ocr_required` instead of failing.

## Modules

| Module | Role |
|---|---|
| `graph_service` | NetworkX graph from `GraphEdge` |
| `intelligence_service` | Betweenness, communities, 72h call-burst flags |
| `identity_service` | Entity-resolution pairs with RESOLVED / UNRESOLVED status |
| `casedna_service` | 4-channel feature vector + cosine similarity |
| `hypothesis_service` | Labeled H1–H4 or heuristic generation |
| `contradiction_service` | 30-minute / 5 km haversine conflict check |
| `counterfactual_service` | Remove a person, recompute connectivity |
| `copilot_service` | Template Q&A with DIRECTLY_OBSERVED / INFERRED tags |
| `extraction_service` | PDF text + spaCy/regex entities, same-sentence relations, human confirm |

## Known Simplifications

These are intentional prototype gaps, not unfinished TODOs:

- **No Neo4j** — in-memory NetworkX per request is enough for this dataset.
- **No GNN / Node2Vec** — the hand-built 4-channel Case DNA vector would be replaced by a learned embedding in production.
- **No blockchain** — `audit_log.jsonl` plus SHA-256 is the full provenance layer.
- **No authentication / RBAC** — not implemented.
- **No PDF / OCR ingestion** — text PDFs can be uploaded and reviewed; scanned pages are flagged `ocr_required` (no OCR engine in this prototype).
- **No external LLM** — the copilot is template-grounded and offline.
