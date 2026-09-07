---
title: Netra Prototype
emoji: 📊
colorFrom: yellow
colorTo: indigo
sdk: gradio
sdk_version: 6.26.0
app_file: app.py
pinned: false
license: mit
short_description: NETRA Crime Evidence & CCTV Analysis Dashboard
---

# NETRA Prototype

Evidence-centric criminal-network investigator dashboard for Smart India Hackathon PS 26189. Built to run against `netra_sim.db`.

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
6. **Upload Document**: extract a text PDF or handwritten note via Gemini Vision OCR → review entities/relations → Confirm to insert edges into the graph.
7. **Evidence & CCTV Upload**: upload CCTV video clips with timestamped frame sampling and YOLOv8 object detection.
8. **Upload Photo**: upload visual evidence with automatic YOLO/face crop extraction and relation mapping.

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
| `extraction_service` | PDF text & Handwritten OCR + spaCy/regex entities, relations |
| `image_extraction_service` | YOLOv8 + Face recognition, padded crop generation |
| `cctv_service` | OpenCV video frame sampling + YOLOv8 object detection |
