"""The deterministic audit engine. Pure Python — no network, no LLM, no
Firestore in the compute path. Given extracted values + authoritative section
properties it produces the entire findings array deterministically.

Spec Part 4.5. The AI never sees this module; it narrates its output.
"""

import hashlib
import json

from formulas import FORMULAS
from registries.check_registry import CHECK_REGISTRY
from registries.national_annex import check_national_annex
from engine.classify import classify, classify_recompute
from tables.steel_grade import fy_for

STATUS_ORDER = ["FAIL", "ERROR", "CONFLICT", "MISSING", "ASSUMED", "WARNING", "PASS"]

# formula_cache — keyed PER CHECK on its specific inputs (spec 5.1), so editing
# one value invalidates only the checks that use it.
_FORMULA_CACHE: dict[str, dict] = {}

# Geometry / material names that must come from the authoritative tables,
# never from the design PDF (spec 5.3).
_PROP_KEYS = {"A", "b", "h", "tf", "tw", "r", "d", "iy", "iz", "Iy", "Iz",
              "Wpl_y", "Wel_y", "hw", "section_type", "axis", "h_over_b"}


def _fmt(x, dp=2):
    if x is None:
        return "?"
    if isinstance(x, (int, float)):
        s = f"{x:,.{dp}f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return str(x)


def _prepare_props(section_props: dict | None) -> dict:
    if not section_props:
        return {}
    p = dict(section_props)
    if "h" in p and "tf" in p and "hw" not in p:
        p["hw"] = round(p["h"] - 2 * p["tf"], 1)
    if "h" in p and "b" in p:
        p["h_over_b"] = round(p["h"] / p["b"], 2)
    p.setdefault("section_type", p.get("family"))
    p.setdefault("axis", "minor")  # minor axis governs flexural buckling
    return p


_STRING_INPUTS = {"grade", "section_class", "section_type", "axis"}

# Engine-expected unit per extracted input, with deterministic conversion
# factors from the unit the document happened to state.
_EXPECTED_UNITS: dict[str, tuple[str, dict[str, float]]] = {
    "Le":  ("m",     {"m": 1.0, "mm": 0.001, "cm": 0.01}),
    "L":   ("mm",    {"mm": 1.0, "m": 1000.0, "cm": 10.0}),
    "NEd": ("kN",    {"kn": 1.0, "n": 0.001, "mn": 1000.0}),
    "VEd": ("kN",    {"kn": 1.0, "n": 0.001}),
    "Gk":  ("kN",    {"kn": 1.0, "n": 0.001}),
    "Qk":  ("kN",    {"kn": 1.0, "n": 0.001}),
    "P":   ("kN",    {"kn": 1.0, "n": 0.001}),
    "MEd": ("kNm",   {"knm": 1.0, "kn.m": 1.0, "nmm": 1e-6}),
    "Mcr": ("kNm",   {"knm": 1.0, "kn.m": 1.0, "nmm": 1e-6}),
    "fy":  ("N/mm2", {"n/mm2": 1.0, "mpa": 1.0}),
    "q":   ("kN/m",  {"kn/m": 1.0, "n/mm": 1.0}),
}


def _normalize_unit(name: str, value, unit: str | None):
    """Convert an extracted value into the engine's expected unit. Unknown
    units pass through unchanged (better a flagged discrepancy than a crash)."""
    if not isinstance(value, (int, float)) or name not in _EXPECTED_UNITS:
        return value, unit
    expected, table = _EXPECTED_UNITS[name]
    key = (unit or expected).lower().replace(" ", "").replace("²", "2")
    factor = table.get(key)
    if factor is None:
        return value, unit
    if factor == 1.0:
        return value, expected  # no arithmetic — keeps ints as ints
    return value * factor, expected


def _coerce(name, raw):
    """Extracted values may arrive as strings ('6,896.25'); numeric inputs
    must be numbers before they reach a formula or a comparison."""
    if name in _STRING_INPUTS or isinstance(raw, (int, float)):
        return raw
    try:
        return float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return raw


def _gather(names, props, extracted):
    """Resolve inputs: authoritative section properties first, then the
    AI-extracted values. Returns (inputs, missing, assumed, sources)."""
    values = extracted.get("values") or {}
    inputs, missing, assumed, sources = {}, [], [], {}
    for name in names:
        if name in _PROP_KEYS and name in props:
            inputs[name] = props[name]
            sources[name] = {"kind": "sbb", "detail": props.get("source", "Steel Blue Book")}
            continue
        entry = values.get(name)
        if entry is not None and entry.get("value") is not None:
            value = _coerce(name, entry["value"])
            value, unit = _normalize_unit(name, value, entry.get("unit"))
            inputs[name] = value
            sources[name] = {
                "kind": "doc", "page": entry.get("page"),
                "quote": entry.get("quote"), "unit": unit or entry.get("unit"),
            }
            # Consume the confidence score (spec 14.6): low-confidence
            # extractions are treated as unverified assumptions.
            confidence = entry.get("confidence")
            if entry.get("flag") == "ASSUMED" or (
                    isinstance(confidence, (int, float)) and confidence < 0.6):
                assumed.append(name)
            continue
        if name in _PROP_KEYS and props:
            # property genuinely absent from the table entry
            missing.append(name)
            continue
        missing.append(name)

    # Authoritative fy fallback: when the document never states a numeric fy
    # but the grade is known and tf comes from the Blue Book, EN 10025-2
    # Table 7 determines fy deterministically (spec 5.3: authoritative values).
    if "fy" in missing:
        grade = (values.get("grade") or {}).get("value")
        tf = props.get("tf")
        if grade and tf is not None:
            try:
                fy_val = fy_for(str(grade), float(tf))
            except Exception:
                fy_val = None
            if fy_val is not None:
                inputs["fy"] = fy_val
                missing.remove("fy")
                sources["fy"] = {
                    "kind": "en10025",
                    "detail": f"EN 10025-2 Table 7: {grade}, tf = {tf} mm",
                    "unit": "N/mm2",
                }
    return inputs, missing, assumed, sources


def _cache_key(check_id: str, inputs: dict) -> str:
    payload = json.dumps({"id": check_id, "in": inputs}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _run_formula(check: dict, inputs: dict) -> dict:
    key = _cache_key(check["id"], inputs)
    if key not in _FORMULA_CACHE:
        _FORMULA_CACHE[key] = FORMULAS[check["formula"]](**inputs)
    return _FORMULA_CACHE[key]


def _calc_block(check, inputs, sources, computed, result_line, document):
    lines = ["Input values", "-" * 42]
    for name, val in inputs.items():
        src = sources.get(name, {})
        if src.get("kind") == "sbb":
            origin = f"> Steel Blue Book . {src.get('detail', '')}"
        elif src.get("kind") == "en10025":
            origin = f"> {src.get('detail', 'EN 10025-2')}"
        elif src.get("kind") == "doc":
            page = f" . p.{src['page']}" if src.get("page") else ""
            origin = f"> {document}{page}"
        else:
            origin = ""
        unit = f" {src.get('unit')}" if src.get("unit") else ""
        lines.append(f"{name:<8}= {_fmt(val)}{unit}   {origin}".rstrip())
    lines += ["", f"Formula — {check['clause']}"]
    lines += computed.get("steps", [])
    lines += ["", "Result", result_line]
    return {
        "label": f"{check['name']} — Calculation summary — {len(lines)} lines",
        "lines": lines,
    }


def _reference_for(check, sources, extracted):
    """Pick the most probative report quote for the REFERENCE column."""
    document = extracted.get("document")
    key = check.get("demand_key") or check.get("engineer_key")
    candidates = [key] if key else []
    candidates += [n for n in check["inputs"] if n not in _PROP_KEYS]
    for name in candidates:
        src = sources.get(name)
        if src and src.get("kind") == "doc" and src.get("quote"):
            return {"quote": src["quote"], "clause": check["clause"],
                    "page": src.get("page"), "source": document}
    return {"quote": None, "clause": check["clause"], "page": None,
            "source": document}


def _badge_for_clause(clause: str) -> str:
    c = clause.lower()
    if "1990" in c:
        return "en1990"
    if "10025" in c:
        return "en10025"
    if "eurocode 3" in c or "1993" in c:
        return "ec3"
    return "report"


def _base_finding(check, extracted, sources):
    return {
        "check_id": check["id"],
        "name": check["name"],
        "category_sub": check["category_sub"],
        "clause": check["clause"],
        "badge": _badge_for_clause(check["clause"]),
        "reference": _reference_for(check, sources, extracted),
        "action": check["action_fix"],
        "calc": None,
        "metrics": {},
        "assumed_inputs": [],
    }


def _finding_missing(check, extracted, sources, missing):
    f = _base_finding(check, extracted, sources)
    f["status"] = check["missing_status"]
    needed = ", ".join(missing)
    f["issue"] = (
        f"No {check['name'].lower()} check is presented — required input"
        f"{'s' if len(missing) > 1 else ''} ({needed}) "
        f"not found in the document. {check['clause']} requires this check."
    )
    return f


def _finding_qualitative(check, extracted, sources, inputs):
    f = _base_finding(check, extracted, sources)
    f["status"] = "WARNING"
    claimed = (extracted.get("values") or {}).get("section_class", {})
    claim_txt = (
        f"The document asserts Class {claimed.get('value')} "
        if claimed.get("value") not in (None, "")
        else "The document asserts a section class "
    )
    f["issue"] = (
        claim_txt + "but no c/t ratio is calculated to confirm it. "
        f"{check['clause']} requires classification before plastic resistance "
        "can be used. Engineer judgement required."
    )
    return f


def _finding_material(check, extracted, sources, inputs, document):
    f = _base_finding(check, extracted, sources)
    grade, tf, fy_claimed = inputs.get("grade"), inputs.get("tf"), inputs.get("fy")
    if not grade or tf is None:
        f["status"] = "ASSUMED"
        f["issue"] = (
            "The steel grade or governing thickness could not be verified, so "
            "the yield strength used by every resistance check is an assumption. "
            "Result changes if a lower band applies (EN 10025-2)."
        )
        return f
    correct = fy_for(str(grade), float(tf))
    f["metrics"] = {"correct_fy": correct, "claimed_fy": fy_claimed, "tf": tf}
    if fy_claimed is not None and abs(float(fy_claimed) - correct) > 1e-9:
        f["status"] = "ERROR"
        f["issue"] = (
            f"fy taken as {_fmt(fy_claimed)} N/mm2, but for {grade} with "
            f"tf = {_fmt(tf)} mm the EN 10025-2 thickness band gives "
            f"fy = {_fmt(correct)} N/mm2. Every resistance computed from "
            f"{_fmt(fy_claimed)} is overstated."
        )
    else:
        f["status"] = "PASS"
        f["issue"] = (
            f"fy = {_fmt(correct)} N/mm2 is consistent with {grade} at "
            f"tf = {_fmt(tf)} mm per EN 10025-2."
        )
        f["action"] = "None — compliant."
    return f


def run_audit(element_type: str, extracted_values: dict,
              section_props: dict | None) -> list[dict]:
    """Loop the complete required check set for the element type; produce one
    deterministic finding per check. Spec Part 4.5."""
    registry = CHECK_REGISTRY[element_type]
    props = _prepare_props(section_props)
    values = extracted_values.get("values") or {}
    not_found = set(extracted_values.get("not_found") or [])
    document = extracted_values.get("document", "document.pdf")
    findings: list[dict] = []

    for check in registry:
        inputs, missing, assumed, sources = _gather(check["inputs"], props, extracted_values)
        missing = [m for m in dict.fromkeys(missing + [n for n in check["inputs"] if n in not_found and n not in inputs])]

        if check["kind"] == "qualitative":
            findings.append(_finding_qualitative(check, extracted_values, sources, inputs))
            continue

        if check["kind"] == "material":
            findings.append(_finding_material(check, extracted_values, sources, inputs, document))
            continue

        if missing:
            findings.append(_finding_missing(check, extracted_values, sources, missing))
            continue

        f = _base_finding(check, extracted_values, sources)
        f["assumed_inputs"] = assumed
        engineer_claim = _coerce(
            "x", (values.get(f"{check['id']}_result") or {}).get("value"))
        if not isinstance(engineer_claim, (int, float)):
            engineer_claim = None

        try:
            computed = _run_formula(check, inputs)
        except Exception as exc:  # a failure maps to a status, never a crash
            f["status"] = check["missing_status"]
            f["issue"] = (
                f"The {check['name'].lower()} check could not be computed "
                f"({exc}). Treated as {check['missing_status'].lower()}."
            )
            findings.append(f)
            continue

        cap_sym, unit = check["capacity_symbol"], check["unit"]

        if check["kind"] == "resistance":
            demand = inputs.get(check["demand_key"])
            verdict = classify(computed["result"], demand, engineer_claim)
            f["metrics"] = {**verdict, "demand": demand,
                            "capacity": round(computed["result"], 1)}
            ratio = verdict.get("ratio")
            d_sym = check["demand_symbol"]
            result_line = (
                f"{d_sym} / {cap_sym} = {_fmt(demand)} / {_fmt(computed['result'], 1)} "
                f"= {_fmt(ratio)} {'>' if (ratio or 0) > 1 else '<='} 1.0   "
                f"[{verdict['status']}]"
            )
            if verdict["status"] == "FAIL":
                f["issue"] = (
                    f"Exceeds the {check['name'].lower()} limit because "
                    f"{d_sym} = {_fmt(demand)} {unit} > {cap_sym} = "
                    f"{_fmt(computed['result'], 1)} {unit} ({_fmt(ratio)} > 1.0)."
                )
            elif verdict["status"] == "ERROR":
                over_note = ""
                if ratio is not None and ratio > 1.0:
                    over_note = (
                        f" The code-correct resistance is still exceeded "
                        f"({d_sym} / {cap_sym} = {_fmt(ratio)} > 1.0)."
                    )
                f["issue"] = (
                    f"The document states {cap_sym} = {_fmt(engineer_claim)} {unit}, "
                    f"but the code-correct value is {_fmt(computed['result'], 1)} {unit} "
                    f"({verdict['discrepancy_pct']}% discrepancy).{over_note}"
                )
            else:
                f["issue"] = (
                    f"{d_sym} = {_fmt(demand)} {unit} is within {cap_sym} = "
                    f"{_fmt(computed['result'], 1)} {unit} ({_fmt(ratio)} <= 1.0)."
                )
                f["action"] = "None — compliant."
            f["status"] = verdict["status"]
            f["calc"] = _calc_block(check, inputs, sources, computed, result_line, document)

        elif check["kind"] == "demand_vs_limit":
            w, w_lim = computed["result"], computed.get("w_lim")
            ratio = round(w / w_lim, 2) if w_lim else None
            status = "FAIL" if ratio and ratio > 1.0 else "PASS"
            f["status"] = status
            f["metrics"] = {"computed": round(w, 2), "limit": w_lim, "ratio": ratio}
            result_line = (
                f"w = {_fmt(w)} mm {'>' if status == 'FAIL' else '<='} "
                f"w_lim = {_fmt(w_lim)} mm   [{status}]"
            )
            f["issue"] = (
                f"Deflection w = {_fmt(w)} mm "
                f"{'exceeds' if status == 'FAIL' else 'is within'} the limit "
                f"w_lim = {_fmt(w_lim)} mm ({check['limit']})."
            )
            if status == "PASS":
                f["action"] = "None — compliant."
            f["calc"] = _calc_block(check, inputs, sources, computed, result_line, document)

        elif check["kind"] == "recompute":
            engineer_stated = _coerce(
                "x", (values.get(check["engineer_key"]) or {}).get("value"))
            if not isinstance(engineer_stated, (int, float)):
                engineer_stated = None
            verdict = classify_recompute(computed["result"], engineer_stated)
            na = check_national_annex(check, {**inputs, **{
                "gamma_Q_used": (values.get("gamma_Q_used") or {}).get("value")}})
            f["metrics"] = verdict
            f["status"] = verdict["status"]
            result_line = (
                f"Ed = {_fmt(computed['result'])} {unit} vs document "
                f"{_fmt(engineer_stated)} {unit}   [{verdict['status']}]"
            )
            if verdict["status"] == "ERROR":
                f["issue"] = (
                    f"The ULS combination gives Ed = {_fmt(computed['result'])} {unit} "
                    f"(1.35Gk + 1.50Qk per EN 1990), but the document carries "
                    f"{_fmt(engineer_stated)} {unit} "
                    f"({verdict['discrepancy_pct']}% discrepancy)."
                )
                if na.get("violation"):
                    f["issue"] += " " + na["violation"]
            else:
                f["issue"] = (
                    f"Design value Ed = {_fmt(computed['result'])} {unit} per "
                    f"EN 1990 Eq 6.10b; the document's figure agrees within tolerance."
                    if engineer_stated is not None else
                    f"Design value recomputed as Ed = {_fmt(computed['result'])} {unit} "
                    f"per EN 1990 Eq 6.10b."
                )
                f["action"] = "None — compliant."
            f["calc"] = _calc_block(check, inputs, sources, computed, result_line, document)

        findings.append(f)

    findings.sort(key=lambda x: STATUS_ORDER.index(x["status"]))
    return findings


def summarize(findings: list[dict]) -> dict:
    counts = {s: 0 for s in STATUS_ORDER}
    for f in findings:
        counts[f["status"]] += 1
    return {s: n for s, n in counts.items() if n}
