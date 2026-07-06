# COMPLY — Full Build Plan
Last updated: [date]
Status: IN PROGRESS

## Purpose
This file describes the complete build plan for COMPLY.
Each step has an overview and a list of tasks.
The current active step is detailed in STEP.md.

## Build Overview
Step 1   — Backend foundation (FastAPI, MCP client, file reader) ✅ COMPLETE
Step 1.5 — File classification (STANDARD vs PROJECT) ✅ COMPLETE
Step 1.6 — System prompt workflow + MCP tool return shape ✅ COMPLETE
Step 2   — PDF coordinate extraction ✅ COMPLETE
Step 3   — Frontend types (dual citation schema) ✅ COMPLETE
Step 4   — Frontend scaffold (Next.js, Tailwind, types, API layer) ✅ COMPLETE
Step 5   — API layer SSE table event handler ✅ COMPLETE
Step 6   — Chat hooks (useChat, useFiles, table attachment) ✅ COMPLETE
Step 7   — Three-panel layout + activeCitation state (page.tsx) ✅ COMPLETE
Step 8   — File sidebar with upload and classification badge ✅ COMPLETE
Step 9   — Excel viewer (mini Excel, ribbon, frozen headers, cell editing) ✅ COMPLETE
Step 10  — PDF viewer (coordinate fetch, citation navigation, lavender highlight) 🔄 ACTIVE — CODE COMPLETE, SMOKE TEST PENDING
Step 11  — Structured output (system prompt, Summary + Table SSE event) ✅ COMPLETE
Step 12  — Chat sidebar rendering (getSummaryText, ComplianceTable, badges) ✅ CODE COMPLETE, SMOKE TEST PENDING
Step 13  — FileViewer citation routing (activeCitation routes by file_id) ✅ CODE COMPLETE, SMOKE TEST PENDING
Step 14  — Token/latency fixes (SSE headers, cache, semaphore, classification) ✅ COMPLETE
Step 15  — MCP server migration (Python, monorepo) ✅ COMPLETE
Step 16  — RAG unification (embed PROJECT files at upload, remove injection) ✅ CODE COMPLETE, SMOKE TEST PENDING
Step 17  — End-to-end test and polish 🔄 ACTIVE — PARTIAL SMOKE TEST COMPLETE

---

## Step 1 — Backend Foundation
Overview: FastAPI server with MCP subprocess, file upload, file reader.
Tasks:
- requirements.txt and .env
- mcp_client.py — spawns Python MCP server via stdio
- file_reader.py — PDF (pypdf) and Excel (openpyxl) to text
- main.py — all endpoints, lifespan, CORS, Claude API streaming

Status: COMPLETE

---

## Step 2 — PDF Coordinate Extraction
Overview: extract word positions from every uploaded PDF for highlight feature.
Tasks:
- add pdfplumber to requirements.txt
- extract_pdf_coordinates function in file_reader.py
- POST /upload triggers coordinate extraction on PDF upload
- GET /files/{file_id}/coordinates serves coordinate JSON

Status: COMPLETE

---

## Step 3 — File Classification
Overview: classify every uploaded file as STANDARD or PROJECT on upload.
Tasks:
- classify_document function in main.py using Claude API
- filename passed as first argument for reliable classification
- _meta.json written per file storing classification
- GET /files returns classification per file
- useFiles.ts injects lightweight reference for STANDARD, full text for PROJECT

Status: IN PROGRESS — classification prompt fixed, rendering fixes pending

---

## Step 4 — Frontend Scaffold
Overview: Next.js 14 App Router foundation files.
Tasks:
- package.json, next.config.js, tailwind.config.ts
- globals.css with CSS variables and IBM Plex Mono
- lib/types.ts — all shared TypeScript types
- lib/api.ts — fetch helpers including streamChat

Status: COMPLETE

---

## Step 5 — Chat Hooks And State Management
Overview: global chat state, file context injection, streaming.
Tasks:
- hooks/useFiles.ts — file list, upload, delete
- hooks/useChat.ts — single global chat, injectFileContext, sendMessage
- app/page.tsx — three panel layout with shared state

Status: COMPLETE

---

## Step 6 — Three Panel Layout Shell
Overview: left sidebar, centre viewer, right chat — full viewport.
Tasks:
- MainLayout or page.tsx three panel shell
- activeCitation state lifted to parent
- onCitationClick wired between ChatSidebar and FileViewer

Status: COMPLETE

---

## Step 7 — File Sidebar
Overview: file list with upload zone.
Tasks:
- FileSidebar.tsx — file list, type badges, delete, drag-and-drop upload
- react-dropzone integration
- classification badge (STANDARD/PROJECT)

Status: COMPLETE

---

## Step 8 — Excel Viewer
Overview: mini Excel with ribbon, frozen headers, cell editing.
Tasks:
- ExcelViewer.tsx — full ribbon (all tabs functional)
- frozen column/row headers
- keyboard navigation
- cell editing with PATCH /files/{id}/cell auto-save
- draw tools, sort/filter, freeze panes

Status: COMPLETE

---

## Step 10 — PDF Viewer
Overview: PDF rendering with citation navigation and highlight.
Tasks:
- PdfViewer.tsx — @react-pdf-viewer with pageNavigationPlugin
- coordinate fetch from GET /files/{id}/coordinates
- lavender source highlight drawn on citation click
- highlight persists until next click
- visual behaviour follows media/reference citation-jump screenshots while keeping the dark prototype shell

Status: ACTIVE — code complete, browser smoke test pending

---

## Step 11 — Structured Output
Overview: backend locks Claude into Summary + JSON table output.
Tasks:
- COMPLIANCE_SYSTEM_PROMPT with 6-step workflow
- extract_table function parses <table> JSON after stream
- table SSE event fired after done event
- dual citation fields in every table row

Status: COMPLETE

---

## Step 12 — Chat Sidebar
Overview: structured compliance output renderer.
Tasks:
- ChatSidebar.tsx — streaming state and settled state
- getSummaryText strips <table> tags before display
- SummaryText renders [n] markers as inline PROJECT badges
- ComplianceTable renders FAIL/WARN/PASS rows
- PROJECT badge (blue) and STANDARD badge (purple) per row
- Quick prompt chips above input
- Hidden pre-prompt chip handling and dual response mode
- Conversational messages render as plain text without tables

Status: CODE COMPLETE — browser smoke test pending

---

## Step 13 — Bidirectional Citations
Overview: click badge in chat → PDF navigates and highlights.
Tasks:
- activeCitation state in page.tsx
- FileViewer routes by activeCitation.file_id
- PdfViewer fetches coordinates, draws highlight on citation change

Status: CODE COMPLETE — browser smoke test pending

---

## Step 14 — Latency Fixes
Overview: SSE buffering, in-memory cache, batch tool calls.
Tasks:
- SSE headers on StreamingResponse
- _coords_cache in main.py
- batch tool call instruction in system prompt
- configurable request semaphore for concurrent calls

Status: COMPLETE

---

## Step 16 — RAG Unification
Overview: embed PROJECT files at upload into Firestore project_chunks.
Tasks:
- upload triggers background chunk+embed for PROJECT files
- search_documents tool accepts file_id filter
- remove full text injection from useChat.ts
- remove GET /files/{id}/content endpoint

Status: CODE COMPLETE — Firestore/browser smoke test pending

---

## Step 17 — End-To-End Test And Polish
Overview: full flow with real documents, deploy prep.
Tasks:
- upload EC1, EC3, client req as STANDARD
- upload design report as PROJECT
- run Check EC3 Compliance chip
- confirm summary, table, PROJECT badge, STANDARD badge all work
- confirm PDF navigates and highlights on badge click
- deploy frontend to Vercel, backend to Railway

Status: ACTIVE — environment/upload/RAG smoke passed; Anthropic credits block chat/compliance checks
