"""EN 1990 ULS load combination — UK NA Eq 6.10b (governing) and Eq 6.10.

Governing clauses: BS EN 1990 Eq 6.10 / 6.10b with UK NA Table NA.A1.2(B)
factors (gamma_G = 1.35, gamma_Q = 1.50, xi = 0.925 from
tables.partial_factors).

Oracle sources: SCI P364 Example 2 sheets 2-3, Example 3 sheet 2.
"""
from tables.partial_factors import GAMMA_G, GAMMA_Q, XI


def load_combo(Gk, Qk, use_6_10b=True, gamma_G=None, gamma_Q=None, xi=None):
    """Ed = xi*gamma_G*Gk + gamma_Q*Qk (Eq 6.10b) or gamma_G*Gk + gamma_Q*Qk (Eq 6.10)."""
    gamma_G = GAMMA_G if gamma_G is None else gamma_G
    gamma_Q = GAMMA_Q if gamma_Q is None else gamma_Q
    xi = XI if xi is None else xi

    if use_6_10b:
        Ed = xi * gamma_G * Gk + gamma_Q * Qk
        governing = "Ed per EN 1990 Eq 6.10b (UK NA Table NA.A1.2(B))"
        steps = [
            f"Ed = xi gamma_G Gk + gamma_Q Qk = {xi} x {gamma_G} x {Gk} + "
            f"{gamma_Q} x {Qk} = {Ed}   [EN 1990 Eq 6.10b, UK NA Table NA.A1.2(B)]"
        ]
    else:
        Ed = gamma_G * Gk + gamma_Q * Qk
        governing = "Ed per EN 1990 Eq 6.10 (UK NA Table NA.A1.2(B))"
        steps = [
            f"Ed = gamma_G Gk + gamma_Q Qk = {gamma_G} x {Gk} + "
            f"{gamma_Q} x {Qk} = {Ed}   [EN 1990 Eq 6.10, UK NA Table NA.A1.2(B)]"
        ]

    return {
        "result": Ed,
        "unit": "same as inputs",
        "steps": steps,
        "governing": governing,
        "gamma_G": gamma_G,
        "gamma_Q": gamma_Q,
        "xi": xi,
    }


def simply_supported_effects(w, P_mid, L):
    """Design effects for a simply supported span: UDL w (kN/m), midspan point
    load P_mid (kN), span L (m). Statics only (no code coefficients)."""
    MEd = w * L ** 2 / 8 + P_mid * L / 4
    VEd = w * L / 2 + P_mid / 2
    steps = [
        f"MEd = w L^2/8 + P L/4 = {w} x {L}^2/8 + {P_mid} x {L}/4 = {MEd} kNm   [statics, simply supported]",
        f"VEd = w L/2 + P/2 = {w} x {L}/2 + {P_mid}/2 = {VEd} kN   [statics, simply supported]",
    ]
    return {"MEd": MEd, "VEd": VEd, "steps": steps}
