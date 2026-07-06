# COMPLY

COMPLY is a local engineering compliance prototype with three services in one workspace:

- `frontend/`: Next.js UI on port `3000`
- `backend/`: FastAPI API on port `8000`
- `backend/mcp/`: Python MCP server launched by the backend subprocess client

## Environment

Create `backend/.env` from `backend/.env.example`. Keep real secrets out of git.

Required backend values:

- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `FIREBASE_PROJECT_ID`
- `GOOGLE_APPLICATION_CREDENTIALS`

Optional backend values:

- `UPLOAD_DIR`, defaults to `./uploads`
- `ANTHROPIC_MODEL`, defaults to `claude-sonnet-4-6`
- `CORS_ORIGINS`, defaults to local Next.js ports
- `MAX_CONCURRENT_CHATS`, defaults to `3`
- `ADMIN_API_KEY`, enables coordinate backfill when set

Frontend uses `frontend/.env.local` for `NEXT_PUBLIC_API_URL`. If omitted, the UI falls back to `http://localhost:8000`.

## Run Locally

Backend:

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The backend starts and stops the MCP subprocess automatically during the FastAPI lifespan.

Docker Compose:

```bash
docker compose up
```

This starts the backend on `8000` and the frontend on `3000`.
