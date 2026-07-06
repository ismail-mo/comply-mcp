COMPLY — Cold Eye Audit
Dimension 1: File and Folder Structure
Score: 2/10

Issues:

No root .gitignore — frontend/.next/, frontend/node_modules/, backend/venv/, backend/__pycache__/, .env, firebase-key.json, *_coords.json, *_meta.json, and backend/audits/*.txt are not excluded.
Workspace is not a git repository — no version control, no commit hygiene, no remote safety net.
No root README.md — onboarding, run order, and env vars are undocumented at repo root.
No docker-compose.yml (or equivalent) — local dev requires manually starting FastAPI + Next.js + MCP with no orchestration.
backend/firebase-key.json exists on disk — service account secret in the project tree.
backend/.env and root .env exist on disk — API keys likely present locally with no documented rotation path.
frontend/.next/ build output is present (thousands of files) — build artifacts treated as source.
backend/venv/ is present — Python virtualenv committed or copied into the tree.
backend/uploads/*_meta.json and *_coords.json sit beside PDFs — runtime/generated data mixed with uploads.
backend/audits/ contains 10+ .txt audit outputs and a .docx — generated reports in source tree, not ignored.
No top-level mcp/ service — MCP lives at backend/mcp/server.py; docs/architecture say “MCP + FastAPI + Next.js” but folder layout does not match that mental model.
backend/package.json is a stray Node manifest inside a Python service — scripts (embed, mcp) belong in root package.json or Makefile, not backend/package.json.
media/prototype/ and media/reference/ split is inconsistent — prototype is current COMPLY; reference is Civils.ai competitor UI; no media/README explaining which is authoritative.
.DS_Store in repo root, backend/, backend/docs/ — macOS junk files.
backend/.env.example documents only ANTHROPIC_API_KEY and UPLOAD_DIR — missing GOOGLE_API_KEY, FIREBASE_PROJECT_ID, CORS origins, model names.
frontend/tsconfig.tsbuildinfo at repo level inside frontend/ — should be gitignored / build-only.
Duplicate env loading paths — root .env plus backend/.env plus MCP loading BACKEND_DIR / ".env" with no single source of truth.
backend/docs/ holds large PDF Eurocodes used only by embed scripts — not separated from runtime upload storage.
method/CLAUDE.md describes extract_design_values as reading “PROJECT text from context” while MCP tool reads Firestore design_chunks only — method docs contradict code.
frontend/hooks/ not listed in tailwind.config.ts content — hooks using Tailwind classes would be purged (hooks currently use mostly inline styles, so this is latent breakage).
Fixes:

Add root .gitignore with: .env, **/.env, firebase-key.json, **/uploads/, **/*_coords.json, **/*_meta.json, backend/audits/, frontend/.next/, node_modules/, venv/, __pycache__/, .DS_Store, *.tsbuildinfo.
Run git init, commit only source; never commit secrets or artifacts.
Add root README.md with: services, ports, env table, uvicorn + next dev commands, MCP lifecycle note.
Add docker-compose.yml wiring backend:8000, frontend:3000, volume for uploads/, env_file template.
Delete backend/firebase-key.json from tree; load via GOOGLE_APPLICATION_CREDENTIALS env path outside repo.
Delete committed .env files; use .env.example only.
Delete frontend/.next/; add to .gitignore; rebuild with npm run build.
Delete backend/venv/ from tree; document python -m venv venv && pip install -r requirements.txt.
Move runtime uploads to backend/uploads/.gitkeep only; gitignore actual upload files.
Gitignore backend/audits/ or move to backend/audits/.gitkeep + external storage.
Either rename docs to “MCP is part of backend” or extract backend/mcp/ to top-level mcp/ with shared types — pick one layout and document it.
Remove backend/package.json or move scripts to root package.json / justfile.
Add media/README.md: “reference = Civils.ai target UX; prototype = COMPLY localhost snapshot.”
Delete all .DS_Store files.
Expand backend/.env.example with every var used in main.py, mcp/server.py, embed/chunk_and_embed.py.
Add *.tsbuildinfo to .gitignore.
Single env file policy: only backend/.env loaded by FastAPI/MCP; frontend uses frontend/.env.local for NEXT_PUBLIC_API_URL.
Move seed PDFs to backend/embed/docs/ or data/standards/.
Fix method/CLAUDE.md workflow to match Firestore RAG or change code to match docs.
Add './hooks/**/*.{ts,tsx}' to tailwind.config.ts content.
Correct: frontend/, backend/main.py, backend/file_reader.py, backend/mcp_client.py, and frontend/components/ separation is logically clear once MCP-under-backend is accepted.

Dimension 2: Backend Code Quality
Score: 3/10

Issues:

read_pdf() in file_reader.py concatenates pages with \n only — no [PAGE n] markers; source_page in compliance table cannot be grounded in injected text.
COMPLIANCE_SYSTEM_PROMPT Step 2 instructs calling extract_design_values with “document text” — extract_design_values in mcp/server.py accepts only element_type and parameter and queries design_chunks in Firestore, not uploaded file text.
get_max_tokens() in main.py (lines 223–242) is defined but never called — dead code; chat uses hardcoded 4096/1024 only.
_clause_cache dict (line 36) is never read or written — dead code.
ChatMessage.role is untyped str — not Literal["user","assistant"]; invalid roles pass through to Anthropic API.
No Pydantic response models on /upload, /files, /chat, /health — OpenAPI and clients are untyped.
/chat handler is ~160 lines inside generate() — business logic, streaming, tool loop, and table extraction are not separated into modules.
asyncio.Semaphore(1) serializes all chat requests globally — second user blocks until first stream completes.
SSE Access-Control-Allow-Origin hardcoded to http://localhost:3000 only (line 711) while CORS middleware allows 3001/3002 — SSE from 3001 fails browser CORS on stream.
classify_document() returns "PROJECT" on any exception (line 293) — misclassifies standards silently.
classify_document() uses max_tokens=10 with no system constraint — model can reply with extra words; parsing uses "STANDARD" in result which false-positives on “NOT STANDARD”.
requirements.txt pins pdfplumber without upper bound — non-reproducible builds.
aiofiles in requirements.txt is unused — dependency bloat.
anthropic_client created at import with ANTHROPIC_API_KEY possibly None — no startup validation.
/admin/backfill-coordinates has no auth — anyone can trigger expensive PDF processing.
health() exposes _request_lock._value — private asyncio internals, not a meaningful queue depth metric.
MCP compare_value_to_clause returns verdict REVIEW — compliance table schema expects WARN; mismatch causes wrong badge semantics.
MCP exposes compliance_chip_handler, response_mode_detector, citation_badge_renderer as callable tools — meta-documentation tools pollute Claude’s tool list and can be invoked by the model.
extract_design_values uses claude-opus-4-7 while chat uses claude-sonnet-4-6 — inconsistent model policy and cost.
mcp_client.py ensure_connected() returns True when pid is None (lines 93–94) — cannot detect dead subprocess when PID introspection fails.
Tool errors return string "Tool error: ..." to Claude with no structured error type — model may hallucinate compliance rows after tool failure.
get_file_content() truncates at 8000 chars with no page boundaries — worsens source_page null rate.
Static mount /uploads serves all uploaded files without auth — any local client can read any uploaded PDF by file_id URL.
edit_cell() uses row=request.row + 2 — undocumented offset; frontend body row 0 maps to Excel row 2; fragile if grid header model changes.
CONVERSATIONAL_SYSTEM_PROMPT still passes full MCP tools — conversational queries can still emit <table> JSON against instructions.
Fixes:

In read_pdf(), emit f"\n[PAGE {i}]\n{text}" per page; use same format in get_file_content injection path.
Change extract_design_values to accept document_text: str and parse that text, or change system prompt to say “query design_chunks via vector search” and remove “document text” wording.
Delete get_max_tokens() or call it from /chat when setting max_tokens.
Delete _clause_cache or implement clause caching keyed by (parameter, code).
class ChatMessage(BaseModel): role: Literal["user", "assistant"].
Add UploadResponse, FileListItem, ChatStreamEvent models; use response_model= on routes.
Split into services/chat_streamer.py, services/classifier.py, services/table_parser.py.
Use Semaphore(int(os.getenv("MAX_CONCURRENT_CHATS", "3"))).
Set SSE header Access-Control-Allow-Origin from same list as CORSMiddleware or omit (middleware handles).
On classify failure, return HTTP 500 or classification: "UNKNOWN" and block compliance chips.
Add system="Reply with exactly one word: STANDARD or PROJECT" and parse with regex ^(STANDARD|PROJECT)$.
Pin pdfplumber>=0.11.0,<1.0.0.
Remove aiofiles from requirements.txt.
In lifespan, if not ANTHROPIC_API_KEY: raise RuntimeError(...).
Protect admin route with API_KEY header or disable in production.
Replace cache metric with explicit in_flight: int counter.
Map REVIEW → WARN in table builder or change MCP to emit WARN.
Remove meta tools from list_tools exposure; keep docs in method/ only.
Single env var ANTHROPIC_MODEL used in both paths.
If pid is None after start, set connected=False and force reconnect.
Return JSON {"error": "...", "retryable": true} from tools on failure.
Raise truncation limit for PROJECT docs or paginate with page markers before cut.
Add auth middleware or signed URLs for /uploads/{file_id}.
Document row indexing in CellEdit model; align frontend/backend on 0-based body rows → 1-based openpyxl rows.
In conversational mode, pass tools=[] or a reduced tool set.
Correct: Lifespan starts/stops MCP; compliance prefix detection (is_compliance_audit, clean_message); table SSE event after stream; coordinate extraction on upload; in-memory _coords_cache; rate-limit retry loop in stream; CORS middleware for standard routes.

Dimension 3: Frontend Code Quality
Score: 4/10

Issues:

useChat.ts onTable mutates last.table and last.citations in place inside setMessages (lines 146–174) — violates React immutability; can skip re-renders.
streamChat() in api.ts has no AbortController — navigating away or unmounting does not cancel fetch; stream continues and setState may run on unmounted tree.
page.tsx calls getMessages() on every render (line 68) — returns same array reference but pattern forces full ChatSidebar re-render; should pass messages from hook directly.
ChatRequest.file_id is always null in useChat.ts (line 135) — typed field unused; backend cannot scope chat to active file.
FileContext stores file_id but history injection only sends filename in string (lines 117–118) — Claude cannot reliably populate project_file_id UUIDs in table JSON.
UploadedFile.type includes 'word' in types.ts (line 4) — backend never returns word; dead type branch in ChatSidebar/FileViewer.
Citation and ActiveCitation interfaces are duplicate — drift risk.
HealthResponse in types.ts missing mcp_pid, cache_size fields returned by API — types lie.
PdfViewer highlight useEffect (line 49) omits coordinates, fileId, jumpToPage from dependency array — citation click before coords load draws nothing with no retry.
PdfViewer highlight overlay is a sibling of <Viewer />, not positioned inside .rpv-core__page-layer — absolute left/top are relative to wrong container; highlight often misplaced or invisible.
PdfViewer drawHighlight() uses document.querySelector('.rpv-core__page-layer') — selects first page layer only; wrong on multi-page DOM after navigation.
FileViewer useEffect for citation switch (line 26) missing files, activeFile, onViewerSwitch in deps — stale closure risk.
During SSE streaming, AssistantMessage uses hasTable === false — raw <table>{...}</table> JSON streams into bubble until onTable fires.
getSummaryText only used when !isStreaming for table layout — streaming UX shows JSON garbage.
ExcelViewer.tsx is 912 lines, light Excel theme (#ffffff, Calibri) — breaks dark COMPLY shell; mixed styling model vs rest of app.
ChatSidebar.tsx is 930 lines — no split into ComplianceTable.tsx, SummaryText.tsx, ChipBar.tsx files as architecture implies.
next.config.js hardcodes NEXT_PUBLIC_API_URL: 'http://localhost:8000' in env block — overrides .env.local unless user knows to change config file.
frontend/package.json uses "latest" for @react-pdf-viewer/*, react-dropzone, xlsx — non-reproducible installs.
console.error in useFiles.ts line 44; console.error/console.warn in PdfViewer.tsx lines 42, 79 — should use user-visible error state.
Hidden prompt chips — correct: handleChipClick calls onSend(chip.hidden_prompt, chip.label) (lines 532–536).
Dual response mode — correct: compliance shows SummaryText + ComplianceTable; non-table assistant shows plain summaryText only (lines 462–482).
useChat sendMessage dependency array is [streaming] only — omits messages, fileContexts, standardRefs; stale history risk if those change during stream (edge case).
standardRefs stores filenames only, not file_id — standard_file_id in table cannot map to uploaded STANDARD PDFs.
tailwind.config.ts missing plugins: [] export default — file may be invalid for Tailwind 3 (works if PostCSS tolerates; still omit hooks from content).
worker-loader rule in next.config.js — no worker-loader in package.json; dead webpack config.
Fixes:

onTable: updated[lastIdx] = { ...last, table, citations }.
Pass AbortSignal from useChat into streamChat; abort in useEffect cleanup on unmount.
const { messages, ... } = useChat() and pass messages={messages}.
Set file_id: activeFile?.file_id ?? null from page state.
Prefix context: [PROJECT DOCUMENT file_id={uuid} filename=...]\n\n{text}.
Remove 'word' from UploadedFile.type or add backend support.
Delete Citation; use ActiveCitation only.
Align HealthResponse with /health JSON.
Add coordinates to citation effect deps; call drawHighlight() when coords arrive if activeCitation set.
Render highlight inside page layer via plugin or portal anchored to active page canvas.
Scope query to visible page: pageLayers[activeCitation.page - 1].
Add full dependency array or disable eslint with documented stable refs.
Strip <table>...</table> from streaming content in token handler before append.
Same strip in streaming branch of AssistantMessage.
Restyle ExcelViewer with CSS variables from globals.css or isolate in iframe.
Extract subcomponents to separate files under components/chat/.
Remove env block from next.config.js; use .env.local only.
Pin exact versions in package-lock.json and replace "latest" with semver ranges.
Surface errors in UI toast/banner. 20–21. No change.
Include state setters and relevant state in useCallback deps or use refs for snapshots intentionally.
Store { file_id, filename }[] for standards; inject into history.
Add hooks to tailwind content.
Remove worker-loader rule or add dependency.
Correct: tsc --noEmit exits 0; lib/api.ts handles token, table, error, done SSE types; chip hidden-prompt UX; getSummaryText strips table block; badge click handlers build ActiveCitation; FileViewer switches file on citation file_id.

Dimension 4: UI/UX Reference Comparison
short summary then table.png
Shows: Civils.ai light-theme “Document Deep Search Agent” — Summary with inline blue numbered citation pills, “Detailed Answer”, risk legend (RED/AMBER/GREEN), wide multi-column contract risk table, disclaimer footer.

Visual differences:

Light theme vs COMPLY dark #0d0d0f shell.
Reference uses “Summary” / “Detailed Answer” headings — COMPLY has neither.
Reference citations are blue numbered circles inline in prose — COMPLY uses blue {n} badges only when row has full project citation fields; otherwise muted [n] text.
Reference severity RED/AMBER/GREEN — COMPLY uses FAIL/WARN/PASS with different colors.
Reference table ~6 columns including “Advice/recommendation” as prose — COMPLY 7-column grid with truncated reference (60 chars) and “✓ Compliant” for PASS.
Reference has top app bar (Editor/Outputs/Run) — COMPLY has none.
Reference no file sidebar — COMPLY three-panel with FILES column.
Typography in reference is sans-serif product UI — COMPLY uses IBM Plex Mono everywhere (closer to prototype than this reference).
Fidelity: 2/10

Exact changes: Add Summary/Detailed Answer labels in AssistantMessage; map FAIL→RED, WARN→AMBER, PASS→GREEN in StatusBadge; add legend row above table; widen chat panel to ~40% viewport; allow full reference_text without 60-char truncation; add footer disclaimer component.

table in detail.png
Shows: “Specification Comparison Table” with navy “SPECS • COMPARE” chip, 4 columns, PASS/FAIL/NOT CLEAR colored keywords, blue citation badges in cells.

Visual differences:

COMPLY table headers: Status, Category, Issue, Reference, Clause, Party, Action — not spec comparison columns.
No “SPECS • COMPARE” view-mode chip in COMPLY.
NOT CLEAR status absent — only FAIL/WARN/PASS.
COMPLY citation badges are “P”/“S” circles — reference uses numeric blue badges.
Reference light table on white — COMPLY dark panel table with var(--border).
Fidelity: 2/10

Exact changes: Either rename product scope to compliance (drop spec-compare layout) or add alternate table schema + renderer for 4-column compare mode; add view chip component in FileViewer header; add NOT CLEAR status color #f59e0b; render citation numbers not letters in ProjectBadge/StandardBadge.

reference code highlight sidebar.png
Shows: PDF left (~50%), chat right; light theme; “Fire Code 2023” title; bold values in answer; “Answer Reference(s)” with filename + blue page badge “184”; purple/lavender full-paragraph PDF highlight; minimal PDF toolbar.

Visual differences:

COMPLY places chat on right but PDF in center with left file list — three panels vs two.
COMPLY PDF uses @react-pdf-viewer/default-layout (thumbnails, full toolbar) — reference minimal chrome.
Reference highlight is lavender multi-line block — COMPLY yellow rgba(255,230,0,0.4) box, often wrong position (overlay bug).
Reference page badge “184” next to filename — COMPLY shows page only inside citation click target, not in prose footer.
Reference bolds key values (800mm and 1.2m) — COMPLY SummaryText renders plain spans only.
Reference search input “Search for info in all your library docs” — COMPLY “Ask about compliance...”.
Dark vs light theme mismatch.
Fidelity: 3/10 (layout inversion partial credit for PDF+chat coexisting)

Exact changes: Remove defaultLayoutPlugin(); use pageNavigationPlugin only; fix highlight portal into page layer; add AnswerReference block under summary with filename + page pill; parse **bold** in summary or use <strong> for numeric phrases; restyle PdfViewer toolbar to match reference spacing.

sidebar text bold writing.png
Shows: Drawings left (~50%), chat right; “DRAWINGS • SPECS” tab; conversational numbered list with bold headings; “References found” row with thumbnails; project-wide search bar.

Visual differences:

COMPLY chat is compliance-table-centric, not long-form numbered prose lists.
No “References found” thumbnail strip under answers.
No top “Search all project” field in chat header.
No “DRAWINGS • SPECS” mode tabs.
COMPLY does not render markdown bold in assistant messages.
File sidebar shows file list, not drawing thumbnails.
Fidelity: 2/10

Exact changes: Add markdown rendering for conversational messages only; add ReferencesRow component fetching PDF thumbs; add mode tabs in FileViewer header; add project search input (wire to backend or client filter).

table citations sidebar.png
Shows: PDF left, compliance table right (~50/50); RED/AMBER status text; blue numeric badges in “Reference text” column; hand cursor on interactive rows; page toolbar “22 / 64”.

Visual differences:

COMPLY chat column fixed 380px — reference table panel wider (~half screen).
COMPLY status badges are filled pills FAIL/WARN/PASS — reference uses text “RED”/“AMBER” without pill container.
COMPLY hides table during stream — reference shows static output.
Citation badges in reference are numeric in table cells — COMPLY uses “P”/“S”.
COMPLY PDF highlight not visible in prototype/reference parity tests.
Row hover states exist in COMPLY — aligned.
Fidelity: 3/10

Exact changes: Change page.tsx chat width to min(42vw, 520px); replace StatusBadge text with RED/AMBER/GREEN labels for compliance mode; use row index badges in table cells; ensure PdfViewer highlight matches lavender or brand yellow consistently.

media/prototype/ui three part viewer design.png (implementation snapshot, not in reference folder)
Shows: Actual COMPLY localhost — dark three-panel, FILES sidebar, PDF center with default-layout viewer, chat with chips “Check EC1”, “Check EC3”, etc.

Visual differences vs current code:

Prototype chip labels shortened (“Check EC1”) — code uses longer labels (“Check EC1 Compliance”) in COMPLIANCE_CHIPS.
Prototype matches dark theme — code matches.
Prototype shows PROJECT badge in chat header — code matches ChatSidebar active file chip.
File list in prototype lacks per-file STANDARD/PROJECT classification badge — WORKFLOW.md Step 8 claims badge on file sidebar, but FileSidebar.tsx does not render file.classification.
Fidelity: 7/10 (prototype vs code — not Civils reference)

Exact changes: Shorten chip labels to match prototype; add classification badge to FileItem in FileSidebar.tsx.

Overall Score: 3/10 (against media/reference/ Civils.ai targets; prototype alignment is higher but reference folder is the stated target)

Dimension 5: System Workflow
Score: 2/10

Broken handoffs:

Upload → text injection → page numbers — backend/file_reader.py read_pdf() / get_file_content(); no [PAGE n] markers; Claude returns source_page: null; Fix: inject page markers in read_pdf() and include them in useChat truncated context.

Upload PROJECT → extract_design_values — mcp/server.py extract_design_values() queries Firestore design_chunks, not uploaded file; uploaded PROJECT PDF text in useChat history is ignored by tool; Fix: add document_text parameter to tool and pass joined PROJECT context from main.py or embed on upload per WORKFLOW Step 16.

STANDARD upload → standard_file_id — useChat.ts standardRefs stores filenames only (lines 40–41, 107–111); table standard_file_id cannot reference eur1.pdf UUID; Fix: standardRefs: {file_id, filename}[] and inject file_id list into system/history.

PROJECT context → project_file_id — useChat.ts history string uses filename without file_id (lines 117–118); Fix: include file_id in [PROJECT DOCUMENT file_id=...] label.

Chip → backend routing — Correct: ChatSidebar.tsx handleChipClick → onSend(hidden_prompt, label) → is_compliance_audit() in main.py.

MCP tool sequence — System prompt mandates order but nothing enforces; Claude can skip tools; Fix: optional server-side orchestration for compliance mode or tool-choice forcing on first turn.

retrieve_code_clauses → standard_page — Tool returns page from Firestore chunk metadata; may not match uploaded STANDARD PDF page numbers; Fix: document mismatch or map chunk source to uploaded file coordinates.

compare_value_to_clause → table status — MCP returns REVIEW; table expects WARN; Fix: normalize in extract_table() post-process or MCP tool.

Stream complete → table SSE — Correct: main.py lines 691–693 emit type: table after agent loop in compliance mode.

table SSE → message attachment — useChat.ts onTable mutates object in place; can fail to attach; Fix: immutable update of last assistant message.

Streaming UI → table strip — tokens append raw <table>JSON</table> until done; Fix: strip table tags in token callback in useChat.ts.

getSummaryText → render — Correct when hasTable true after stream ends.

Badge click → activeCitation — Correct: SummaryText/ProjectBadge/StandardBadge call onCitationClick.

activeCitation → FileViewer — Correct: page.tsx setActiveCitation; FileViewer switches file by file_id.

PdfViewer coordinates — fetch on fileId change works; citation effect does not wait for coords; Fix: chain drawHighlight when coordinates loads.

Highlight position — PdfViewer.tsx drawHighlight() overlay outside page layer; Fix: position overlay inside active page element.

Word coordinate match — findIndex on first word of highlight_start only; multi-word phrases often fail (console.warn path); Fix: sliding window match across pageData.words.

Conversational flow — prefix absent → conversational prompt — Correct in main.py; frontend free-text handleSend sends unprefixed message.

ChatRequest.file_id — always null; active file not sent to backend; Fix: pass activeFile.file_id from page.tsx.

Classification on upload — Correct: /upload calls classify_document and writes _meta.json.

Coordinates on upload — Correct: PDF upload writes _coords.json.

useFiles coordinate fetch — no frontend pre-fetch; acceptable because PdfViewer fetches on mount — Correct by design.

Priority Fix List
CRITICAL

firebase-key.json and .env in project tree (Dimension 1 #5–6).
No [PAGE n] markers → source_page null → citation journey broken (D2 #1, D5 #1).
extract_design_values ignores uploaded PROJECT text (D2 #2, D5 #2).
project_file_id / standard_file_id not injectable by Claude from context (D3 #5–6, D5 #3–4).
PdfViewer highlight overlay positioning broken (D3 #10–11, D5 #16).
No gitignore / build artifacts / secrets discipline (D1 #1, #7–8).
HIGH 7. Streaming shows raw <table> JSON during compliance response (D3 #13–14, D5 #11). 8. Global Semaphore(1) blocks concurrent chats (D2 #8). 9. SSE CORS hardcoded to port 3000 only (D2 #9). 10. onTable immutable update bug (D3 #1, D5 #10). 11. Static /uploads without auth (D2 #23). 12. MCP meta-tools exposed to Claude (D2 #18). 13. Classification failure defaults to PROJECT (D2 #10). 14. REVIEW vs WARN verdict mismatch (D2 #17, D5 #8). 15. No root README / docker-compose (D1 #3–4).

MEDIUM 16. get_max_tokens and _clause_cache dead code (D2 #3–4). 17. file_id always null in chat request (D3 #4, D5 #19). 18. getMessages() anti-pattern (D3 #3). 19. No AbortController on SSE (D3 #2). 20. classify_document fragile parsing (D2 #11). 21. Unpinned pdfplumber and npm "latest" deps (D2 #12, D3 #18). 22. next.config.js hardcoded API URL (D3 #17). 23. FileSidebar missing classification badges per WORKFLOW (D4 prototype diff, D3). 24. ExcelViewer light theme breaks dark shell (D3 #15). 25. Admin backfill unauthenticated (D2 #15).

LOW 26. .DS_Store files (D1 #14). 27. Duplicate Citation/ActiveCitation types (D3 #7). 28. word file type in types never used (D3 #6). 29. console.error in production components (D3 #19). 30. Chip label length vs prototype (D4). 31. worker-loader webpack rule unused (D3 #25). 32. aiofiles unused dependency (D2 #13). 33. Civils.ai reference typography/headings/RED-AMBER legend (D4 — polish).

Distance From Production Ready
A senior engineer opening this tree would treat it as an advanced prototype, not a shippable product. Secrets and Firebase credentials sit beside source; build outputs and virtualenv bulk the tree; there is no git history or CI. The backend implements streaming, MCP tooling, and classification, but the compliance pipeline described in prompts does not match the MCP implementation (Firestore RAG vs uploaded PDF text), page-aware citations are not possible without reader changes, and the global semaphore makes the API a single-lane bottleneck. The frontend compiles cleanly and the chip/hidden-prompt path works, but citation highlighting—the core differentiator—is structurally broken in PdfViewer, and compliance tables likely stream as raw JSON before render. Fixing page markers, file_id injection in context, tool/input alignment, and highlight positioning is weeks of focused work; production also requires auth, secret management, tests, observability, and removal of meta-tools from the model surface.

Distance From Reference UI
Against media/reference/ (Civils.ai), the gap is large: reference is light-themed, two-panel PDF+outputs layouts with RED/AMBER/GREEN risk language, numeric citation pills, Summary/Detailed Answer hierarchy, and lavender PDF highlights. COMPLY’s dark three-panel shell is closer to media/prototype/ui three part viewer design.png (~7/10 fidelity to its own prototype) than to the reference folder (~3/10). Minimum work to close the reference gap: (1) restyle chat output blocks (headings, legend, status vocabulary, numeric badges), (2) widen chat column and simplify table column set to match risk-table reference, (3) strip default PDF layout chrome and fix in-page highlight, (4) add reference footer and “Answer Reference(s)” strip with page pills, (5) optional light/dark theme toggle if reference is mandatory. That is largely CSS/component work if data/handoffs are fixed first; without handoff fixes, prettier UI still will not navigate citations correctly.