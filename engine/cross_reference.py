"""Inter-element consistency — CONFLICT detection. Deterministic, no AI.

The known case (spec Part 14.4): one part of the submission states S275 for
the column calc while another states S355 — fy differs between elements.
CONFLICT findings satisfy the full frontend AuditFinding contract.
"""


def cross_reference(extracts_by_element: dict[str, dict]) -> list[dict]:
    """extracts_by_element: {element_type: extracted_values dict}.
    Returns CONFLICT findings for parameters that must agree across
    elements/documents but do not."""
    findings: list[dict] = []
    for param, clause in (("grade", "EN 10025-2"), ("fy", "EN 10025-2")):
        seen: dict = {}
        for element, extracted in extracts_by_element.items():
            entry = (extracted.get("values") or {}).get(param)
            if not entry or entry.get("value") in (None, ""):
                continue
            seen[element] = entry
        distinct = {str(e["value"]) for e in seen.values()}
        if len(distinct) > 1:
            detail = "; ".join(
                f"{el}: {e['value']}"
                + (f" (p.{e['page']})" if e.get("page") else "")
                for el, e in seen.items()
            )
            first = next(iter(seen.values()))
            findings.append({
                "check_id": f"conflict_{param}",
                "status": "CONFLICT",
                "name": f"Inconsistent {param}",
                "category_sub": "Structural . material",
                "clause": clause,
                "badge": "en10025",
                "issue": (
                    f"The document states different values of {param} for "
                    f"different elements ({detail}). One of them governs the "
                    f"other checks, so the disagreement must be resolved."
                ),
                "action": "Confirm the specified grade on the section order and align every calculation with it.",
                "reference": {
                    "quote": first.get("quote") or detail,
                    "clause": clause,
                    "page": first.get("page"),
                    "source": None,
                },
                "calc": None,
                "metrics": {},
                "assumed_inputs": [],
            })
    return findings
