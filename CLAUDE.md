# COMPLY — Agent Guide

Engineering-compliance audit app. Engineer uploads standards (Eurocodes) and a
project design report, clicks a compliance chip, gets a summary + PASS/WARN/FAIL
table whose citations navigate-and-highlight the source PDF.

## Architecture

```
frontend/  Next.js 14 (port 3000) — three views: FileSidebar | FileViewer | ChatSidebar
backend/   FastAPI (port 8000)    — main.py: upload/classify/coords/RAG/chat-SSE
backend/mcp/server.py             — MCP stdio subprocess (5 tools), spawned by lifespan
Firestore  code_chunks / project_chunks / design_chunks (1536-dim Gemini vectors)
```

Audit path: chip → `[COMPLIANCE_AUDIT]` prefix → `POST /chat` SSE → agentic tool
loop (extract_design_values → retrieve_code_clauses → compare_value_to_clause) →
`<table>` JSON parsed server-side → `table` SSE event → ChatSidebar renders
summary + table → citation badge click → PdfViewer jumps to page and highlights
via `GET /files/{id}/coordinates` word boxes.

## Token discipline (do not regress this)

The app previously crashed on Anthropic TPM limits. The fix is layered — keep
all of it:

1. **MCP tools return compressed structured JSON, never raw chunk prose**
   (`server.py`: retrieve_code_clauses compresses clauses to
   {clause_number, requirement, formula, threshold, excerpt} via a small
   FAST_MODEL call; search_documents truncates excerpts; compare echoes slim).
2. **Heavy LLM work runs inside the tools as independent small API calls**
   (extraction + clause compression on FAST_MODEL) — the main chat context
   never sees document prose.
3. **Prompt caching** — `cache_control` on the tool list + system prompt in
   `main.py /chat`.
4. **429/529 retry with backoff** on every Anthropic call (main.py stream
   entry; server.py `_anthropic_call`), plus MAX_TOOL_ROUNDS=12,
   MAX_TOOL_RESULT_CHARS, server-side history trim.
5. **No whole-document paths.** `GET /files/{id}/content` was removed;
   `file_reader.read_file` refuses PDFs. Document text only enters via
   chunked retrieval (`services/rag.py` → project_chunks).

## Contracts that must stay in sync

- `[COMPLIANCE_AUDIT]` prefix: ChatSidebar chips ↔ `is_compliance_audit()`.
- SSE events: `token | status | reset_text | table | error | done`
  (backend `main.py` ↔ `frontend/lib/api.ts` streamChat).
- Table row fields: COMPLIANCE_SYSTEM_PROMPT (main.py) ↔ `ComplianceRow`
  (frontend/lib/types.ts). Citation badges need project_file_id + source_page +
  highlight_start/end (project) or standard_file_id + standard_page +
  standard_text (standard).
- PATCH /files/{id}/cell: `row` is 0-based into the sheet BODY (first sheet
  row is a header) — backend writes to physical `row + 2`.
- Embeddings: gemini-embedding-001 @ 1536 dims. Query side (server.py
  embed_query, RETRIEVAL_QUERY) must match document side (services/rag.py,
  RETRIEVAL_DOCUMENT). Firestore needs a vector index per *_chunks collection.
- file_id format: `{uuid4}_{sanitized_filename}` — GET /files recovers the
  display name via `split('_', 1)`.

## Run

```bash
# backend
cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000
# frontend
cd frontend && npm run dev
```

`backend/.env` needs ANTHROPIC_API_KEY, GOOGLE_API_KEY, FIREBASE_PROJECT_ID,
GOOGLE_APPLICATION_CREDENTIALS. Optional: ANTHROPIC_MODEL (default
claude-sonnet-4-6), ANTHROPIC_FAST_MODEL (default claude-haiku-4-5-20251001),
MAX_CONCURRENT_CHATS, ADMIN_API_KEY.

Seed the standards corpus (one-off): `python backend/embed/chunk_and_embed.py`
(reads backend/docs/*.pdf → code_chunks / design_chunks).

## Verify a change

Upload `backend/docs/eurocode3.pdf` (→ STANDARD) and `backend/docs/d3-solution.pdf`
(→ PROJECT, wait for the indexing dot to clear), run the "Check EC3 Compliance"
chip, and confirm: status lines stream, summary + table render, a FAIL/WARN row's
P badge jumps the PDF to the cited page with a yellow highlight. A full audit
takes ~3-5 minutes.

## Media

`media/reference/` = target quality bar (civils.ai screenshots — capability
parity, NOT visual cloning). `media/prototype/` = historical screenshots of the
old broken UI; superseded.
