"""SLS vertical deflection of a simply supported beam (UDL + midspan point load).

Governing clauses: BS EN 1990 A1.4.3 (serviceability criteria, variable
actions only); BS EN 1993-1-1 clause 7.2.1 (vertical deflections — limits
left to the National Annex / project; default limit L/360 here).

Oracle: SCI P364 Worked Example 2, sheet 10 (UB 533x210x92, Iy = 55200 cm4,
L = 6500 mm, q = 30 kN/m, Q = 50 kN -> w = 8.5 mm, w_lim = 6500/360 = 18.1 mm).
"""


def deflection(q, P, L, Iy, E=210000.0, limit_denominator=360):
    """SLS midspan deflection, simply supported beam, variable actions only.

    q kN/m (== N/mm), P kN, L mm, Iy cm4, E N/mm2. Returns w in mm.
    """
    EI = E * Iy * 1e4  # N.mm2 (Iy cm4 -> mm4)
    w_udl = 5.0 * q * L**4 / (384.0 * EI)
    w_point = (P * 1e3) * L**3 / (48.0 * EI)
    w = w_udl + w_point
    w_lim = L / limit_denominator
    ratio = round(w / w_lim, 2)
    den = limit_denominator
    steps = [
        f"EI = E Iy = {E:.0f} x {Iy} x 1e4 = {EI:.4g} N.mm2   [EN 1993-1-1 3.2.6]",
        f"w_udl = 5 q L^4 / (384 EI) = 5 x {q} x {L}^4 / (384 x {EI:.4g}) = {w_udl:.2f} mm   [elastic beam theory]",
        f"w_point = P L^3 / (48 EI) = {P * 1e3:.0f} x {L}^3 / (48 x {EI:.4g}) = {w_point:.2f} mm   [elastic beam theory]",
        f"w = w_udl + w_point = {w_udl:.2f} + {w_point:.2f} = {w:.2f} mm   [EN 1990 A1.4.3]",
        f"w_lim = L/{den} = {L}/{den} = {w_lim:.2f} mm   [EC3 7.2.1 / NA]",
        f"w / w_lim = {w:.2f} / {w_lim:.2f} = {ratio:.2f} {'<= 1.0 OK' if ratio <= 1.0 else '> 1.0 FAIL'}   [EC3 7.2.1]",
    ]
    return {
        "result": w,
        "unit": "mm",
        "steps": steps,
        "governing": f"w <= L/{den}",
        "w_lim": w_lim,
        "ratio": ratio,
        "utilisation": ratio,
    }
