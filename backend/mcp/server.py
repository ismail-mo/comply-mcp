"""COMPLY MCP server — RAG + compliance tools over Firestore.

Token discipline (the reason this file looks the way it does):
- Tools NEVER return raw chunk prose to the calling model. Everything is
  compressed to structured JSON (clause / requirement / formula / threshold /
  short verbatim excerpt) before it enters the caller's context window.
- The heavy lifting (extraction, clause compression) happens in SEPARATE small
  Anthropic calls inside the tools — independent API calls that never inflate
  the main chat session (the "batching layer").
- Firestore fetches exclude the 1536-float embedding field via projection.
"""

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
import requests
from dotenv import load_dotenv
from google.cloud import firestore
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from google.oauth2 import service_account
from mcp.server.fastmcp import FastMCP


BACKEND_DIR = Path(__file__).resolve().parents[1]
AUDITS_DIR = BACKEND_DIR / "audits"

load_dotenv(BACKEND_DIR / ".env")
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

# Read AFTER load_dotenv so backend/.env values are honoured.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
# Small/fast model for mechanical extraction + compression steps.
FAST_MODEL = os.getenv("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5-20251001")

mcp = FastMCP("vc-compliance-mcp")
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_db: firestore.Client | None = None

# Chunk fields we actually use — embedding is deliberately excluded.
CHUNK_FIELDS = [
    "text", "source", "source_type", "page", "clause_number",
    "chunk_index", "file_id", "filename",
]


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


def _anthropic_call(model: str, system: str, prompt: str, max_tokens: int) -> str:
    """Anthropic call with backoff on rate limits / overload."""
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            response = anthropic_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            status = getattr(exc, "status_code", None)
            retryable = isinstance(exc, (anthropic.RateLimitError, anthropic.APIConnectionError)) or (
                status in (429, 500, 503, 529)
            )
            if not retryable or attempt == 3:
                raise
            last_exc = exc
            time.sleep(2 ** attempt)
    raise last_exc or RuntimeError("Anthropic call failed")


def embed_query(text: str) -> list[float]:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")

    for attempt in range(4):
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
        if response.status_code in (429, 500, 503) and attempt < 3:
            time.sleep(2 ** attempt)
            continue
        if not response.ok:
            raise RuntimeError(f"Embed API {response.status_code}: {response.text[:200]}")
        return response.json()["embedding"]["values"]
    raise RuntimeError("Embed API failed after retries")


def vector_search(
    collection_name: str,
    query_vector: list[float],
    top_k: int = 5,
    file_id: str | None = None,
) -> list[dict]:
    top_k = max(1, min(top_k, 20))
    limit = top_k * 8 if file_id else top_k
    base = get_db().collection(collection_name)
    try:
        query = base.select(CHUNK_FIELDS)  # skip the 1536-float embedding
    except Exception:
        query = base
    snapshot = query.find_nearest(
        vector_field="embedding",
        query_vector=Vector(query_vector),
        distance_measure=DistanceMeasure.COSINE,
        limit=limit,
    ).get()
    results = []
    for doc in snapshot:
        row = {"id": doc.id, **doc.to_dict()}
        row.pop("embedding", None)  # belt-and-braces if select() was skipped
        results.append(row)
    if file_id:
        results = [row for row in results if row.get("file_id") == file_id]
    return results[:top_k]


def parse_json_value(raw_text: str, fallback):
    """Extract the first JSON object or array from LLM output."""
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = raw_text.find(open_ch)
        end = raw_text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(raw_text[start : end + 1])
            except Exception:
                continue
    try:
        return json.loads(raw_text)
    except Exception:
        return fallback


def _truncate(text: str, limit: int) -> str:
    if not text or len(text) <= limit:
        return text or ""
    cut = text[:limit]
    return cut[: cut.rfind(" ")] + " …"


def collections_for_filter(source_filter: str | None) -> list[str]:
    filter_value = (source_filter or "all").lower()
    if filter_value in {"project", "projects", "uploaded"}:
        return ["project_chunks"]
    if filter_value in {"design", "client", "requirements"}:
        return ["design_chunks"]
    if filter_value in {"eurocode", "code", "standard", "standards"}:
        return ["code_chunks"]
    return ["project_chunks", "design_chunks", "code_chunks"]


@mcp.tool()
def search_documents(
    query: str,
    source_filter: str | None = None,
    top_k: int = 5,
    file_id: str | None = None,
) -> dict:
    """Semantic search across project_chunks, design_chunks, or code_chunks.
    Returns compact excerpts (≤600 chars each), never full chunks."""
    top_k = max(1, min(int(top_k or 5), 8))
    query_embed = embed_query(query)
    collections = collections_for_filter(source_filter)

    all_results: list[dict] = []
    for collection in collections:
        chunks = vector_search(
            collection,
            query_embed,
            top_k,
            file_id=file_id if collection == "project_chunks" else None,
        )
        all_results.extend({**chunk, "collection": collection} for chunk in chunks)

    return {
        "query": query,
        "file_id": file_id,
        "results": [
            {
                "collection": chunk.get("collection"),
                "file_id": chunk.get("file_id"),
                "filename": chunk.get("filename"),
                "source": chunk.get("source"),
                "page": chunk.get("page"),
                "clause_number": chunk.get("clause_number"),
                "excerpt": _truncate(chunk.get("text") or "", 600),
            }
            for chunk in all_results
        ],
    }


CLAUSE_COMPRESSION_SYSTEM = (
    "You compress engineering standard text into structured JSON facts. "
    "Return only valid JSON. Never invent values that are not in the text."
)


@mcp.tool()
def retrieve_code_clauses(
    parameter: str,
    element_type: str | None = None,
    code: str | None = None,
) -> dict:
    """Retrieve code/standard clauses for an engineering parameter as
    COMPRESSED structured facts: {clause_number, code, page, requirement,
    formula, threshold, excerpt}. 'code' may be e.g. 'EC1', 'EC3', or
    'client requirements'."""
    query = f"{parameter} {element_type or ''} requirement minimum maximum limit".strip()
    query_embed = embed_query(query)

    code_lower = (code or "").lower()
    if any(k in code_lower for k in ("client", "requirement", "brief", "employer")):
        collections = ["design_chunks", "code_chunks"]
    else:
        collections = ["code_chunks"]

    chunks: list[dict] = []
    for collection in collections:
        chunks.extend(vector_search(collection, query_embed, 10))

    if code:
        filtered = [
            chunk for chunk in chunks
            if code_lower.replace(" ", "") in str(chunk.get("source", "")).lower().replace(" ", "")
            or code_lower in str(chunk.get("source", "")).lower()
        ]
        if filtered:  # fall back to unfiltered rather than returning nothing
            chunks = filtered
    chunks = chunks[:6]

    if not chunks:
        return {"parameter": parameter, "clauses": [], "note": "no matching clauses found"}

    numbered = "\n\n".join(
        f"--- chunk {i} (source={c.get('source')}, page={c.get('page')}, "
        f"clause≈{c.get('clause_number') or '?'}) ---\n{c.get('text')}"
        for i, c in enumerate(chunks)
    )
    compression_prompt = f"""Extract every requirement relevant to the parameter "{parameter}"
(element type: {element_type or 'any'}) from the standard-text chunks below.
The text may contain OCR noise — normalise obvious character errors when
writing 'requirement', but NEVER alter the verbatim 'excerpt'.

Return a JSON array (max 5 items), each item:
{{
  "chunk": <chunk index the item came from>,
  "clause_number": "<clause number as printed, e.g. '6.3.2', or null>",
  "requirement": "<the rule in plain engineering language, max 30 words>",
  "formula": "<governing formula exactly as written, or null>",
  "threshold": "<the limit/criterion, e.g. 'MEd/Mb,Rd <= 1.0', or null>",
  "excerpt": "<VERBATIM contiguous substring copied character-for-character from the chunk, 8-20 words, containing the core requirement>"
}}

Only include items genuinely relevant to "{parameter}". Return ONLY the JSON array."""

    compressed: list[dict] | None = None
    try:
        raw = _anthropic_call(FAST_MODEL, CLAUSE_COMPRESSION_SYSTEM, compression_prompt, 1200)
        parsed = parse_json_value(raw, None)
        if isinstance(parsed, list):
            compressed = parsed
    except Exception:
        compressed = None

    clauses = []
    if compressed:
        for item in compressed[:5]:
            idx = item.get("chunk")
            src = chunks[idx] if isinstance(idx, int) and 0 <= idx < len(chunks) else {}
            clauses.append({
                "clause_number": item.get("clause_number") or src.get("clause_number"),
                "code": src.get("source"),
                "page": src.get("page"),
                "requirement": _truncate(str(item.get("requirement") or ""), 240),
                "formula": item.get("formula"),
                "threshold": item.get("threshold"),
                "excerpt": _truncate(str(item.get("excerpt") or ""), 200),
            })
    else:
        # Compression failed — degrade to truncated chunks, never fail the tool.
        clauses = [
            {
                "clause_number": c.get("clause_number"),
                "code": c.get("source"),
                "page": c.get("page"),
                "requirement": None,
                "formula": None,
                "threshold": None,
                "excerpt": _truncate(c.get("text") or "", 350),
            }
            for c in chunks[:5]
        ]

    return {"parameter": parameter, "clauses": clauses}


@mcp.tool()
def extract_design_values(
    document_text: str | None = None,
    file_id: str | None = None,
    element_type: str | None = None,
    parameter: str | None = None,
) -> dict:
    """Extract structured numeric design claims from a PROJECT document
    (by file_id, queries project_chunks). Returns structured claims only."""
    chunk_file_id = file_id
    query = f"{element_type or ''} {parameter or ''} design value calculation span load section".strip()
    if not query:
        query = "design values calculations sizing span load"

    if file_id:
        chunks = vector_search("project_chunks", embed_query(query), 14, file_id=file_id)
        chunk_text = "\n\n".join(
            (
                f"--- chunk {index} "
                f"(file_id={chunk.get('file_id') or file_id}, "
                f"filename={chunk.get('filename') or '?'}, "
                f"p.{chunk.get('page') or '?'}) ---\n{chunk.get('text')}"
            )
            for index, chunk in enumerate(chunks)
        )
    elif document_text and document_text.strip():
        chunk_text = document_text.strip()[:12000]  # hard cap on caller-supplied prose
    else:
        chunks = vector_search("design_chunks", embed_query(query), 10)
        chunk_text = "\n\n".join(
            f"--- chunk {index} (p.{chunk.get('page') or '?'}) ---\n{chunk.get('text')}"
            for index, chunk in enumerate(chunks)
        )

    stage_one_prompt = f"""You are a structural engineer reading a design report.
From the chunks below, extract every piece of structural data you can find.

Return a JSON object with this schema:
{{
  "elements": [
    {{
      "element_id": "<name or description, e.g. 'internal primary beam'>",
      "element_type": "<beam|column|slab|connection|foundation>",
      "page": <page number or null>,
      "raw_inputs": {{
        "span_m": <number or null>,
        "load_uls_kNm": <ULS uniformly distributed load in kN/m, or null>,
        "load_sls_kNm": <SLS/quasi-permanent UDL in kN/m, or null>,
        "load_point_kN": <point load in kN, or null>,
        "section": "<section designation e.g. '610x229x101 UB', or null>",
        "steel_grade": "<e.g. 'S355', or null>",
        "f_y_Nmm2": <yield strength in N/mm2, or null>,
        "W_pl_y_cm3": <plastic section modulus in cm3, or null>,
        "A_v_mm2": <shear area in mm2, or null>,
        "I_y_cm4": <second moment of area in cm4, or null>
      }},
      "stated_results": [
        {{
          "parameter": "<e.g. 'bending moment', 'shear force', 'deflection'>",
          "value": <number>,
          "unit": "<SI unit>",
          "source_quote": "<exact phrase from report, max 12 words>",
          "page": <page number of the chunk this came from, or null>
        }}
      ]
    }}
  ]
}}

Rules:
- Extract every element you can find (beams, columns, slabs, connections).
- raw_inputs: only put values EXPLICITLY stated in the text; null means not found.
- stated_results: results that are explicitly given in the report as a calculated answer.
- If the same element appears in multiple chunks, merge into one entry.
- Return [] for elements if none found.

CHUNKS:
{chunk_text}

Return ONLY the JSON object. No prose."""

    raw = _anthropic_call(
        FAST_MODEL,
        "You extract structured JSON from engineering documents. Return only valid JSON.",
        stage_one_prompt,
        3000,
    )
    extracted = parse_json_value(raw, {"elements": []})
    if not isinstance(extracted, dict):
        extracted = {"elements": []}

    claims: list[dict] = []
    e_steel = 210000

    for element in extracted.get("elements", []):
        base = {
            "element_id": element.get("element_id"),
            "element_type": element.get("element_type"),
            "page": element.get("page"),
            "file_id": chunk_file_id,
        }
        raw_inputs = element.get("raw_inputs") or {}
        stated_results = element.get("stated_results") or []

        for result in stated_results:
            claims.append(
                {
                    **base,
                    "page": result.get("page") or element.get("page"),
                    "parameter": result.get("parameter"),
                    "value": result.get("value"),
                    "unit": result.get("unit"),
                    "source_quote": result.get("source_quote"),
                    "derived": False,
                    "raw_inputs": raw_inputs,
                }
            )

        span = raw_inputs.get("span_m")
        load_uls = raw_inputs.get("load_uls_kNm")
        load_sls = raw_inputs.get("load_sls_kNm")
        has_bending = any("bending" in str(r.get("parameter", "")).lower() for r in stated_results)
        has_shear = any("shear" in str(r.get("parameter", "")).lower() for r in stated_results)
        has_deflection = any("deflect" in str(r.get("parameter", "")).lower() for r in stated_results)

        if span and load_uls and not has_bending:
            claims.append(
                {
                    **base,
                    "parameter": "bending moment",
                    "value": round(load_uls * span * span / 8, 1),
                    "unit": "kNm",
                    "source_quote": f"span {span}m, ULS UDL {load_uls} kN/m",
                    "derived": True,
                    "formula": "M_Ed = wL^2/8",
                    "raw_inputs": raw_inputs,
                }
            )

        if span and load_uls and not has_shear:
            claims.append(
                {
                    **base,
                    "parameter": "shear force",
                    "value": round(load_uls * span / 2, 1),
                    "unit": "kN",
                    "source_quote": f"span {span}m, ULS UDL {load_uls} kN/m",
                    "derived": True,
                    "formula": "V_Ed = wL/2",
                    "raw_inputs": raw_inputs,
                }
            )

        i_y_cm4 = raw_inputs.get("I_y_cm4")
        i_mm4 = i_y_cm4 * 1e4 if i_y_cm4 else None
        if span and load_sls and i_mm4 and not has_deflection:
            span_mm = span * 1000
            delta = (5 * load_sls * math.pow(span_mm, 4)) / (384 * e_steel * i_mm4)
            claims.append(
                {
                    **base,
                    "parameter": "deflection",
                    "value": round(delta, 1),
                    "unit": "mm",
                    "source_quote": f"span {span}m, SLS UDL {load_sls} kN/m",
                    "derived": True,
                    "formula": "delta = 5wL^4/(384EI)",
                    "raw_inputs": raw_inputs,
                }
            )

    filtered = [
        claim
        for claim in claims
        if (not element_type or str(claim.get("element_type", "")).lower() == element_type.lower())
        and (not parameter or parameter.lower() in str(claim.get("parameter", "")).lower())
    ]
    return {"claims": filtered, "total": len(filtered)}


@mcp.tool()
def compare_value_to_clause(design_claim: dict, code_clause: dict) -> dict:
    """Compare one design value against one code clause. Returns a compact
    verdict — inputs are echoed back in slim form only."""
    raw_context = (
        json.dumps(design_claim.get("raw_inputs"), indent=2)
        if design_claim.get("raw_inputs")
        else "(no section properties available)"
    )
    derived_note = (
        f"Design value was calculated using formula: {design_claim.get('formula', 'standard formula')}"
        if design_claim.get("derived")
        else "Design value was explicitly stated in the design report."
    )
    clause_body = code_clause.get("clause_text") or "\n".join(
        f"{k}: {v}"
        for k, v in (
            ("Requirement", code_clause.get("requirement")),
            ("Formula", code_clause.get("formula")),
            ("Threshold", code_clause.get("threshold")),
            ("Excerpt", code_clause.get("excerpt")),
        )
        if v
    ) or "(no clause text supplied)"

    verdict_prompt = f"""You are a structural engineer performing a Eurocode compliance check.

DESIGN DEMAND
Parameter: {design_claim.get('parameter')}
Value: {design_claim.get('value', 'NOT PROVIDED')} {design_claim.get('unit', '')}
Element: {design_claim.get('element_id') or 'unspecified'} ({design_claim.get('element_type') or 'unknown'})
Source: "{design_claim.get('source_quote')}" (p.{design_claim.get('page') or '?'})
{derived_note}

Section / material properties from the design report:
{raw_context}

GOVERNING CODE CLAUSE
{clause_body}
(Reference: {code_clause.get('code') or 'Eurocode'}, clause {code_clause.get('clause_number') or '-'})

Return ONLY this JSON (all fields required):
{{
  "verdict": "PASS" | "FAIL" | "WARN",
  "capacity_value": <number or null>,
  "capacity_unit": "<unit>",
  "capacity_formula": "<formula used>",
  "utilization_pct": <number 0-999 or null>,
  "margin": <capacity_value minus demand_value, signed, or null>,
  "margin_unit": "<same unit as capacity>",
  "calculation_steps": ["<step 1 as string>", "<step 2>"],
  "comparison_op": ">=" | "<=" | "==" | "n/a",
  "explanation": "<one-sentence engineering verdict, max 30 words>"
}}

Critical rules:
- If design value is null/missing, set verdict to WARN, all numbers to null.
- If a capacity formula is in the clause but section data is missing, still compute what you can and WARN the rest.
- NEVER invent a clause threshold. If it is not in the clause text, use WARN."""

    raw = _anthropic_call(
        ANTHROPIC_MODEL,
        "You are a structural engineer performing Eurocode compliance checks. Return only valid JSON.",
        verdict_prompt,
        1500,
    )
    verdict = parse_json_value(
        raw,
        {
            "verdict": "WARN",
            "capacity_value": None,
            "capacity_unit": "",
            "capacity_formula": "Could not determine",
            "utilization_pct": None,
            "margin": None,
            "margin_unit": "",
            "calculation_steps": ["Comparison could not be completed - check inputs"],
            "comparison_op": "n/a",
            "explanation": "Could not parse comparison result",
        },
    )
    if not isinstance(verdict, dict):
        verdict = {"verdict": "WARN", "explanation": "Could not parse comparison result"}

    raw_verdict = str(verdict.get("verdict", "")).upper()
    if raw_verdict.startswith("PASS"):
        verdict["verdict"] = "PASS"
    elif raw_verdict.startswith("FAIL"):
        verdict["verdict"] = "FAIL"
    else:
        verdict["verdict"] = "WARN"

    steps = verdict.get("calculation_steps")
    if isinstance(steps, list):
        verdict["calculation_steps"] = [str(s)[:160] for s in steps[:4]]

    # Slim echoes only — never send the full clause text back into context.
    slim_claim = {
        k: design_claim.get(k)
        for k in ("parameter", "value", "unit", "element_id", "element_type", "page", "source_quote")
    }
    slim_clause = {
        k: code_clause.get(k) for k in ("clause_number", "code", "page", "excerpt")
    }
    return {"design_claim": slim_claim, "code_clause": slim_clause, **verdict}


@mcp.tool()
def write_audit_report(
    findings: list[dict],
    mode: str = "full",
    project_name: str = "audit",
) -> dict:
    """Write a structured compliance audit to a text file in backend/audits."""
    AUDITS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-").replace(".", "-")[:19]
    filename = "single-checks.txt" if mode == "append" else f"{project_name}-audit-{timestamp}.txt"
    filepath = AUDITS_DIR / filename

    def normalize_verdict(value: Any) -> str:
        upper = str(value or "").upper()
        if upper.startswith("PASS"):
            return "PASS"
        if upper.startswith("FAIL"):
            return "FAIL"
        return "WARN"

    def as_number(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).strip().rstrip("%"))
        except (TypeError, ValueError):
            return None

    counts = {"PASS": 0, "FAIL": 0, "WARN": 0}
    for finding in findings:
        counts[normalize_verdict(finding.get("verdict"))] += 1

    compliance_rate = (counts["PASS"] / len(findings) * 100) if findings else 0
    utilizations = [
        u for u in (as_number(f.get("utilization_pct")) for f in findings) if u is not None
    ]
    max_util = max(utilizations) if utilizations else None
    avg_util = sum(utilizations) / len(utilizations) if utilizations else None
    controlling = (
        next((f for f in findings if as_number(f.get("utilization_pct")) == max_util), None)
        if max_util is not None
        else None
    )

    grouped: dict[str, list[dict]] = {}
    for finding in findings:
        key = (finding.get("design_claim") or {}).get("element_type") or "uncategorised"
        grouped.setdefault(key, []).append(finding)

    width = 67
    bar = "=" * width
    dash = "-" * width
    lines = [
        bar,
        "   STRUCTURAL COMPLIANCE AUDIT",
        f"   Generated: {datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')}",
        f"   Project:   {project_name}",
        bar,
        "",
        "SUMMARY",
        f"   Total checks:    {len(findings)}",
        f"   PASS:            {counts['PASS']}",
        f"   FAIL:            {counts['FAIL']}",
        f"   WARN:            {counts['WARN']}",
        f"   Compliance rate: {compliance_rate:.1f}%  ({counts['PASS']}/{len(findings)} checks pass)",
    ]
    if max_util is not None:
        suffix = ""
        if controlling:
            claim = controlling.get("design_claim") or {}
            suffix = f"  ({claim.get('parameter', 'unknown')} - {claim.get('element_id') or claim.get('element_type') or ''})"
        lines.append(f"   Max utilization: {max_util:.1f}%{suffix}")
    if avg_util is not None:
        lines.append(f"   Avg utilization: {avg_util:.1f}%")
    lines.extend(["", dash, ""])

    check_index = 0
    for element_type, items in grouped.items():
        lines.extend([element_type.upper(), ""])
        for finding in items:
            check_index += 1
            verdict = normalize_verdict(finding.get("verdict"))
            claim = finding.get("design_claim") or {}
            clause = finding.get("code_clause") or {}
            lines.extend(
                [
                    f"  CHECK {check_index}: {str(claim.get('parameter') or 'unknown').upper()}",
                    "",
                    f"    Element:       {claim.get('element_id') or claim.get('element_type') or '-'}",
                    f"    Design value:  {claim.get('value', 'NOT AVAILABLE')} {claim.get('unit', '')}",
                    f"    Source:        \"{claim.get('source_quote') or '-'}\" (p.{claim.get('page') or '?'})",
                    f"    Code clause:   {clause.get('code') or 'Eurocode'}, clause {clause.get('clause_number') or '-'}",
                ]
            )
            if finding.get("capacity_formula") and finding.get("capacity_formula") != "Could not determine":
                lines.append(f"    Formula:       {finding.get('capacity_formula')}")
            if finding.get("calculation_steps"):
                lines.append("    Calculation:")
                lines.extend(f"      -> {step}" for step in finding["calculation_steps"])
            if finding.get("capacity_value") is not None:
                lines.append(f"    Capacity:      {finding.get('capacity_value')} {finding.get('capacity_unit') or ''}")
            util = as_number(finding.get("utilization_pct"))
            if util is not None:
                lines.append(f"    Utilization:   {util:.1f}%")
            if finding.get("margin") is not None:
                lines.append(f"    Margin:        {finding.get('margin')} {finding.get('margin_unit') or ''}")
            lines.extend(["", f"    [{verdict}]  {finding.get('explanation') or ''}", ""])

    lines.extend([bar, "   END OF REPORT", bar, ""])
    report = "\n".join(lines)

    if mode == "append":
        with filepath.open("a", encoding="utf-8") as file:
            file.write("\n\n" + report)
    else:
        filepath.write_text(report, encoding="utf-8")

    return {
        "filepath": str(filepath),
        "summary": {
            "total": len(findings),
            "PASS": counts["PASS"],
            "FAIL": counts["FAIL"],
            "WARN": counts["WARN"],
            "compliance_rate": f"{compliance_rate:.1f}%",
            "max_utilization": f"{max_util:.1f}%" if max_util is not None else None,
            "avg_utilization": f"{avg_util:.1f}%" if avg_util is not None else None,
            "controlling_check": (
                f"{(controlling.get('design_claim') or {}).get('parameter')} ({max_util:.1f}%)"
                if controlling and max_util is not None
                else None
            ),
        },
    }


if __name__ == "__main__":
    mcp.run("stdio")
