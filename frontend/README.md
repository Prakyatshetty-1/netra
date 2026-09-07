# NETRA Frontend

React (JavaScript) investigator dashboard. Talks to the existing FastAPI backend — do not start this without the API.

## Setup

```bash
cp .env.example .env   # already defaults to http://localhost:8000
npm install
```

Start the FastAPI backend first (project root):

```bash
uvicorn backend.main:app --reload --port 8000
```

Then:

```bash
npm run dev
```

Open the URL Vite prints (usually **http://localhost:5173**).

After installing Python deps, once:

```bash
python -m spacy download en_core_web_sm
```

`VITE_API_BASE_URL` in `.env` must match wherever uvicorn is listening.

```bash
npm run build    # production bundle in dist/
```
