# COMPLY — Build System Guide

## How This System Works
Three files control the build. Read all three before touching any code.

CLAUDE.md (this file) — system overview, file conventions, media references
WORKFLOW.md — complete build plan, all steps with overview and task descriptions
STEP.md — current active step broken into detailed stages

## Project Structure
Frontend lives at: ../frontend/
Backend lives at: ../backend/main.py
MCP server lives at: ../backend/mcp/server.py
Media images live at: ../media/

## Full Request Workflow
FRONTEND (Next.js)

Engineer clicks "Check EC3" chip

↓

ChatSidebar.tsx fires onSend(hidden_prompt)
Chat bubble shows "Check EC3 Compliance" only

↓

useChat.ts sendMessage()
Detects [COMPLIANCE_AUDIT] prefix
Strips prefix from visible message
Builds history with file context labels
Calls streamChat() in api.ts

↓

api.ts POST /chat to localhost:8000
SSE connection opens

BACKEND (FastAPI)

main.py POST /chat receives request

↓

is_compliance_audit() detects prefix
Selects COMPLIANCE_SYSTEM_PROMPT or CONVERSATIONAL_SYSTEM_PROMPT
Cleans prefix from message

↓

ensure_connected() checks MCP subprocess alive
get_tools() returns available tool list

↓

Anthropic API call with:
- system prompt
- message history
- MCP tools attached
- max_tokens based on query type

CLAUDE API + MCP TOOLS

Claude receives message + tools

↓

Calls extract_design_values
→ receives PROJECT file_id from context
→ queries Firestore project_chunks for uploaded PROJECT evidence
→ falls back to document_text/design_chunks only for legacy/debug paths
→ returns structured parameter list

↓

Calls retrieve_code_clauses
→ MCP server queries Firebase Firestore
→ Gemini embedding on query
→ vector search on code_chunks collection
→ returns clause text, page, source

↓

Calls compare_value_to_clause
→ compares extracted value vs clause requirement
→ returns PASS/FAIL/WARN with margin

↓

Claude writes Summary + <table> JSON

FIREBASE (Firestore)

Queried by retrieve_code_clauses tool

Collections:
- code_chunks → EC1, EC3 clauses
- project_chunks → uploaded PROJECT document chunks keyed by file_id
- design_chunks → legacy embedded design/client requirement chunks used as fallback

Returns top K matching chunks per query.
Each chunk: text, page, clause_number, source.

BACK TO BACKEND

Stream tokens back to frontend via SSE

↓

After stream completes:
extract_table() parses <table>...</table>
Fires data: {"type":"table","data":[...]}
Fires data: {"type":"done"}

BACK TO FRONTEND

api.ts SSE parser receives chunks
onToken → appends to last assistant message
onTable → attaches table to last assistant message
onDone → sets isStreaming false

↓

useChat.ts attaches table to message
Parses [n] markers into Citation objects

↓

ChatSidebar.tsx renders:
- getSummaryText strips <table> block
- SummaryText renders [n] as PROJECT badges
- ComplianceTable renders below summary
- PROJECT badge onClick → onCitationClick
- STANDARD badge onClick → onCitationClick

↓

page.tsx setActiveCitation

↓

FileViewer routes by activeCitation.file_id

↓

PdfViewer fetches _coords.json
Searches for highlight_start text
Draws yellow rectangle
jumpToPage(activeCitation.page - 1)

## How To Use The Media Folder
The ../media/ folder contains two important visual comparison folders:

- ../media/reference/ contains inspiration images for the target UI design.
- ../media/prototype/ contains images of the current UI we have designed so far.

When working on any UI stage, compare the relevant images in both folders.
Use ../media/reference/ to understand the intended visual direction, layout,
spacing, hierarchy, and interaction feel. Use ../media/prototype/ to understand
the current implementation, what needs fixing, how far it is from the reference,
and what can be improved.

Look for images by matching the filename to the component or feature being built.

Image naming convention: descriptive lowercase with spaces replaced by underscores.

Examples:
- When refactoring the UI and sidebar design, look for: sidebar_ui.png
- When looking for reference to text output layout in chat sidebar, look for: text_sidebar_output.png
- When building the compliance table rendering, look for: compliance_table.png
- When working on PDF viewer citation highlights, look for: pdf_highlight.png
- When building the file upload zone, look for: file_upload_zone.png

If no matching image exists in either folder, proceed without visual reference.
If matching images exist, use them to evaluate the gap between the current UI and
the target reference, then improve the implementation to better match the
reference style, layout, and spacing.

## How To Use WORKFLOW.md
WORKFLOW.md contains the full build plan.
Read it to understand where the current step fits in the overall system.
Do not jump ahead. Each step depends on the one before it.

## How To Use STEP.md
STEP.md contains the current active step only.
It breaks the step into stages — Stage 1, Stage 2, Stage 3 etc.
Complete each stage fully and confirm it passes before moving to the next.
Do not proceed to the next stage if the current stage has unresolved failures.

## Build Principles
- One stage at a time
- Confirm before proceeding
- Never skip a stage to get to a later one
- If a stage fails, fix it before moving forward
- Check ../media/reference/ and ../media/prototype/ for visual comparison at every UI stage
- Check WORKFLOW.md for context, STEP.md for instructions
