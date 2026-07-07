"""EC3 plastic shear resistance Vpl,Rd for rolled I/H sections, load parallel
to the web.

Governing clauses: EN 1993-1-1 6.2.6(2) Eq 6.18 (resistance) and 6.2.6(3)(a)
(shear area of rolled I/H sections).

Oracle sources: SCI P364 worked examples — Example 2 sheet 5 (UB 533x210x92,
S275) and Example 3 sheet 5 (UKB 457x191x67, S275).
"""
import math


def shear(VEd, A, b, tf, tw, r, hw, fy, eta=1.0, gamma_M0=1.0):
    """Plastic shear resistance per EC3 6.2.6.

    Units: A cm2; b, tf, tw, r, hw mm; fy N/mm2; VEd kN. Returns Vpl,Rd in kN.
    """
    Av_rolled = A * 100 - 2 * b * tf + tf * (tw + 2 * r)
    Av_min = eta * hw * tw
    Av = max(Av_rolled, Av_min)
    Vpl_Rd = Av * (fy / math.sqrt(3)) / gamma_M0 / 1000
    ratio = round(VEd / Vpl_Rd, 2)
    steps = [
        f"Av = A - 2 b tf + tf (tw + 2 r) = {A} x 100 - 2 x {b} x {tf} "
        f"+ {tf} x ({tw} + 2 x {r}) = {Av_rolled:.1f} mm2   [EC3 6.2.6(3)(a)]",
        f"Av >= eta hw tw = {eta} x {hw} x {tw} = {Av_min:.1f} mm2 "
        f"-> Av = {Av:.1f} mm2   [EC3 6.2.6(3)]",
        f"Vpl,Rd = Av (fy / sqrt(3)) / gM0 = {Av:.1f} x ({fy} / 1.732) / "
        f"{gamma_M0} = {Vpl_Rd:.1f} kN   [EC3 6.2.6(2) Eq 6.18]",
        f"VEd / Vpl,Rd = {VEd} / {Vpl_Rd:.1f} = {ratio:.2f} <= 1.0   "
        f"[EC3 6.2.6(1) Eq 6.17]",
    ]
    return {
        "result": Vpl_Rd,
        "unit": "kN",
        "steps": steps,
        "governing": "VEd / Vpl,Rd <= 1.0",
        "Av": Av,
        "ratio": ratio,
    }
