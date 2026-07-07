"""COMPLY MCP server — exactly THREE tools (spec Part 2).

Only jobs that genuinely require the AI's language ability are tools:
  extract_element   turn messy calc prose into strict, schema-enforced JSON
  write_overview    narrate FINISHED deterministic findings in house style
  search_documents  retrieve Eurocode clause prose for quick answers

Everything else is deterministic Python in the repo-root engine/ and the
backend pipeline. The AI never runs a formula and never decides a verdict.

Token discipline: tools return compact structured JSON, never raw chunk
prose; the two LLM calls here are independent small calls that never
inflate the orchestrator's context.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv
from google.cloud import firestore
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from google.oauth2 import service_account
from mcp.server.fastmcp import FastMCP

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))          # services.*
sys.path.insert(0, str(BACKEND_DIR.parent))   # engine/, tables/ if ever needed

from services.indexer import read_pages  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("comply.mcp")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
FAST_MODEL = os.getenv("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5-20251001")

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

mcp = FastMCP("comply-mcp")

_db: firestore.Client | None = None


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(credentials_path)
        else:
            credentials = service_account.Credentials.from_service_account_file(
                BACKEND_DIR / "firebase-key.json"
            )
        _db = firestore.Client(
            project=os.getenv("FIREBASE_PROJECT_ID"),
            credentials=credentials,
        )
    return _db


CHUNK_FIELDS = ["text", "source", "source_type", "page", "clause_number",
                "chunk_index", "file_id", "filename"]


# ---------------------------------------------------------------------------
# Shared plumbing
# ---------------------------------------------------------------------------

def _anthropic_tool_call(model: str, system: str, prompt: str, tool: dict,
                         max_tokens: int) -> dict:
    """Schema-enforced call: the model MUST answer via the forced tool.
    Backoff on rate limits / overload; one retry loop covers schema misses."""
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            response = anthropic_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
            )
            for block in response.content:
                if block.type == "tool_use":
                    return block.input
            raise ValueError("model returned no tool_use block")
        except (anthropic.RateLimitError, anthropic.APIStatusError,
                anthropic.APIConnectionError) as exc:
            status = getattr(exc, "status_code", None)
            retryable = isinstance(
                exc, (anthropic.RateLimitError, anthropic.APIConnectionError)
            ) or status in (429, 500, 503, 529)
            if not retryable or attempt == 3:
                raise
            last_exc = exc
            time.sleep(2 ** attempt)
        except ValueError as exc:
            if attempt == 3:
                raise
            last_exc = exc
    raise last_exc or RuntimeError("Anthropic call failed")


def embed_query(text: str) -> list[float]:
    api_key = os.getenv("GOOGLE_API_KEY")
    last: Exception | None = None
    for attempt in range(4):
        try:
            response = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                "gemini-embedding-001:embedContent",
                headers={"x-goog-api-key": api_key},
                json={
                    "model": "models/gemini-embedding-001",
                    "content": {"parts": [{"text": text}]},
                    "taskType": "RETRIEVAL_QUERY",
                    "outputDimensionality": 1536,
                },
                timeout=30,
            )
            if response.status_code in (429, 500, 503):
                raise RuntimeError(f"embedding HTTP {response.status_code}")
            response.raise_for_status()
            return response.json()["embedding"]["values"]
        except Exception as exc:
            last = exc
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise last  # pragma: no cover


# ---------------------------------------------------------------------------
# Tool 1: extract_element — the single hard AI job
# ---------------------------------------------------------------------------

_EXTRACT_TOOL = {
    "name": "emit_element_values",
    "description": "Emit the extracted design values as strict JSON.",
    "input_schema": {
        "type": "object",
        "properties": {
            "designation": {
                "type": ["string", "null"],
                "description": "Section designation, e.g. 'UC 254x254x132'",
            },
            "values": {
                "type": "object",
                "description": "One entry per extracted value, keyed by parameter name.",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "value": {"type": ["number", "string"]},
                        "unit": {"type": "string"},
                        "page": {"type": ["integer", "null"]},
                        "quote": {"type": "string"},
                        "confidence": {"type": "number"},
                        "flag": {"type": ["string", "null"]},
                        "note": {"type": ["string", "null"]},
                    },
                    "required": ["value", "unit", "page", "quote", "confidence"],
                },
            },
            "not_found": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["values", "not_found"],
    },
}

_EXTRACT_SYSTEM = """You extract structured values from engineering calculation \
prose. You NEVER infer, calculate, or invent a value: if a required name is not \
explicitly stated in the pages, it goes in not_found. Every value carries its \
verbatim source quote and page number. Flag a value ASSUMED when the document \
states it without verification (e.g. a steel grade stated without confirming the \
thickness band, an effective length taken without justification) and say why in \
note. Where the document states the RESULT of a check it performed (e.g. a \
buckling resistance or design moment it computed), report it under the requested \
<check>_result name. Where the document applies a load factor to variable/imposed \
loads, report that factor as gamma_Q_used. Normalise units to kN, kNm, kN/m, m, \
mm, N/mm2. Numbers must be plain numbers (no thousands separators)."""


@mcp.tool()
def extract_element(element_type: str, pdf_path: str, pages: list[int],
                    required_inputs: list[str],
                    input_descriptions: dict | None = None,
                    designation: str | None = None) -> dict:
    """Extract all design values for ONE element from its own PDF pages.
    Returns strict JSON: {designation, values{name:{value,unit,page,quote,
    confidence,flag,note}}, not_found[]}. Absence is data — not_found is
    mandatory and explicit."""
    text = read_pages(pdf_path, pages)
    if not text.strip():
        return {"element": element_type, "designation": designation,
                "values": {}, "not_found": sorted(required_inputs),
                "error": "no extractable text on the element pages"}

    if input_descriptions:
        params = "\n".join(
            f"- {name}: {input_descriptions.get(name, '')}"
            for name in required_inputs
        )
    else:
        params = json.dumps(required_inputs)
    prompt = (
        f"Element type: {element_type}\n"
        f"Known designation (verify or correct from the text): {designation}\n"
        f"Required parameters — report each either in values or in not_found. "
        f"Match the SEMANTICS exactly; if the document states a different "
        f"quantity (e.g. a required area rather than a resistance), that "
        f"parameter is not_found:\n{params}\n\n"
        f"Pages provided: {pages}\n"
        f"--- DOCUMENT TEXT ---\n{text}"
    )
    result = _anthropic_tool_call(
        FAST_MODEL, _EXTRACT_SYSTEM, prompt, _EXTRACT_TOOL, max_tokens=3000
    )
    result.setdefault("designation", designation)
    result.setdefault("values", {})
    reported = set(result["values"].keys())
    stated_missing = set(result.get("not_found") or [])
    result["not_found"] = sorted(
        (set(required_inputs) - reported) | (stated_missing - reported)
    )
    result["element"] = element_type
    logger.info("extract_element(%s): %d values, %d missing",
                element_type, len(result["values"]), len(result["not_found"]))
    return result


# ---------------------------------------------------------------------------
# Tool 2: write_overview — language only; cannot alter any verdict
# ---------------------------------------------------------------------------

_OVERVIEW_TOOL = {
    "name": "emit_overview",
    "description": "Emit the overview paragraph and recommended actions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "overview": {"type": "string"},
            "recommended_actions": {
                "type": "array", "items": {"type": "string"},
                "minItems": 2, "maxItems": 4,
            },
        },
        "required": ["overview", "recommended_actions"],
    },
}

_OVERVIEW_SYSTEM = """You are the report writer for COMPLY, an engineering \
compliance auditor. You NARRATE finished audit findings. You must not change, \
recompute, round differently, or re-judge any number, ratio, status, or verdict \
— the findings are locked by a deterministic engine.

OVERVIEW — one paragraph, sentences in this exact order:
S1 What was checked: document, element, codes. One sentence.
S2 How many checks ran: total plus breakdown by status (counts as WORDS: \
"three failures, two errors, one missing check").
S3 The critical issue: what fails and why, in plain terms. One or two sentences.
S4 What is correct, if anything. One sentence.
S5 Secondary issues (errors, missing, assumed) named briefly.
S6-S7 Suggestions, SOFT tone: "it is suggested ...", two long comma-separated \
sentences.
S8 Close with exactly: "Addressing these points together would put the design \
in a position to pass a full compliance review."

STYLE (absolute): Full sentences, full words; no bullet points in the overview; \
small words over big words; NO em dashes anywhere; no calculations mid-sentence \
(numbers appear only as values like NEd = 6,896 kN); numbers as digits, counts \
as words; active voice; code references in FULL ("Eurocode 3, Section 6.3.1", \
never "EC3 sec 6.3.1"); keep variable letters (NEd, chi, Nb,Rd). Bold with \
**double asterisks**: the document name, element name, code references, key \
values, and each status-count phrase (e.g. **three failures**, **two errors**, \
**one missing check**, **one assumed value**, **one pass**).

RECOMMENDED ACTIONS — 2 to 4 items. Each: **bold action verb + subject** then \
" — " and the specific values, ending with the target section or value. Base \
every number strictly on the findings input."""


@mcp.tool()
def write_overview(element: str, designation: str | None, document: str,
                   findings: list[dict], summary: dict) -> dict:
    """Write the overview paragraph + recommended actions from FINISHED
    deterministic findings. Narration only — cannot alter any verdict."""
    digest = [
        {
            "status": f.get("status"),
            "name": f.get("name"),
            "clause": f.get("clause"),
            "issue": f.get("issue"),
            "metrics": f.get("metrics") or {},
            "element": f.get("element"),
        }
        for f in findings
    ]
    prompt = (
        f"Document: {document}\nElement: {element}"
        f"{f' ({designation})' if designation else ''}\n"
        f"Status counts: {json.dumps(summary)}\n\n"
        f"Findings (locked, deterministic):\n{json.dumps(digest, default=str)}"
    )
    result = _anthropic_tool_call(
        ANTHROPIC_MODEL, _OVERVIEW_SYSTEM, prompt, _OVERVIEW_TOOL,
        max_tokens=1200,
    )
    logger.info("write_overview: %d chars, %d actions",
                len(result.get("overview", "")),
                len(result.get("recommended_actions", [])))
    return result


# ---------------------------------------------------------------------------
# Tool 3: search_documents — clause prose retrieval for quick_answer
# ---------------------------------------------------------------------------

@mcp.tool()
def search_documents(query: str, top_k: int = 3) -> dict:
    """Retrieve Eurocode clause prose from the embedded standards corpus
    (Firestore code_chunks). Excerpts are capped at 600 chars; never returns
    whole documents."""
    top_k = max(1, min(int(top_k), 8))
    vector = embed_query(query)
    snapshot = (
        get_db().collection("code_chunks")
        .select(CHUNK_FIELDS)
        .find_nearest(
            vector_field="embedding",
            query_vector=Vector(vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=top_k,
        )
        .get()
    )
    results = []
    for doc in snapshot:
        row = doc.to_dict()
        row.pop("embedding", None)
        results.append({
            "clause": row.get("clause_number"),
            "text": (row.get("text") or "")[:600],
            "page": row.get("page"),
            "source": row.get("source") or row.get("filename"),
            "chunk_id": doc.id,
        })
    return {"query": query, "results": results}


if __name__ == "__main__":
    mcp.run("stdio")
