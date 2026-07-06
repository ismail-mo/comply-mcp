import json
import math
import os
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
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

load_dotenv(BACKEND_DIR / ".env")
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

mcp = FastMCP("vc-compliance-mcp")
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

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


def embed_query(text: str) -> list[float]:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")

    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-embedding-001:embedContent?key={api_key}",
        json={
            "model": "models/gemini-embedding-001",
            "content": {"parts": [{"text": text}]},
            "taskType": "RETRIEVAL_QUERY",
            "outputDimensionality": 1536,
        },
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Embed API {response.status_code}: {response.text}")
    return response.json()["embedding"]["values"]


def vector_search(
    collection_name: str,
    query_vector: list[float],
    top_k: int = 5,
    file_id: str | None = None,
) -> list[dict]:
    limit = max(top_k * 8, top_k) if file_id else top_k
    snapshot = (
        get_db()
        .collection(collection_name)
        .find_nearest(
            vector_field="embedding",
            query_vector=Vector(query_vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit,
        )
        .get()
    )
    results = [{"id": doc.id, **doc.to_dict()} for doc in snapshot]
    if file_id:
        results = [row for row in results if row.get("file_id") == file_id]
    return results[:top_k]


def parse_json_object(raw_text: str, fallback: dict) -> dict:
    try:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1 and end >= start:
            return json.loads(raw_text[start : end + 1])
        return json.loads(raw_text)
    except Exception:
        return fallback


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
    """Free-form semantic search across project_chunks, design_chunks, or code_chunks."""
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
                "text": chunk.get("text"),
            }
            for chunk in all_results
        ],
    }


@mcp.tool()
def retrieve_code_clauses(
    parameter: str,
    element_type: str | None = None,
    code: str | None = None,
) -> dict:
    """Retrieve relevant Eurocode clauses for an engineering parameter."""
    query = f"{parameter} {element_type or ''} requirement minimum maximum limit".strip()
    query_embed = embed_query(query)
    chunks = vector_search("code_chunks", query_embed, 8)

    if code:
        code_lower = code.lower()
        chunks = [
            chunk
            for chunk in chunks
            if code_lower in str(chunk.get("source", "")).lower()
        ]

    return {
        "parameter": parameter,
        "clauses": [
            {
                "clause_text": chunk.get("text"),
                "clause_number": chunk.get("clause_number") or "see source",
                "code": chunk.get("source"),
                "page": chunk.get("page"),
            }
            for chunk in chunks
        ],
    }


@mcp.tool()
def extract_design_values(
    document_text: str | None = None,
    file_id: str | None = None,
    element_type: str | None = None,
    parameter: str | None = None,
) -> dict:
    """Extract structured numeric design claims from project document text."""
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
        chunk_text = document_text.strip()
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
          "source_quote": "<exact phrase from report, max 12 words>"
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

    response = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        system="You extract structured JSON from engineering documents. Return only valid JSON.",
        messages=[{"role": "user", "content": stage_one_prompt}],
    )
    extracted = parse_json_object(response.content[0].text.strip(), {"elements": []})

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
    """Compare one design value against one Eurocode clause."""
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
{code_clause.get('clause_text')}
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

    response = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        system="You are a structural engineer performing Eurocode compliance checks. Return only valid JSON.",
        messages=[{"role": "user", "content": verdict_prompt}],
    )
    verdict = parse_json_object(
        response.content[0].text.strip(),
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

    raw_verdict = str(verdict.get("verdict", "")).upper()
    if raw_verdict.startswith("PASS"):
        verdict["verdict"] = "PASS"
    elif raw_verdict.startswith("FAIL"):
        verdict["verdict"] = "FAIL"
    else:
        verdict["verdict"] = "WARN"

    return {"design_claim": design_claim, "code_clause": code_clause, **verdict}


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

    counts = {"PASS": 0, "FAIL": 0, "WARN": 0}
    for finding in findings:
        counts[normalize_verdict(finding.get("verdict"))] += 1

    compliance_rate = (counts["PASS"] / len(findings) * 100) if findings else 0
    utilizations = [
        finding.get("utilization_pct")
        for finding in findings
        if isinstance(finding.get("utilization_pct"), (int, float))
    ]
    max_util = max(utilizations) if utilizations else None
    avg_util = sum(utilizations) / len(utilizations) if utilizations else None
    controlling = (
        next((f for f in findings if f.get("utilization_pct") == max_util), None)
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
            if finding.get("utilization_pct") is not None:
                lines.append(f"    Utilization:   {finding.get('utilization_pct'):.1f}%")
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


@mcp.tool()
def compliance_chip_handler() -> dict:
    """Return the hidden pre-prompt contract for compliance quick chips."""
    chips = [
        {
            "label": "Check EC1",
            "hidden_prompt": (
                "[COMPLIANCE_AUDIT] You are checking this project document for "
                "Eurocode 1 compliance. Run a full compliance audit following "
                "the compliance_audit skill exactly:\n"
                "1. Call extract_design_values\n"
                "2. Call retrieve_code_clauses for each value against EC1\n"
                "3. Call compare_value_to_clause for each comparison\n"
                "4. Return Summary + Table in exact required format"
            ),
        },
        {
            "label": "Check EC3",
            "hidden_prompt": (
                "[COMPLIANCE_AUDIT] You are checking this project document for "
                "Eurocode 3 compliance. Run a full compliance audit following "
                "the compliance_audit skill exactly:\n"
                "1. Call extract_design_values\n"
                "2. Call retrieve_code_clauses for each value against EC3\n"
                "3. Call compare_value_to_clause for each comparison\n"
                "4. Return Summary + Table in exact required format"
            ),
        },
        {
            "label": "Client Reqs",
            "hidden_prompt": (
                "[COMPLIANCE_AUDIT] You are checking this project document "
                "against client requirements. Run a full compliance audit "
                "following the compliance_audit skill exactly:\n"
                "1. Call extract_design_values\n"
                "2. Call retrieve_code_clauses against client requirements\n"
                "3. Call compare_value_to_clause for each comparison\n"
                "4. Return Summary + Table in exact required format"
            ),
        },
        {
            "label": "Summarise Risks",
            "hidden_prompt": (
                "[COMPLIANCE_AUDIT] Identify all engineering risks across "
                "uploaded project documents. Rank by severity. Return Summary "
                "+ Table in exact required format with FAIL for critical risks, "
                "WARN for moderate, PASS for managed."
            ),
        },
        {
            "label": "What's Missing?",
            "hidden_prompt": (
                "[COMPLIANCE_AUDIT] Identify what is absent from the uploaded "
                "project documents that would be required for a complete EC1, "
                "EC3, or client requirements submission. Return Summary + Table "
                "in exact required format."
            ),
        },
    ]

    return {
        "name": "compliance_chip_handler",
        "file": "frontend/components/ChatSidebar.tsx",
        "description": (
            "Compliance quick chips send hidden audit prompts directly to the "
            "backend while showing only the chip label in chat."
        ),
        "current_behaviour": (
            "Legacy behavior pre-populated the textarea with the full prompt and "
            "made that prompt visible as the user message."
        ),
        "required_behaviour": {
            "on_click": "Send immediately without pre-populating the textarea.",
            "visible_user_message": "Show only the chip label.",
            "backend_message": (
                "Send the full hidden_prompt prefixed with [COMPLIANCE_AUDIT]."
            ),
        },
        "chips": chips,
        "implementation_steps": [
            "Call onSend(chip.hidden_prompt, chip.label) immediately on chip click.",
            "In useChat.ts, detect or accept the visible label separately.",
            "Store only chip.label in the user chat message.",
            "Send chip.hidden_prompt unchanged to the backend.",
            "Backend receives the [COMPLIANCE_AUDIT] prefix and routes to compliance mode.",
        ],
        "example": {
            "chat_bubble": "Check EC3",
            "backend_receives": (
                "[COMPLIANCE_AUDIT] You are checking this project document..."
            ),
        },
    }


@mcp.tool()
def response_mode_detector() -> dict:
    """Return the backend response mode routing contract."""
    return {
        "name": "response_mode_detector",
        "file": "backend/main.py",
        "description": (
            "Detect whether an incoming chat message is a compliance audit or "
            "a conversational query, then route it to the correct response format."
        ),
        "prefix": "[COMPLIANCE_AUDIT]",
        "helpers": {
            "is_compliance_audit": (
                "return message.strip().startswith('[COMPLIANCE_AUDIT]')"
            ),
            "clean_message": (
                "return message.replace('[COMPLIANCE_AUDIT]', '', 1).strip()"
            ),
        },
        "routing": {
            "compliance_audit": {
                "condition": "Message starts with [COMPLIANCE_AUDIT].",
                "system_prompt": "COMPLIANCE_SYSTEM_PROMPT",
                "response_format": "Summary + Table with <table></table> JSON payload.",
                "tools": "Pass MCP tools.",
                "max_tokens": 4096,
                "prefix_handling": (
                    "Clean [COMPLIANCE_AUDIT] before sending the user message to Claude."
                ),
            },
            "conversational_query": {
                "condition": "Message does not start with [COMPLIANCE_AUDIT].",
                "system_prompt": "CONVERSATIONAL_SYSTEM_PROMPT",
                "response_format": "Plain conversational text only.",
                "tools": "Pass MCP tools; Claude may use them only when useful.",
                "max_tokens": 1024,
            },
        },
        "conversational_system_prompt": (
            "You are COMPLY, an AI engineering compliance assistant.\n"
            "Answer the engineer's question directly and concisely.\n"
            "Use plain text only. No tables. No JSON. No citation markers.\n"
            "Reference documents and findings naturally in prose.\n"
            "Be precise and technical. Use engineering terminology."
        ),
        "compliance_system_prompt": (
            "Use the existing six-step compliance workflow prompt. It must "
            "produce PART 1 SUMMARY and PART 2 TABLE for compliance audits."
        ),
        "implementation_steps": [
            "Detect compliance mode before calling the Claude API.",
            "Clean the hidden prefix before sending the user message to Claude.",
            "Use COMPLIANCE_SYSTEM_PROMPT and 4096 tokens for compliance audits.",
            "Use CONVERSATIONAL_SYSTEM_PROMPT and 1024 tokens for normal queries.",
            "Only parse and emit table SSE events for compliance mode.",
        ],
    }


@mcp.tool()
def citation_badge_renderer() -> dict:
    """Return the frontend citation badge rendering contract."""
    return {
        "name": "citation_badge_renderer",
        "file": "frontend/components/ChatSidebar.tsx",
        "description": (
            "Render [n] markers in compliance summaries and PROJECT/STANDARD "
            "table citations as clickable navigation badges. Each badge fires "
            "onCitationClick with an ActiveCitation object."
        ),
        "project_badge": {
            "visual": {
                "display": "inline-flex",
                "size": "w-4 h-4",
                "border_radius": "rounded-full",
                "background": "#2563eb",
                "hover_background": "#1d4ed8",
                "text": "white, 9px, bold",
                "cursor": "pointer",
                "title": "View in document",
                "position": "inline, immediately after citation marker or reference text",
            },
            "render_condition": [
                "row.project_file_id is not null",
                "row.source_page is not null",
                "row.highlight_start is not null",
                "row.highlight_end is not null",
            ],
            "active_citation": {
                "type": "project",
                "file_id": "row.project_file_id",
                "page": "row.source_page",
                "highlight_start": "row.highlight_start",
                "highlight_end": "row.highlight_end",
            },
        },
        "standard_badge": {
            "visual": {
                "display": "inline-flex",
                "size": "w-4 h-4",
                "border_radius": "rounded-full",
                "background": "#9333ea",
                "hover_background": "#7e22ce",
                "text": "white, 9px, bold",
                "cursor": "pointer",
                "title": "View in standard",
                "position": "inline, immediately after standard clause text",
            },
            "render_condition": [
                "row.standard_file_id is not null",
                "row.standard_page is not null",
                "row.standard_text is not null",
            ],
            "highlight_derivation": [
                "const words = (row.standard_text ?? '').split(' ').filter(w => w.length > 0)",
                "const highlight_start = words.slice(0, 5).join(' ')",
                "const highlight_end = words.slice(-5).join(' ')",
            ],
            "active_citation": {
                "type": "standard",
                "file_id": "row.standard_file_id",
                "page": "row.standard_page",
                "highlight_start": "first 5 words of row.standard_text",
                "highlight_end": "last 5 words of row.standard_text",
            },
        },
        "summary_badges": {
            "split_regex": r"(\[\d+\])",
            "row_lookup": "For marker [n], use table[n - 1].",
            "project_badge_condition": (
                "If the row exists and has project_file_id, source_page, "
                "highlight_start, and highlight_end, render a PROJECT badge."
            ),
            "fallback": "Render plain [n] text when no complete PROJECT citation exists.",
            "non_marker_text": "Render as plain spans.",
        },
        "implementation_steps": [
            "Strip <table> blocks from assistant display text before rendering summary.",
            "Split summary text on /(\\[\\d+\\])/g.",
            "Map each citation marker to table row n - 1.",
            "Render PROJECT badges for complete project citations.",
            "Render PROJECT badges in table reference cells.",
            "Render STANDARD badges in table clause cells.",
            "Dispatch onCitationClick with the ActiveCitation object on badge click.",
        ],
    }


if __name__ == "__main__":
    mcp.run("stdio")
