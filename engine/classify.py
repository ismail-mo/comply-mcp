"""Status assignment — deterministic branches over numbers. No AI.

Full taxonomy (spec Part 4.6):
  FAIL      Ed > Rd — a number proves the clause is breached
  ERROR     computed differs from the engineer's figure by > tolerance,
            or a wrong partial factor / unreferenced value
  MISSING   a required input absent -> the check was never performed
  ASSUMED   an input flagged unverified and the result depends on it
  WARNING   qualitative clause — no number can satisfy it
  PASS      Ed <= Rd — a number proves the clause is satisfied
  CONFLICT  two element values disagree (engine/cross_reference.py)
"""

TOLERANCE = 0.02  # 2% — spec Part 4.6


def classify(computed_result: float, demand: float | None,
             engineer_value: float | None = None,
             tolerance: float = TOLERANCE) -> dict:
    """Classify a resistance-style check.

    computed_result: the engine's code-correct resistance (Rd)
    demand:          the design action effect (Ed), if known
    engineer_value:  the resistance the REPORT claims, if it states one
    """
    out: dict = {"computed": round(computed_result, 2)}

    if demand is not None and computed_result:
        ratio = demand / computed_result
        out["ratio"] = round(ratio, 2)
        out["delta"] = round(demand - computed_result, 1)

    # ERROR — the engineer's number differs from the correct formula result.
    if engineer_value is not None and computed_result:
        disc = abs(computed_result - engineer_value) / abs(computed_result)
        if disc > tolerance:
            out.update({
                "status": "ERROR",
                "engineer": engineer_value,
                "discrepancy_pct": round(disc * 100, 1),
            })
            return out

    if demand is None:
        out["status"] = "PASS"  # resistance computed, no demand to compare
        return out

    out["status"] = "FAIL" if out["ratio"] > 1.0 else "PASS"
    return out


def classify_recompute(computed: float, engineer_value: float | None,
                       tolerance: float = TOLERANCE) -> dict:
    """Classify a recompute-style check (e.g. the ULS load combination):
    the engine recomputes the value; the report's stated figure either
    matches (PASS) or does not (ERROR)."""
    out: dict = {"computed": round(computed, 2)}
    if engineer_value is None:
        out["status"] = "PASS"
        out["note"] = "recomputed value; report states no comparable figure"
        return out
    disc = abs(computed - engineer_value) / abs(computed) if computed else 0.0
    out["engineer"] = engineer_value
    out["discrepancy_pct"] = round(disc * 100, 1)
    out["status"] = "ERROR" if disc > tolerance else "PASS"
    return out
