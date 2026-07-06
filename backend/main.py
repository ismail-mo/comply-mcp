"""COMPLY API — FastAPI backend.

Token / rate-limit architecture:
- The chat loop uses the ASYNC Anthropic client (no event-loop blocking) with
  real 429/529 retry + exponential backoff wrapped around the stream entry.
- Prompt caching (cache_control) on the tool list and system prompt: the stable
  ~2K-token prefix is cached, so loop iterations and follow-up turns don't
  re-bill it — and cache reads don't count toward the TPM ceiling.
- MCP tools return COMPRESSED structured JSON (see backend/mcp/server.py), so
  accumulated tool results stay small across the agentic loop. Heavy extraction
  and comparison run inside the tools as independent small API calls.
- History is trimmed server-side; tool results are size-capped; the agentic
  loop has a hard iteration cap.
- Whole-document endpoints are gone: all document access flows through chunk
  retrieval (project_chunks / code_chunks / design_chunks).
"""

import asyncio
import json
import logging
import os
import random
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, UploadFile
from openpyxl import load_workbook
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal, Optional

from mcp_client import MCPClient
from file_reader import read_file, read_pdf_sample, extract_pdf_coordinates
from services.rag import PROJECT_COLLECTION, delete_project_chunks, embed_project_file

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("comply.main")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3001,http://localhost:3002",
    ).split(",")
    if origin.strip()
]
MAX_CONCURRENT_CHATS = int(os.getenv("MAX_CONCURRENT_CHATS", "3"))
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

MAX_TOOL_ROUNDS = 12          # hard cap on the agentic loop
MAX_TOOL_RESULT_CHARS = 16000  # safety cap on any single tool result
MAX_HISTORY_MESSAGES = 8       # server-side history trim
MAX_HISTORY_CHARS = 4000       # per-message cap

anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
sync_anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv"}

_coords_cache: dict = {}
_COORDS_CACHE_MAX = 8
_request_lock = asyncio.Semaphore(MAX_CONCURRENT_CHATS)
_in_flight_chats = 0

COMPLIANCE_AUDIT_PREFIX = "[COMPLIANCE_AUDIT]"

COMPLIANCE_SYSTEM_PROMPT = """You are COMPLY, an AI engineering compliance checker. You help
engineers verify that their design documents and specifications
meet relevant standards and codes (Eurocodes, QCS, BS standards).

WORKFLOW — follow this exact sequence for every message:

STEP 1 — IDENTIFY FILE TYPES IN CONTEXT
Read the conversation history. Identify which messages list
[STANDARD DOCUMENTS AVAILABLE] and which list [PROJECT DOCUMENTS
AVAILABLE]. Documents are referenced by file_id only — their text
is NEVER in the conversation. All document access goes through tools.

STEP 2 — EXTRACT DESIGN VALUES FROM PROJECT DOCUMENTS
Call extract_design_values ONCE per PROJECT file_id. It returns a
structured list of design claims (parameter, value, unit, page,
source_quote). If you need more evidence call search_documents with
source_filter="project" and the same file_id. If no PROJECT document
is available, state this clearly and do not run a compliance check.

STEP 3 — RETRIEVE CLAUSES
Select the most critical claims (at most 8) and call
retrieve_code_clauses once per distinct parameter with the relevant
code ("EC1", "EC3", or "client requirements"). The tool returns
COMPRESSED clause facts: clause_number, code, page, requirement,
formula, threshold, and a verbatim excerpt. Never use training-data
clause values — tool results only.

STEP 4 — COMPARE
For each claim/clause pair call compare_value_to_clause. Use its
verdict (PASS/FAIL/WARN), utilization and explanation.

STEP 5 — BUILD THE TABLE
One row per finding (aim for 5-10 high-value rows). Populate:

  PROJECT citation fields (where the issue was found):
    reference_text: the claim's source_quote (verbatim, max 30 words)
    source_page: the claim's page number (integer or null)
    highlight_start: first 5 words of reference_text
    highlight_end: last 5 words of reference_text
    project_file_id: the PROJECT file_id used

  STANDARD citation fields (what standard governs):
    standard_clause: e.g. "EC3 §6.3.2" (from clause_number + code)
    standard_page: page from retrieve_code_clauses, or null
    standard_text: the verbatim excerpt from retrieve_code_clauses,
                   or null
    standard_file_id: file_id of the matching uploaded STANDARD
                      document (match by source: eurocode1 → the EC1
                      upload, eurocode3 → the EC3 upload), or null

Never invent citation fields. Never guess page numbers. If uncertain
write null. For findings about ABSENT content (e.g. "no deflection
check is presented") there is no quotable evidence: set
reference_text, source_page, highlight_start and highlight_end all
to null rather than paraphrasing.

TOOL RESTRICTION — write_audit_report:
Only call write_audit_report when the engineer explicitly asks for a
report file ("generate report", "download report", "save audit").

STEP 6 — WRITE SUMMARY
Write the summary last, after all tool calls complete.

EFFICIENCY RULES:
- Never repeat a tool call with identical parameters.
- Batch independent tool calls in a single response where possible.
- At most ~15 tool calls total per audit.
- NEVER write prose in a response that contains tool calls. Call
  tools silently — no progress narration, no "I will now…". Your
  only prose output is the final PART 1 + PART 2 response after all
  tool calls are complete.

Every response must follow this exact two-part structure:

PART 1 — SUMMARY:
A concise narrative paragraph (max 150 words). Every factual claim
carries a citation marker [n] matching table row n (1-indexed, in
the order the rows appear in your table). State how many documents
were analysed and the overall compliance status.

PART 2 — TABLE:
Immediately after the summary, a JSON array wrapped in <table></table>
tags. One object per finding with exactly these fields:

  status: "FAIL" | "WARN" | "PASS"
  category: engineering domain e.g. "Structural", "Foundation Design"
  issue: plain-language description (your own synthesis)
  reference_text: verbatim PROJECT excerpt, max 30 words
  source_page: integer or null
  highlight_start: first 5 words of reference_text
  highlight_end: last 5 words of reference_text
  project_file_id: string
  standard_clause: e.g. "EC3 §6.3.2" or "N/A"
  standard_page: integer or null
  standard_text: verbatim standard excerpt or null
  standard_file_id: string or null
  party_affected: e.g. "Design Engineer" ("—" for PASS rows)
  recommendation: specific action ("None — compliant" for PASS)

Rules you must never break:
- Both PART 1 and PART 2, always. <table> tags on their own lines.
- Do NOT write the literal headings "PART 1" / "PART 2 — TABLE" or
  "---" separators, and no preamble like "Here is the audit result".
  Begin directly with the summary paragraph, then the <table> block.
- Rows ordered FAIL first, then WARN, then PASS.
- Citation numbers match table row order (row 1 = [1]).
- reference_text only from tool results — never invented.
- standard_page/standard_text only from tool results — never memory.
- If data is insufficient to verify a requirement, use WARN.
- Valid parseable JSON inside <table>. No markdown fences."""

CONVERSATIONAL_SYSTEM_PROMPT = """You are COMPLY, an AI engineering compliance assistant.
Answer the engineer's question directly and concisely.
Use plain text only. No tables. No JSON. No citation markers.
Reference documents and findings naturally in prose.
Be precise and technical. Use engineering terminology.
Use MCP tools only when genuinely needed for accuracy; do not force tool calls."""


def is_compliance_audit(message: str) -> bool:
    return message.strip().startswith(COMPLIANCE_AUDIT_PREFIX)


def clean_message(message: str) -> str:
    return message.replace(COMPLIANCE_AUDIT_PREFIX, "", 1).strip()


def extract_table(response: str) -> list | None:
    matches = re.findall(r"<table>(.*?)</table>", response, re.DOTALL)
    if not matches:
        return None
    # The final table is authoritative if the model emitted more than one.
    for raw in reversed(matches):
        try:
            rows = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and str(row.get("status", "")).upper() == "REVIEW":
                    row["status"] = "WARN"
            return rows
    return None


async def classify_document(filename: str, text_sample: str) -> str:
    filename_lower = filename.lower()
    standard_filename_tokens = (
        "ec1", "ec2", "ec3", "ec4", "ec5", "ec6", "ec7", "ec8",
        "eurocode", "eur", "en 199", "en199", "bs ", "bs-", "qcs",
        "client_req", "clientreq", "requirements", "specification",
    )
    if any(token in filename_lower for token in standard_filename_tokens):
        return "STANDARD"

    project_filename_tokens = (
        "design", "calculation", "calc", "report", "solution",
        "coursework", "project", "submission",
    )
    if any(token in filename_lower for token in project_filename_tokens):
        return "PROJECT"

    try:
        prompt = (
            "Classify this engineering document as either STANDARD "
            "or PROJECT based on the filename and document sample.\n\n"
            "STANDARD documents — published codes, standards, and "
            "specifications (Eurocodes, EN 199x, British Standards, QCS, "
            "AASHTO, ACI, AISC, ISO) and client requirement documents.\n\n"
            "PROJECT documents — engineer-produced project-specific "
            "documents: design reports, calculation packs, geotechnical or "
            "site investigation reports, coursework submissions.\n\n"
            f"Filename: {filename}\n\n"
            "Document sample (first 500 characters):\n"
            f"{text_sample[:500]}\n\n"
            "Reply with exactly one word: STANDARD or PROJECT"
        )
        response = await anthropic_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=10,
            system="Reply with exactly one word: STANDARD or PROJECT.",
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.content[0].text.strip().upper()
        match = re.match(r"^(STANDARD|PROJECT)\b", result)
        if not match:
            raise ValueError(f"Unexpected classification response: {result!r}")
        return match.group(1)
    except Exception as exc:
        logger.error("classify_document error for %s: %s", filename, exc)
        return "UNKNOWN"


def _ext_to_type(ext: str) -> str:
    if ext == ".pdf":
        return "pdf"
    return "excel"


def _safe_filename(name: str) -> str:
    base = Path(name or "upload").name  # strip any path components
    base = re.sub(r"[^\w.\- ()\[\]]", "_", base)
    return base[:120] or "upload"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    mcp = MCPClient()
    await mcp.start()
    app.state.mcp = mcp
    logger.info("Startup complete — MCP connected: %s", mcp.connected)
    yield
    await app.state.mcp.stop()
    logger.info("Shutdown complete")


app = FastAPI(title="COMPLY API", lifespan=lifespan)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    file_id: Optional[str] = None
    history: list[ChatMessage] = Field(default_factory=list)


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    type: Literal["pdf", "excel"]
    classification: Literal["STANDARD", "PROJECT", "UNKNOWN"]
    rag_status: Optional[Literal["not_applicable", "pending", "embedded", "failed"]] = None
    rag_collection: Optional[str] = None
    rag_error: Optional[str] = None


class CellEdit(BaseModel):
    sheet: str
    row: int
    col: int
    value: str


def write_file_meta(file_id: str, updates: dict) -> dict:
    meta_path = UPLOAD_DIR / f"{file_id}_meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            meta = {}
    meta.update(updates)
    meta_path.write_text(json.dumps(meta))
    return meta


def embed_project_file_task(file_id: str, filename: str, path: str) -> None:
    try:
        result = embed_project_file(file_id=file_id, filename=filename, path=path)
        write_file_meta(
            file_id,
            {
                "rag_status": "embedded",
                "rag_collection": result["collection"],
                "rag_error": None,
                "rag_chunks": result["chunks"],
                "rag_pages": result["pages"],
            },
        )
        logger.info("PROJECT RAG embedded: %s (%d chunks)", file_id, result["chunks"])
    except Exception as exc:
        logger.error("PROJECT RAG embedding failed for %s: %s", file_id, exc)
        write_file_meta(
            file_id,
            {
                "rag_status": "failed",
                "rag_collection": PROJECT_COLLECTION,
                "rag_error": str(exc),
            },
        )


@app.get("/health")
async def health():
    mcp = app.state.mcp
    return {
        "status": "ok",
        "mcp_connected": mcp.connected,
        "mcp_pid": None,
        "tools": [t["name"] for t in mcp.get_tools()],
        "cache_size": {
            "coords": len(_coords_cache),
            "in_flight_chats": _in_flight_chats,
        },
    }


@app.post("/upload", response_model=UploadResponse)
async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    original_name = _safe_filename(file.filename or "")
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    file_id = f"{uuid.uuid4()}_{original_name}"
    dest = UPLOAD_DIR / file_id

    contents = await file.read()
    dest.write_bytes(contents)
    logger.info("Uploaded: %s", file_id)

    file_type = _ext_to_type(ext)

    try:
        if file_type == "pdf":
            sample = await asyncio.to_thread(read_pdf_sample, str(dest), 3)
        else:
            sample = (await asyncio.to_thread(read_file, str(dest), file_type))[:2000]
    except Exception:
        sample = ""

    classification = await classify_document(original_name, sample)
    logger.info("Classified %s as %s", file_id, classification)

    rag_status = "pending" if file_type == "pdf" and classification == "PROJECT" else "not_applicable"
    rag_collection = PROJECT_COLLECTION if rag_status == "pending" else None

    write_file_meta(file_id, {
        "classification": classification,
        "filename": original_name,
        "type": file_type,
        "rag_status": rag_status,
        "rag_collection": rag_collection,
        "rag_error": None,
    })

    if file_type == "pdf":
        try:
            coords = await asyncio.to_thread(extract_pdf_coordinates, str(dest))
            coords_path = UPLOAD_DIR / f"{file_id}_coords.json"
            coords_path.write_text(json.dumps(coords))
            logger.info("Coordinates stored: %s", file_id)
        except Exception as exc:
            logger.error("Coordinate extraction failed for %s: %s", file_id, exc)

    if rag_status == "pending":
        background_tasks.add_task(embed_project_file_task, file_id, original_name, str(dest))

    return {
        "file_id": file_id,
        "filename": original_name,
        "type": file_type,
        "classification": classification,
        "rag_status": rag_status,
        "rag_collection": rag_collection,
        "rag_error": None,
    }


@app.get("/files", response_model=list[UploadResponse])
async def list_files():
    if not UPLOAD_DIR.exists():
        return []
    result = []
    for f in UPLOAD_DIR.iterdir():
        if not f.is_file():
            continue
        if f.name.endswith("_meta.json") or f.name.endswith("_coords.json"):
            continue
        ext = f.suffix.lower()
        parts = f.name.split("_", 1)
        original = parts[1] if len(parts) == 2 else f.name

        meta_path = UPLOAD_DIR / f"{f.name}_meta.json"
        classification = "PROJECT"
        rag_status = "not_applicable"
        rag_collection = None
        rag_error = None
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                classification = meta.get("classification", "PROJECT")
                rag_status = meta.get("rag_status", "not_applicable")
                rag_collection = meta.get("rag_collection")
                rag_error = meta.get("rag_error")
            except Exception:
                pass

        result.append({
            "file_id": f.name,
            "filename": original,
            "type": _ext_to_type(ext),
            "classification": classification,
            "rag_status": rag_status,
            "rag_collection": rag_collection,
            "rag_error": rag_error,
        })
    return result


@app.delete("/files/{file_id}")
async def delete_file(file_id: str):
    path = UPLOAD_DIR / file_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    path.unlink()
    meta_path = UPLOAD_DIR / f"{file_id}_meta.json"
    if meta_path.exists():
        meta_path.unlink()
    coords_path = UPLOAD_DIR / f"{file_id}_coords.json"
    if coords_path.exists():
        coords_path.unlink()
    _coords_cache.pop(file_id, None)
    # Remove embedded chunks so deleted documents stop surfacing in RAG.
    try:
        await asyncio.to_thread(delete_project_chunks, file_id)
    except Exception as exc:
        logger.warning("RAG chunk cleanup failed for %s: %s", file_id, exc)
    logger.info("Deleted: %s", file_id)
    return {"deleted": True}


@app.get("/files/{file_id}/classification")
async def get_file_classification(file_id: str):
    meta_path = UPLOAD_DIR / f"{file_id}_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Classification metadata not found")
    try:
        meta = json.loads(meta_path.read_text())
        return {"file_id": file_id, "classification": meta.get("classification", "PROJECT")}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read classification metadata")


@app.get("/files/{file_id}/coordinates")
async def get_file_coordinates(file_id: str):
    if file_id in _coords_cache:
        return _coords_cache[file_id]
    coords_path = UPLOAD_DIR / f"{file_id}_coords.json"
    if not coords_path.exists():
        raise HTTPException(status_code=404, detail="Coordinates not found for this file")
    try:
        data = json.loads(coords_path.read_text())
        if len(_coords_cache) >= _COORDS_CACHE_MAX:
            _coords_cache.pop(next(iter(_coords_cache)))
        _coords_cache[file_id] = data
        return data
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read coordinates file")


@app.post("/admin/backfill-coordinates")
async def backfill_coordinates(x_admin_api_key: str | None = Header(default=None)):
    if ADMIN_API_KEY and x_admin_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Admin endpoint disabled")
    if not UPLOAD_DIR.exists():
        return {"backfilled": 0, "skipped": 0, "errors": []}
    backfilled, skipped, errors = 0, 0, []
    for f in UPLOAD_DIR.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() != ".pdf":
            continue
        if f.name.endswith("_meta.json") or f.name.endswith("_coords.json"):
            continue
        coords_path = UPLOAD_DIR / f"{f.name}_coords.json"
        if coords_path.exists():
            skipped += 1
            continue
        try:
            coords = await asyncio.to_thread(extract_pdf_coordinates, str(f))
            coords_path.write_text(json.dumps(coords))
            logger.info("Backfilled coordinates: %s", f.name)
            backfilled += 1
        except Exception as exc:
            logger.error("Backfill failed for %s: %s", f.name, exc)
            errors.append({"file": f.name, "error": str(exc)})
    return {"backfilled": backfilled, "skipped": skipped, "errors": errors}


@app.patch("/files/{file_id}/cell")
async def edit_cell(file_id: str, request: CellEdit):
    path = UPLOAD_DIR / file_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    ext = path.suffix.lower()
    if ext not in {".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="File is not an Excel file")
    wb = load_workbook(path)
    if request.sheet not in wb.sheetnames:
        raise HTTPException(status_code=404, detail="Sheet not found")
    ws = wb[request.sheet]
    ws.cell(row=request.row + 2, column=request.col + 1).value = request.value
    wb.save(path)
    logger.info("Cell edit saved: %s [%s] r%d c%d", file_id, request.sheet, request.row, request.col)
    return {"saved": True, "sheet": request.sheet, "row": request.row, "col": request.col, "value": request.value}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


TOOL_STATUS_LABELS = {
    "extract_design_values": "Extracting design values",
    "retrieve_code_clauses": "Retrieving code clauses",
    "compare_value_to_clause": "Checking compliance",
    "search_documents": "Searching documents",
    "write_audit_report": "Writing audit report",
}


@app.post("/chat")
async def chat(req: ChatRequest):
    async def generate():
        global _in_flight_chats
        async with _request_lock:
            _in_flight_chats += 1
            full_response = ""
            try:
                compliance_mode = is_compliance_audit(req.message)
                user_message = clean_message(req.message) if compliance_mode else req.message
                system_prompt = (
                    COMPLIANCE_SYSTEM_PROMPT if compliance_mode else CONVERSATIONAL_SYSTEM_PROMPT
                )
                max_tokens = 8192 if compliance_mode else 1024

                # Server-side history trim: last N messages, each size-capped.
                trimmed = req.history[-MAX_HISTORY_MESSAGES:]
                messages = [
                    {"role": m.role, "content": m.content[:MAX_HISTORY_CHARS]}
                    for m in trimmed
                ]
                messages.append({"role": "user", "content": user_message[:MAX_HISTORY_CHARS]})

                await app.state.mcp.ensure_connected()
                all_tools = app.state.mcp.get_tools()
                compliance_tool_names = {
                    "search_documents",
                    "retrieve_code_clauses",
                    "extract_design_values",
                    "compare_value_to_clause",
                    "write_audit_report",
                }
                conversational_tool_names = {"search_documents", "retrieve_code_clauses"}
                runtime_tool_names = (
                    compliance_tool_names if compliance_mode else conversational_tool_names
                )
                tools = [
                    dict(tool) for tool in all_tools if tool.get("name") in runtime_tool_names
                ]
                # Prompt caching: cache breakpoint after tools + system so the
                # stable prefix is cached across loop iterations and turns.
                if tools:
                    tools[-1]["cache_control"] = {"type": "ephemeral"}
                kwargs = dict(
                    model=ANTHROPIC_MODEL,
                    max_tokens=max_tokens,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=messages,
                )
                if tools:
                    kwargs["tools"] = tools

                stop_reason = None
                for round_index in range(MAX_TOOL_ROUNDS):
                    assistant_content = []
                    tool_use_blocks = []
                    current_tool: dict | None = None
                    round_text_emitted = False
                    final_message = None

                    # Real retry: the HTTP request fires inside the async with,
                    # so 429/529/overloaded is caught here. Only retry if this
                    # round hasn't emitted tokens yet (no duplicates).
                    for attempt in range(4):
                        try:
                            async with anthropic_client.messages.stream(**kwargs) as stream:
                                async for event in stream:
                                    etype = getattr(event, "type", None)

                                    if etype == "content_block_start":
                                        block = event.content_block
                                        if block.type == "text":
                                            assistant_content.append({"type": "text", "text": ""})
                                        elif block.type == "tool_use":
                                            current_tool = {
                                                "type": "tool_use",
                                                "id": block.id,
                                                "name": block.name,
                                                "input_raw": "",
                                            }
                                            assistant_content.append(current_tool)

                                    elif etype == "content_block_delta":
                                        delta = event.delta
                                        if delta.type == "text_delta":
                                            text = delta.text
                                            full_response += text
                                            round_text_emitted = True
                                            yield _sse({"type": "token", "content": text})
                                            for blk in reversed(assistant_content):
                                                if blk.get("type") == "text":
                                                    blk["text"] += text
                                                    break
                                        elif delta.type == "input_json_delta" and current_tool is not None:
                                            current_tool["input_raw"] += delta.partial_json

                                    elif etype == "content_block_stop":
                                        if current_tool is not None:
                                            try:
                                                current_tool["input"] = json.loads(
                                                    current_tool["input_raw"] or "{}"
                                                )
                                            except json.JSONDecodeError:
                                                current_tool["input"] = {}
                                            del current_tool["input_raw"]
                                            tool_use_blocks.append(current_tool)
                                            current_tool = None

                                final_message = await stream.get_final_message()
                            break  # stream completed

                        except (anthropic.RateLimitError, anthropic.APIStatusError,
                                anthropic.APIConnectionError) as exc:
                            status = getattr(exc, "status_code", None)
                            retryable = isinstance(
                                exc, (anthropic.RateLimitError, anthropic.APIConnectionError)
                            ) or status in (429, 500, 503, 529)
                            if not retryable or attempt == 3 or round_text_emitted:
                                raise
                            wait = 2 ** attempt + random.uniform(0, 1)
                            logger.warning(
                                "Anthropic %s — retrying in %.1fs (attempt %d)",
                                status or type(exc).__name__, wait, attempt + 1,
                            )
                            yield _sse({
                                "type": "status",
                                "message": "Rate limited — retrying shortly…",
                            })
                            # Reset partial state accumulated before failure.
                            assistant_content = []
                            tool_use_blocks = []
                            current_tool = None
                            await asyncio.sleep(wait)

                    if final_message is None:
                        raise RuntimeError("Model stream failed after retries")

                    stop_reason = final_message.stop_reason
                    if stop_reason != "tool_use" or not tool_use_blocks:
                        break

                    api_assistant_content = []
                    for blk in assistant_content:
                        if blk["type"] == "text":
                            api_assistant_content.append({"type": "text", "text": blk["text"]})
                        elif blk["type"] == "tool_use":
                            api_assistant_content.append({
                                "type": "tool_use",
                                "id": blk["id"],
                                "name": blk["name"],
                                "input": blk.get("input", {}),
                            })

                    # Any narration streamed in a tool-calling round is noise —
                    # tell the client to clear it (a status line replaces it).
                    if round_text_emitted:
                        yield _sse({"type": "reset_text"})

                    if len(tool_use_blocks) == 1:
                        label = TOOL_STATUS_LABELS.get(
                            tool_use_blocks[0]["name"], f"Running {tool_use_blocks[0]['name']}"
                        )
                        yield _sse({"type": "status", "message": f"{label}…"})
                    else:
                        names = {tb["name"] for tb in tool_use_blocks}
                        labels = " + ".join(
                            TOOL_STATUS_LABELS.get(n, n) for n in sorted(names)
                        )
                        yield _sse({
                            "type": "status",
                            "message": f"{labels} ({len(tool_use_blocks)} calls)…",
                        })

                    # Execute this round's tools concurrently (bounded).
                    tool_semaphore = asyncio.Semaphore(4)

                    async def run_tool(tb: dict) -> dict:
                        async with tool_semaphore:
                            logger.info(
                                "Calling MCP tool: %s %s", tb["name"], tb.get("input", {})
                            )
                            is_error = False
                            try:
                                mcp_result = await app.state.mcp.call_tool(
                                    tb["name"], tb.get("input", {})
                                )
                                first = mcp_result.content[0] if mcp_result.content else None
                                result_text = (
                                    getattr(first, "text", None) or "Tool returned no content"
                                )
                            except Exception as tool_exc:
                                logger.error(
                                    "MCP tool error (%s): %s", tb["name"], tool_exc
                                )
                                result_text = json.dumps({"error": str(tool_exc)[:500]})
                                is_error = True
                            if len(result_text) > MAX_TOOL_RESULT_CHARS:
                                result_text = (
                                    result_text[:MAX_TOOL_RESULT_CHARS]
                                    + '… [truncated — result exceeded size cap]'
                                )
                            block = {
                                "type": "tool_result",
                                "tool_use_id": tb["id"],
                                "content": result_text,
                            }
                            if is_error:
                                block["is_error"] = True
                            return block

                    tool_results = list(
                        await asyncio.gather(*(run_tool(tb) for tb in tool_use_blocks))
                    )

                    messages.append({"role": "assistant", "content": api_assistant_content})
                    messages.append({"role": "user", "content": tool_results})
                else:
                    logger.warning("Agentic loop hit MAX_TOOL_ROUNDS cap")
                    yield _sse({
                        "type": "status",
                        "message": "Stopped after maximum tool rounds — results may be partial.",
                    })

                if stop_reason == "max_tokens":
                    yield _sse({
                        "type": "status",
                        "message": "Response reached the length limit and may be truncated.",
                    })

                table = extract_table(full_response) if compliance_mode else None
                if table is not None:
                    yield _sse({"type": "table", "data": table})

            except Exception as e:
                logger.exception("Chat stream error")
                err_msg = str(e)
                lowered = err_msg.lower()
                if "rate limit" in lowered or "429" in err_msg or "overloaded" in lowered:
                    err_msg = "Rate limit reached. Please wait a moment and try again."
                elif "credit" in lowered or "billing" in lowered:
                    err_msg = "Anthropic API credits exhausted — check the account billing."
                yield _sse({"type": "error", "message": err_msg})
            finally:
                _in_flight_chats = max(0, _in_flight_chats - 1)
                yield _sse({"type": "done"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
