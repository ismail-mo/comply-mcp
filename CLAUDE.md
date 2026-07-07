# COMPLY — Agent Guide

Engineering-compliance auditor. Engineer uploads a design report (PDF), asks
"check the column" (or clicks a chip), and gets a deterministic Eurocode audit:
status pills, overview, recommended actions, and a findings table whose
citations navigate-and-highlight the source PDF.

## Core philosophy (do not regress this)

**COMPLY is a tested deterministic Eurocode-checking engine wrapped in a thin
AI membrane.** The AI has exactly two jobs per audit: (1) extract values from
prose into strict JSON, (2) narrate finished findings. The AI never runs a
formula, never decides a verdict, never sees document prose in the main chat
context. Every number in a finding comes from pure Python that is unit-tested
against hand-worked answers.

## Architecture

```
engine/     run_audit.py (orchestrator), classify.py, cross_reference.py
formulas/   7 Tier-1 EC3 formulas as pure functions (lazy registry by name)
tables/     transcribed lookup data: section_properties (SCI P363 Blue Book),
            steel_grade (EN 10025-2), buckling/LTB curves, partial factors
registries/ check_registry.py (checks per element type), national_annex.py
tests/      28 pytest tests + golden snapshot (tests/golden/check8.json)
backend/    FastAPI (port 8000) — main.py: deterministic 7-stage pipeline
backend/mcp/server.py   MCP stdio subprocess — 3 tools only
backend/services/indexer.py  build_document_index / read_pages (PyMuPDF)
frontend/   Next.js 14 (port 3000), light theme — FileSidebar | FileViewer |
            ChatSidebar with draggable splitters; AuditView renders findings
Firestore   code_chunks (1536-dim Gemini vectors) — quick_answer path only
```

### The audit pipeline (main.py `_audit_stream`)

```
Stage 0  upload → coords + document_index ({file_id}_index.json)   0 AI
Stage 1  route: audit keywords/prefix vs quick answer              0 AI
Stage 2  scope: element match + clause/status filters              0 AI
Stage 3  extraction cache check ({file_id}_extract_{el}.json)      0 AI
Stage 4  extract_element — schema-enforced forced tool call        AI #1 (FAST)
Stage 5  run_audit() — formulas, classify, cross_reference         0 AI (<100ms)
Stage 6  write_overview — narrate the finished findings            AI #2
Stage 7  assemble + stream (findings event BEFORE overview event)
```

Two AI calls per cold audit (~30s full, ~9s findings table); warm extraction
cache makes repeat audits near-instant to findings.

### The 3 MCP tools

- `extract_element(element_type, pdf_path, pages, required_inputs,
  input_descriptions, designation)` — FAST_MODEL forced tool call returns
  `{values: {name: {value, unit, page, quote, confidence, flag}}, not_found}`.
- `write_overview(element, designation, document, findings, summary)` —
  narration only; returns overview paragraph + recommended_actions.
- `search_documents(query, top_k)` — Firestore vector search; quick_answer only.

## Engine invariants

- **Statuses** (severity order): FAIL → ERROR → CONFLICT → MISSING → ASSUMED →
  WARNING → PASS. ERROR = engineer's arithmetic disagrees with the engine's
  code-correct recompute (>2% tolerance); CONFLICT = elements disagree on a
  shared parameter (grade/fy), detected via cached extracts of other elements.
- **Section properties come from `tables/section_properties.py` (Blue Book),
  never from the design PDF** (spec Part 5.3). Add new sections by transcribing
  P363 rows with a `source` citation.
- **fy fallback**: if fy isn't stated but grade + Blue Book tf are known,
  `fy_for(grade, tf)` derives it from EN 10025-2 Table 7 deterministically.
- **Unit normalization**: `_EXPECTED_UNITS` in run_audit.py coerces extracted
  strings ("5,190.75") to floats and converts mm→m etc. before formulas run.
- **Confidence**: extracted values with confidence < 0.6 are flagged ASSUMED.
- **Formulas are test-first.** Every formula reproduces ≥2 independent
  known-answer oracles (SCI P364 worked examples, P363 published resistances)
  to 3 sig figs. `pytest tests/ -q` must stay green (28 tests). Golden
  snapshot: regenerate ONLY deliberately via `REGEN_GOLDEN=1 … pytest
  tests/test_engine.py`.

## Contracts that must stay in sync

- SSE events: `status | findings | overview | quick_refs | token | error |
  done(timing)` — backend `_sse()` in main.py ↔ `frontend/lib/api.ts`
  streamChat ↔ `ChatStreamChunk` in types.ts.
- `AuditFinding` fields (types.ts) ↔ engine output dicts — including
  `badge` (CiteBadge: ec3|en1990|en10025|report|sbb), `reference.{quote,
  clause, page, source}`, `calc.{label, lines}`, `metrics`, `assumed_inputs`.
  Anything that emits findings (run_audit, cross_reference) must emit the
  full contract or AuditView breaks on `var(--cite-undefined-bg)`.
- Audit routing: chip prefixes / keywords ↔ `is_compliance_audit()` (main.py).
- Scope filters: `_scope_filters()` parses clause ("6.3.1") and status
  ("failures") words from the message; keep `_STATUS_WORDS` in sync with the
  status taxonomy.
- Upload response includes `indexed_elements: [{type, designation}]` for
  PROJECT PDFs → FileSidebar shows the "Ready. N elements indexed…" notice.
- Extraction cache files `{file_id}_extract_{element}.json` carry a
  `_pages_key` fingerprint; the delete endpoint and `list_files()` must keep
  excluding `_meta/_coords/_index/_extract_*` sidecars.
- PATCH /files/{id}/cell: `row` is 0-based into the sheet BODY (first sheet
  row is a header) — backend writes to physical `row + 2`.
- Embeddings (quick_answer only): gemini-embedding-001 @ 1536 dims;
  RETRIEVAL_QUERY on the query side must match RETRIEVAL_DOCUMENT on the
  corpus side. Firestore needs a vector index on code_chunks.
- file_id format: `{uuid4}_{sanitized_filename}` — display name recovered via
  `split('_', 1)`.

## Token discipline (why it never hits TPM limits)

Heavy LLM work happens inside the tools on FAST_MODEL; the chat context holds
only compact JSON. Prompt caching (`cache_control` ephemeral) on system +
tool list; 4-attempt jittered backoff on 429/500/503/529 everywhere. No
whole-document paths — document text enters only via `read_pages` (bounded)
inside extract_element, or chunked retrieval for quick_answer.

## Run

```bash
cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000
cd frontend && npm run dev
# engine tests (from repo root)
backend/venv/bin/python -m pytest tests/ -q
```

`backend/.env` needs ANTHROPIC_API_KEY, GOOGLE_API_KEY, FIREBASE_PROJECT_ID,
GOOGLE_APPLICATION_CREDENTIALS. Optional: ANTHROPIC_MODEL (default
claude-sonnet-4-6), ANTHROPIC_FAST_MODEL (default claude-haiku-4-5-20251001),
MAX_CONCURRENT_CHATS, ADMIN_API_KEY.

Standards corpus for quick_answer (one-off):
`python backend/embed/chunk_and_embed.py` (reads backend/docs/*.pdf).

## Verify a change

1. `backend/venv/bin/python -m pytest tests/ -q` → 28 passed.
2. Upload `backend/docs/d3-solution.pdf` (→ PROJECT; sidebar shows "Ready. 2
   elements indexed: column (UC 254x254x132), beam (UB 610x178x100).").
3. Click "Check the column": status lines stream, findings table renders
   (~9s cold, instant warm), then overview + recommended actions fill in.
4. Click a `> source · p.N` reference line → PDF jumps to the cited page with
   a blue highlight.
5. "Check the beam" exercises the fy-fallback (S355 stated, no numeric fy)
   and the shear ERROR path. Ask "what is chi in the buckling check?" to hit
   the quick_answer path.

## Media & reference

`media/reference/` = target quality bar (civils.ai screenshots — capability
parity, NOT visual cloning). `prompts/prompt1.md` = the authoritative spec
for this build. `backend/mcp/skills/*/SKILL.md` = output format contracts
(reference docs, not loaded at runtime).
