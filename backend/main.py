import asyncio
import json
import logging
import os
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
from services.rag import PROJECT_COLLECTION, embed_project_file

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

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv"}

_coords_cache: dict = {}
_request_lock = asyncio.Semaphore(MAX_CONCURRENT_CHATS)
_in_flight_chats = 0

COMPLIANCE_AUDIT_PREFIX = "[COMPLIANCE_AUDIT]"

COMPLIANCE_SYSTEM_PROMPT = """You are COMPLY, an AI engineering compliance checker. You help
engineers verify that their design documents and specifications
meet relevant standards and codes (Eurocodes, QCS, BS standards).

WORKFLOW — follow this exact sequence for every message:

STEP 1 — IDENTIFY FILE TYPES IN CONTEXT
Read the conversation history. Identify which messages are
labelled [STANDARD DOCUMENT] and which are [PROJECT DOCUMENT].

STANDARD DOCUMENT files:
  These are Eurocode 1, Eurocode 3, or client requirement
  documents uploaded for visual reference only.
  Do NOT read their content.
  Do NOT extract values from them.
  Do NOT compare them against anything.
  When you need clauses from a Eurocode or client requirement,
  call retrieve_code_clauses — never read the standard text
  directly from context.

PROJECT DOCUMENT files:
  These are the engineer's own design reports or project
  reports. They are referenced by file_id and embedded in
  Firestore project_chunks. Do NOT expect their full text in
  chat history. Use their file_id with MCP tools to retrieve
  and extract evidence.

STEP 2 — EXTRACT DESIGN VALUES FROM PROJECT DOCUMENTS
For each PROJECT document in context call extract_design_values
with file_id set to the PROJECT document file_id. The tool queries
project_chunks and returns a structured list of all design parameters
found. If you need more source evidence, call search_documents with
source_filter="project" and the same file_id. If no PROJECT document
file_id is present, state this clearly and do not proceed with
compliance checking.

STEP 3 — RETRIEVE CLAUSES FROM FIRESTORE
For each extracted design value call retrieve_code_clauses with:
  - the parameter name
  - the value found
  - the relevant standard (Eurocode 1, Eurocode 3, or client
    requirements — infer from context or engineer query)
This queries the Firestore database of embedded standards.
Never use training data or memory for clause requirements.
Always call the tool. Always use the tool result.

STEP 4 — COMPARE VALUES AGAINST CLAUSES
For each value and its retrieved clause call
compare_value_to_clause with the extracted value and the
clause requirement returned by retrieve_code_clauses.
Use the tool result to determine PASS, FAIL, or WARN.

STEP 5 — BUILD THE TABLE
Every table row must be grounded in:
  - A value from a PROJECT document (design report or
    project report) — this is the project citation
  - A clause from Firestore via retrieve_code_clauses
    (Eurocode 1, Eurocode 3, or client requirements)
    — this is the standard citation

For each table row populate these citation fields:

  PROJECT citation fields (where the problem was found):
    reference_text: verbatim excerpt from PROJECT document
    source_page: page number in the PROJECT document
    highlight_start: first 5 words of reference_text
    highlight_end: last 5 words of reference_text
    project_file_id: the file_id of the PROJECT document used in
                     extract_design_values/search_documents

  STANDARD citation fields (what standard was violated):
    standard_clause: clause number e.g. "EC1 §6.3.2" or
                     "EC3 §7.6.2.1" or client req clause
    standard_page: page field returned by retrieve_code_clauses
    standard_text: text field returned by retrieve_code_clauses
    standard_file_id: file_id of the uploaded STANDARD document
                      that matches the source field returned
                      by retrieve_code_clauses
                      (eurocode1, eurocode3, or client req)

Never invent citation fields. Never guess page numbers.
Only populate standard_page and standard_text from actual
tool results. Only populate source_page from actual document
text position. If uncertain write null for that field.

TOOL RESTRICTION — write_audit_report:
Only call write_audit_report when the engineer explicitly requests
a downloadable audit report using words like "generate report",
"download report", or "save audit".
Never call it automatically during a standard compliance check.

STEP 6 — WRITE SUMMARY
Write the summary paragraph last, after all tool calls complete.
Every claim must reference a table row number [n].

EFFICIENCY: Never call the same tool with identical parameters
twice in one response. If you have already retrieved a clause
for a parameter, reuse that result. Batch similar tool calls
where possible — retrieve multiple clauses in a single
retrieve_code_clauses call if the tool supports it.

Every response you give must follow this exact two-part structure.
No exceptions. Never deviate from this format.

PART 1 — SUMMARY:
Write a concise narrative paragraph (maximum 150 words) synthesising
your key findings across all provided documents. Every factual claim
must include a citation marker in square brackets e.g. [1] [2] [3].
Each citation number must correspond to a row in the table below.
Start by stating how many documents were analysed and the overall
compliance status. Use plain engineering language.

PART 2 — TABLE:
Immediately after the summary, output a JSON array wrapped in
<table></table> tags. The array must contain one object per finding.
Each object must have exactly these fields and no others:

  status: "FAIL" or "WARN" or "PASS"
  category: engineering domain e.g. "Foundation Design",
            "Slope Stability", "Drainage", "Structural"
  issue: plain language description of what is wrong or confirmed
         compliant. Claude's own synthesis, not a quote.
  reference_text: verbatim excerpt from the source PROJECT document
                  that supports this finding. Maximum 30 words.
                  Exact quote only.
  source_page: integer page number in the PROJECT document where
               reference_text appears
  highlight_start: first 5 words of reference_text verbatim —
                   used to locate the text in the PDF viewer
  highlight_end: last 5 words of reference_text verbatim —
                 used to locate the end of the highlight
  project_file_id: file_id of the PROJECT document
  standard_clause: the standard and clause number e.g. "EC1 §6.3.2"
                   or "EC3 §7.6.2.1". If no specific clause write "N/A"
  standard_page: integer page number returned by retrieve_code_clauses.
                 null if not available
  standard_text: clause text returned by retrieve_code_clauses.
                 null if not available
  standard_file_id: file_id of the uploaded STANDARD document
                    matching the source from retrieve_code_clauses.
                    null if not available
  party_affected: who owns this issue e.g. "Design Engineer",
                  "Contractor", "Site Engineer".
                  Write "—" for PASS rows with no party.
  recommendation: specific technical action to take.
                  For PASS rows write "None — compliant"

Rules you must never break:
- Never output a response without both PART 1 and PART 2
- Every claim in the summary must have a [n] citation marker
- Citation numbers must match row order in the table (row 1 = [1])
- Never include a finding without reference_text from a PROJECT document
- Never guess or invent reference_text — only quote what is present
- Never populate standard_page or standard_text from memory — tool results only
- Order rows: FAIL first, then WARN, then PASS
- Be precise and technical. Use exact clause references.
- If data is insufficient to verify a requirement write WARN
- The <table> tags must appear on their own lines
- The JSON inside <table> tags must be valid parseable JSON
- Do not include markdown code fences inside the table tags"""

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
    match = re.search(r"<table>(.*?)</table>", response, re.DOTALL)
    if not match:
        return None
    try:
        rows = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and str(row.get("status", "")).upper() == "REVIEW":
            row["status"] = "WARN"
    return rows


async def classify_document(filename: str, text_sample: str) -> str:
    filename_lower = filename.lower()
    standard_filename_tokens = (
        "ec1",
        "ec2",
        "ec3",
        "ec4",
        "ec5",
        "ec6",
        "ec7",
        "ec8",
        "eurocode",
        "eur",
        "en 199",
        "en199",
        "bs ",
        "bs-",
        "qcs",
        "client_req",
        "clientreq",
        "requirements",
        "specification",
    )
    if any(token in filename_lower for token in standard_filename_tokens):
        return "STANDARD"

    project_filename_tokens = (
        "design",
        "calculation",
        "calc",
        "report",
        "solution",
        "coursework",
        "project",
        "submission",
    )
    if any(token in filename_lower for token in project_filename_tokens):
        return "PROJECT"

    try:
        prompt = (
            "Classify this engineering document as either STANDARD "
            "or PROJECT based on the filename and document sample.\n\n"
            "STANDARD documents — published codes, standards, and "
            "specifications. Examples:\n"
            "- Eurocodes: EC1, EC2, EC3, EC4, EC5, EC6, EC7, EC8,\n"
            "  Eurocode 1, Eurocode 3, EN 1990, EN 1991, EN 1992,\n"
            "  EN 1993, EN 1994, EN 1995, EN 1996, EN 1997, EN 1998\n"
            "- British Standards: BS 5950, BS 8004, BS 8110\n"
            "- QCS (Qatar Construction Specification)\n"
            "- AASHTO, ACI, AISC, ISO standards\n"
            "- Client requirement documents, employer requirements,\n"
            "  project brief, project specification issued by a client\n"
            "- Any document whose filename contains: ec1, ec2, ec3,\n"
            "  ec4, ec5, ec6, ec7, ec8, eurocode, eur, bs, qcs,\n"
            "  client_req, clientreq, requirements, specification\n\n"
            "PROJECT documents — engineer-produced project-specific\n"
            "documents. Examples:\n"
            "- Design reports, structural calculation reports\n"
            "- Geotechnical investigation reports\n"
            "- Site investigation reports\n"
            "- Calculation packs and design briefs\n"
            "- Any document produced by an engineering team for a\n"
            "  specific project or coursework submission\n\n"
            f"Filename: {filename}\n\n"
            "Document sample (first 500 characters):\n"
            f"{text_sample[:500]}\n\n"
            "If the filename contains ec1, ec2, ec3, ec4, ec5, ec6,\n"
            "ec7, ec8, eur, eurocode, bs, qcs, client_req, clientreq,\n"
            "requirements, or specification — classify as STANDARD\n"
            "regardless of document content.\n\n"
            "Reply with exactly one word: STANDARD or PROJECT"
        )

        def _call():
            return anthropic_client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=10,
                system="Reply with exactly one word: STANDARD or PROJECT.",
                messages=[{"role": "user", "content": prompt}],
            )

        response = await asyncio.to_thread(_call)
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


class FileListItem(UploadResponse):
    pass


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
        "mcp_pid": mcp.pid,
        "tools": [t["name"] for t in mcp.get_tools()],
        "cache_size": {
            "coords": len(_coords_cache),
            "in_flight_chats": _in_flight_chats,
        },
    }


@app.post("/upload", response_model=UploadResponse)
async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    file_id = f"{uuid.uuid4()}_{file.filename}"
    dest = UPLOAD_DIR / file_id

    contents = await file.read()
    dest.write_bytes(contents)
    logger.info("Uploaded: %s", file_id)

    file_type = _ext_to_type(ext)

    try:
        if file_type == "pdf":
            sample = read_pdf_sample(str(dest), max_pages=3)
        else:
            sample = read_file(str(dest), file_type)[:2000]
    except Exception:
        sample = ""

    classification = await classify_document(
        file.filename, sample)
    logger.info("Classified %s as %s", file_id, classification)

    rag_status = "pending" if file_type == "pdf" and classification == "PROJECT" else "not_applicable"
    rag_collection = PROJECT_COLLECTION if rag_status == "pending" else None

    write_file_meta(file_id, {
        "classification": classification,
        "filename": file.filename,
        "type": file_type,
        "rag_status": rag_status,
        "rag_collection": rag_collection,
        "rag_error": None,
    })

    if file_type == "pdf":
        try:
            coords = extract_pdf_coordinates(str(dest))
            coords_path = UPLOAD_DIR / f"{file_id}_coords.json"
            coords_path.write_text(json.dumps(coords))
            logger.info("Coordinates stored: %s", file_id)
        except Exception as exc:
            logger.error("Coordinate extraction failed for %s: %s", file_id, exc)

    if rag_status == "pending":
        background_tasks.add_task(embed_project_file_task, file_id, file.filename, str(dest))

    return {
        "file_id": file_id,
        "filename": file.filename,
        "type": file_type,
        "classification": classification,
        "rag_status": rag_status,
        "rag_collection": rag_collection,
        "rag_error": None,
    }


@app.get("/files", response_model=list[FileListItem])
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
    logger.info("Deleted: %s", file_id)
    return {"deleted": True}


@app.get("/files/{file_id}/content")
async def get_file_content(file_id: str):
    path = UPLOAD_DIR / file_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    ext = path.suffix.lower()
    file_type = _ext_to_type(ext)
    try:
        content = read_file(str(path), file_type)
    except Exception:
        content = "(could not read file)"
    if len(content) > 8000:
        content = (
            content[:8000]
            + "\n\n[Document truncated to 8000 characters. "
            + "Full document available via search_documents tool.]"
        )
    return {"file_id": file_id, "content": content}


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
            coords = extract_pdf_coordinates(str(f))
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
                    COMPLIANCE_SYSTEM_PROMPT
                    if compliance_mode
                    else CONVERSATIONAL_SYSTEM_PROMPT
                )
                max_tokens = 4096 if compliance_mode else 1024

                messages = [{"role": m.role, "content": m.content} for m in req.history]
                messages.append({"role": "user", "content": user_message})

                await app.state.mcp.ensure_connected()
                all_tools = app.state.mcp.get_tools()
                compliance_tool_names = {
                    "search_documents",
                    "retrieve_code_clauses",
                    "extract_design_values",
                    "compare_value_to_clause",
                    "write_audit_report",
                }
                conversational_tool_names = {
                    "search_documents",
                    "retrieve_code_clauses",
                }
                runtime_tool_names = (
                    compliance_tool_names
                    if compliance_mode
                    else conversational_tool_names
                )
                tools = [
                    tool
                    for tool in all_tools
                    if tool.get("name") in runtime_tool_names
                ]
                kwargs = dict(
                    model=ANTHROPIC_MODEL,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=messages,
                )
                if tools:
                    kwargs["tools"] = tools

                # Agentic loop: keep going until Claude stops calling tools
                while True:
                    assistant_content = []
                    tool_use_blocks = []
                    current_tool: dict | None = None

                    # Streaming with exponential backoff retry on rate limit
                    stream_ctx = None
                    for attempt in range(3):
                        try:
                            stream_ctx = anthropic_client.messages.stream(**kwargs)
                            break
                        except Exception as e:
                            err_str = str(e).lower()
                            if ("rate_limit" in err_str or "429" in err_str) and attempt < 2:
                                wait = 2 ** attempt
                                logger.warning("Rate limit hit, retrying in %ds (attempt %d)", wait, attempt + 1)
                                await asyncio.sleep(wait)
                                continue
                            raise

                    if stream_ctx is None:
                        raise Exception("Rate limit exceeded after retries. Please wait a moment and try again.")

                    with stream_ctx as stream:
                        for event in stream:
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
                                    yield f'data: {json.dumps({"type": "token", "content": text})}\n\n'
                                    for blk in reversed(assistant_content):
                                        if blk.get("type") == "text":
                                            blk["text"] += text
                                            break
                                elif delta.type == "input_json_delta" and current_tool is not None:
                                    current_tool["input_raw"] += delta.partial_json

                            elif etype == "content_block_stop":
                                if current_tool is not None:
                                    try:
                                        current_tool["input"] = json.loads(current_tool["input_raw"] or "{}")
                                    except json.JSONDecodeError:
                                        current_tool["input"] = {}
                                    del current_tool["input_raw"]
                                    tool_use_blocks.append(current_tool)
                                    current_tool = None

                        final_message = stream.get_final_message()

                    if final_message.stop_reason != "tool_use" or not tool_use_blocks:
                        break

                    # Build assistant content for API (strip internal key)
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

                    # Execute each tool via MCP and collect results
                    tool_results = []
                    for tb in tool_use_blocks:
                        logger.info("Calling MCP tool: %s %s", tb["name"], tb.get("input", {}))
                        try:
                            mcp_result = await app.state.mcp._session.call_tool(
                                tb["name"], tb.get("input", {})
                            )
                            result_text = (
                                mcp_result.content[0].text
                                if mcp_result.content
                                else "Tool returned no content"
                            )
                        except Exception as tool_exc:
                            logger.error("MCP tool error (%s): %s", tb["name"], tool_exc)
                            result_text = json.dumps({
                                "error": str(tool_exc),
                                "retryable": True,
                            })

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb["id"],
                            "content": result_text,
                        })

                    messages.append({"role": "assistant", "content": api_assistant_content})
                    messages.append({"role": "user", "content": tool_results})
                    kwargs["messages"] = messages

                table = extract_table(full_response) if compliance_mode else None
                if table is not None:
                    yield f'data: {json.dumps({"type": "table", "data": table})}\n\n'

            except Exception as e:
                logger.exception("Chat stream error")
                err_msg = str(e)
                if "rate limit" in err_msg.lower() or "429" in err_msg:
                    err_msg = "Rate limit reached. Please wait a moment and try again."
                yield f'data: {json.dumps({"type": "error", "message": err_msg})}\n\n'
            finally:
                _in_flight_chats = max(0, _in_flight_chats - 1)
                yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
