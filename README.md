# COMPLY

AI engineering-compliance audits with document-anchored citations.

Upload standards (Eurocodes, client requirements) and a project design report,
run a compliance check, and get a concise summary plus a PASS/WARN/FAIL findings
table. Every finding cites both the project document and the governing clause —
clicking a citation navigates the PDF viewer to the exact page and highlights
the quoted text.

## Stack

- `frontend/` — Next.js 14, three-view layout (files / document viewer / chat), port `3000`
- `backend/` — FastAPI, port `8000`; spawns `backend/mcp/server.py` (MCP stdio
  subprocess with the RAG + compliance tools) during app lifespan
- Firestore vector search (Gemini `gemini-embedding-001`, 1536 dims) over
  `code_chunks` / `project_chunks` / `design_chunks`
- Anthropic API (Claude) for audit orchestration and per-check verdicts

## Environment

Create `backend/.env` from `backend/.env.example`. Keep real secrets out of git.

Required:

- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `FIREBASE_PROJECT_ID`
- `GOOGLE_APPLICATION_CREDENTIALS` (path to a service-account key)

Optional:

- `ANTHROPIC_MODEL` — default `claude-sonnet-4-6` (orchestration + verdicts)
- `ANTHROPIC_FAST_MODEL` — default `claude-haiku-4-5-20251001` (extraction + clause compression)
- `UPLOAD_DIR` — default `./uploads`
- `CORS_ORIGINS` — defaults to local Next.js ports
- `MAX_CONCURRENT_CHATS` — default `3`
- `ADMIN_API_KEY` — enables `POST /admin/backfill-coordinates`

Frontend uses `frontend/.env.local` for `NEXT_PUBLIC_API_URL`
(default `http://localhost:8000`).

## Run locally

Backend:

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Or both via Docker: `docker compose up`.

One-off corpus seeding (embeds `backend/docs/*.pdf` into Firestore):

```bash
python backend/embed/chunk_and_embed.py
```

## Using it

1. Upload standards (e.g. `eurocode1.pdf`, `eurocode3.pdf`) — auto-classified
   STANDARD.
2. Upload a design report — classified PROJECT and chunk-embedded into
   Firestore (amber dot in the sidebar while indexing).
3. Select the project file and click a chip ("Check EC3 Compliance", …).
4. Watch live status while the audit runs (~3–5 min), then explore the findings
   table; `P` badges highlight the project PDF, `S` badges the standard.

Excel files open in a built-in windowed grid viewer with cell editing
(auto-saved back to the file).
