"""UK National Annex cross-checks — pure dict lookups, no computation.

check_national_annex(check, inputs) returns an informational note about the
NA parameters governing the check, and — where an extracted gamma factor is
available — whether it matches the NA-required value.
"""

from tables.partial_factors import GAMMA_G, GAMMA_Q, XI, GAMMA_M0, GAMMA_M1

_NA_NOTES = {
    "load_combo": (
        f"UK NA to BS EN 1990, Table NA.A1.2(B): gamma_G = {GAMMA_G}, "
        f"gamma_Q = {GAMMA_Q}, xi = {XI} (Eq 6.10b governs unless permanent "
        f"actions exceed 4.5x variable)."
    ),
    "flex_buckling": f"UK NA to BS EN 1993-1-1, NA.2.15: gamma_M1 = {GAMMA_M1}.",
    "ltb": "UK NA to BS EN 1993-1-1, NA.2.17: lambda_LT,0 = 0.4, beta = 0.75; buckling curve by h/b.",
    "compression": f"UK NA to BS EN 1993-1-1, NA.2.15: gamma_M0 = {GAMMA_M0}.",
    "bending": f"UK NA to BS EN 1993-1-1, NA.2.15: gamma_M0 = {GAMMA_M0}.",
    "shear": f"UK NA to BS EN 1993-1-1, NA.2.15: gamma_M0 = {GAMMA_M0}.",
}


def check_national_annex(check: dict, inputs: dict) -> dict:
    note = _NA_NOTES.get(check["id"])
    result = {"note": note} if note else {}
    # Deterministic gamma verification when the report's factor was extracted.
    if check["id"] == "load_combo":
        used_gq = inputs.get("gamma_Q_used")
        if used_gq is not None and abs(float(used_gq) - GAMMA_Q) > 1e-9:
            result["violation"] = (
                f"gamma_Q = {used_gq} applied to variable actions; UK NA Table "
                f"NA.A1.2(B) requires gamma_Q = {GAMMA_Q}."
            )
    return result
