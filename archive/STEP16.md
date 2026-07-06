# COMPLY — Current Active Step
Last updated: [date]
Status: ACTIVE

## Current Step: Step 16 — RAG Unification

## Overview
The current PROJECT document path is still partly temporary:

`upload PROJECT → frontend fetches /files/{id}/content → useChat injects truncated PROJECT text into Claude history → extract_design_values(document_text=...) reads that context`

Step 16 moves PROJECT documents into the same retrieval pattern as standards:

`upload PROJECT → backend chunks + embeds PROJECT PDF → Firestore project_chunks → MCP search/extract tools query by file_id → chat no longer injects large document text`

The goal is one consistent RAG pipeline where Claude retrieves PROJECT evidence
and STANDARD clauses through tools, while citations still carry `file_id`,
`page`, `highlight_start`, and `highlight_end` for PDF navigation.

---

## Stage 1 — Define PROJECT chunk schema
Create the Firestore shape for uploaded PROJECT documents.

Target collection:

```text
project_chunks
```

Required fields:

```text
chunk_id: string
file_id: uploaded file_id
filename: original filename
source: original filename or stable source label
classification: "PROJECT"
text: chunk text
page: source PDF page number
chunk_index: integer
word_count: integer
embedding: Vector
created_at: timestamp or ISO string
```

Pass condition:
- Every PROJECT chunk can be filtered by `file_id`.
- Every PROJECT chunk preserves `page`.
- Every PROJECT chunk has enough `text` to quote `reference_text`.

Status: [x] implemented in code; pending Firestore smoke test

---

## Stage 2 — Add reusable backend embedding service
Extract reusable chunk/embed helpers from `backend/embed/chunk_and_embed.py`.

Current code:
- `chunk_and_embed.py` is a batch script for static docs in `backend/docs`.
- It writes to `design_chunks` and `code_chunks`.
- It is not called by `/upload`.

Tasks:
- Create reusable helpers, probably under `backend/services/rag.py` or similar.
- Reuse `read_pdf_with_pages`, chunking, Gemini embedding, and Firestore writes.
- Load Firebase credentials the same way as `backend/mcp/server.py`.
- Keep batch static-doc script working or adapt it to use the shared helpers.

Pass condition:
- Backend can call one function like `embed_project_file(file_id, filename, path)`.
- Function writes PROJECT chunks to `project_chunks`.
- Function is importable without running the batch script.

Status: [x] implemented in code; pending Firestore smoke test

---

## Stage 3 — Trigger PROJECT embedding on upload
Update `backend/main.py` upload flow.

Current code:
- Saves file to `backend/uploads`.
- Classifies as STANDARD / PROJECT / UNKNOWN.
- Extracts PDF coordinates.
- Does not embed uploaded PROJECT documents.

Tasks:
- If uploaded file is a PDF and classification is PROJECT, start PROJECT chunk+embed.
- Prefer background task or async handoff so upload does not feel frozen.
- Store embedding status in `_meta.json`:

```text
rag_status: "pending" | "embedded" | "failed"
rag_collection: "project_chunks"
rag_error: string | null
```

Pass condition:
- Uploading a PROJECT PDF eventually creates Firestore `project_chunks`.
- `/files` can report or preserve RAG status from metadata.
- Failed embedding does not break PDF upload/viewing.

Status: [x] implemented in code; pending upload smoke test

---

## Stage 4 — Add file_id filter to MCP search_documents
Update `backend/mcp/server.py`.

Current code:
- `search_documents(query, source_filter=None, top_k=5)`
- Searches `design_chunks` and/or `code_chunks`.
- No `file_id` filter.
- No `project_chunks` collection.

Tasks:
- Add optional `file_id: str | None = None`.
- Add source filters:

```text
project → project_chunks
design  → design_chunks
eurocode/code → code_chunks
all     → project_chunks + design_chunks + code_chunks
```

- When `file_id` is provided, only return chunks matching that `file_id`.
- Return `file_id`, `filename`, `page`, `text`, and `collection`.

Pass condition:
- Claude can ask for PROJECT evidence from one uploaded file only.
- Tool results include enough citation data to populate `project_file_id` and `source_page`.

Status: [x] implemented in code; pending MCP smoke test

---

## Stage 5 — Update extract_design_values to use project_chunks
Update the MCP extraction path.

Current code:
- `extract_design_values(document_text=None, element_type=None, parameter=None)`
- Uses `document_text` when provided.
- Falls back to Firestore `design_chunks`.

Target:
- Prefer `project_chunks` filtered by `file_id`.
- Keep `document_text` only as a temporary fallback until migration is complete.

Tasks:
- Add optional `file_id: str | None = None`.
- If `file_id` is present, retrieve relevant chunks from `project_chunks`.
- Preserve chunk page numbers in extracted claims.
- Make `source_quote` suitable for `reference_text`.

Pass condition:
- Compliance audits can extract values from uploaded PROJECT chunks without frontend full-text injection.
- Extracted claims include page/source quote information for citations.

Status: [x] implemented in code; pending MCP smoke test

---

## Stage 6 — Update compliance prompt/tool instructions
Update backend prompts and skill docs so Claude follows the new RAG path.

Current prompt:
- Says PROJECT text is injected in context.
- Calls `extract_design_values` with document text.

Target prompt:
- PROJECT documents are identified by `file_id`.
- Claude calls `extract_design_values(file_id=...)`.
- Claude calls `search_documents(source_filter="project", file_id=...)` when it needs more PROJECT evidence.

Files to update:

```text
backend/main.py
backend/mcp/skills/compliance_audit/SKILL.md
backend/mcp/skills/conversational_query/SKILL.md
method/CLAUDE.md
method/WORKFLOW.md
```

Pass condition:
- Prompt no longer depends on large injected document text.
- Prompt still requires exact PROJECT citation fields in the table.

Status: [x] implemented in code

---

## Stage 7 — Remove frontend full-text injection
Update frontend once backend PROJECT RAG is working.

Current code:
- `useFiles.ts` calls `getFileContent(uploaded.file_id)` for PROJECT files.
- `useChat.ts` stores large `fileContexts`.
- `useChat.ts` injects truncated PROJECT text into chat history.

Tasks:
- Stop calling `/files/{id}/content` on upload for PROJECT files.
- Store uploaded PROJECT references as `{file_id, filename}` only.
- Build history with PROJECT labels only:

```text
[PROJECT DOCUMENT file_id=... filename="..."]
```

- Keep STANDARD references as `{file_id, filename}`.

Pass condition:
- Chat request history no longer contains huge PROJECT text.
- Claude still receives all PROJECT and STANDARD file IDs.
- Compliance audit still produces table citations through MCP tool results.

Status: [x] implemented in code

---

## Stage 8 — Retire or repurpose /files/{id}/content
Decide what to do with the temporary content endpoint.

Options:
- Remove endpoint after frontend no longer uses it.
- Keep it as a debug/admin endpoint only.
- Keep it for Excel/plain viewer needs if still useful.

Pass condition:
- No production compliance flow depends on `/files/{id}/content`.
- If endpoint remains, its purpose is documented.

Status: [ ] pending decision

---

## Stage 9 — Smoke test PROJECT RAG audit
Use real uploaded documents.

Test:
1. Upload EC1/EC3 as STANDARD.
2. Upload design report as PROJECT.
3. Confirm PROJECT embedding completes.
4. Click `Check EC3 Compliance`.

Pass condition:
- Claude calls MCP tools.
- PROJECT values come from `project_chunks`, not injected frontend text.
- Table rows include `project_file_id`, `source_page`, `reference_text`, `highlight_start`, `highlight_end`.
- PROJECT badge jumps/highlights in PDF viewer.

Status: [ ] pending browser + Firestore smoke test

---

## Stage 10 — Smoke test conversational RAG
Test normal chat questions without `[COMPLIANCE_AUDIT]`.

Examples:

```text
What does my report say about imposed loads?
Where is the section size stated?
What does clause 6.2.6 mean?
```

Pass condition:
- Normal questions return plain text.
- PROJECT-specific questions can use `project_chunks`.
- Standard/code questions can use `code_chunks`.
- No compliance table appears unless the hidden compliance prefix is used.

Status: [ ] pending browser + Firestore smoke test

---

## Next Step After This
Step 17 — End-to-End Test And Polish

After RAG unification, run the full PROJECT + STANDARD compliance flow and
verify table rendering, citation badges, PDF page jumps, highlights, and plain
conversational answers from the same uploaded file set.
