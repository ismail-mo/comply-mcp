"""Lateral-torsional buckling resistance Mb,Rd — rolled-sections method.

Governing clauses: BS EN 1993-1-1:2005 6.3.2.2 (lambda_bar_LT, neglect
threshold), 6.3.2.3(1) Eq 6.57 (chi_LT, rolled sections), 6.3.2.3(2)
(moment-shape modification f), Eq 6.55 (Mb,Rd), with UK NA parameters
NA.2.16/NA.2.17/NA.2.18 (lambda_LT,0 = 0.4, beta = 0.75, curve by h/b,
alpha_LT per Table 6.5 letters). Mcr is an input (EC3-1-1 gives no Mcr
method; SCI P364 obtains it from LTBeam).

Oracle: SCI P364 Example 3 sheets 7-9 (457x191x67 UKB, S275, Lcr = 9.0 m,
Mcr = 355.7 kNm, C1 = 2.65).
"""

import math

from tables.ltb_curves import LAMBDA_LT0, BETA_LT, ltb_curve
from tables.imperfection import IMPERFECTION_FACTOR


def ltb(MEd, Wpl_y, fy, Mcr, h, b, C1=None, gamma_M1=1.0):
    """EC3 6.3.2.3 LTB. Units: Wpl_y cm3, fy N/mm2, Mcr/MEd kNm, h/b mm."""
    Wpl = Wpl_y * 1e3  # mm3
    steps = []

    lam = math.sqrt(Wpl * fy / (Mcr * 1e6))
    steps.append(
        f"lam_bar_LT = sqrt(Wpl,y fy / Mcr) = sqrt({Wpl_y} x 1e3 x {fy} / "
        f"{Mcr} x 1e6) = {lam:.3f}   [EC3 6.3.2.2(1)]"
    )

    h_over_b = h / b
    curve = ltb_curve(h_over_b)
    alpha_LT = IMPERFECTION_FACTOR[curve]
    steps.append(
        f"h/b = {h}/{b} = {h_over_b:.2f} -> buckling curve '{curve}'   [UK NA.2.17]"
    )
    steps.append(
        f"alpha_LT = {alpha_LT} for curve '{curve}'   [NA.2.16 & Table 6.5]"
    )

    if lam <= LAMBDA_LT0:
        phi_LT = 0.5 * (1 + alpha_LT * (lam - LAMBDA_LT0) + BETA_LT * lam**2)
        chi_LT = 1.0
        steps.append(
            f"lam_bar_LT = {lam:.3f} <= lambda_LT,0 = {LAMBDA_LT0}: LTB may be "
            f"neglected, chi_LT = 1.0   [EC3 6.3.2.2(4), NA.2.17]"
        )
    else:
        phi_LT = 0.5 * (1 + alpha_LT * (lam - LAMBDA_LT0) + BETA_LT * lam**2)
        steps.append(
            f"phi_LT = 0.5 (1 + {alpha_LT} x ({lam:.3f} - {LAMBDA_LT0}) + "
            f"{BETA_LT} x {lam:.3f}^2) = {phi_LT:.3f}   [EC3 6.3.2.3(1)]"
        )
        chi_LT = min(
            1.0,
            1 / lam**2,
            1 / (phi_LT + math.sqrt(phi_LT**2 - BETA_LT * lam**2)),
        )
        steps.append(
            f"chi_LT = min(1.0, 1/{lam:.3f}^2, 1/({phi_LT:.3f} + "
            f"sqrt({phi_LT:.3f}^2 - {BETA_LT} x {lam:.3f}^2))) = {chi_LT:.3f}"
            f"   [EC3 Eq 6.57]"
        )

    if C1 is not None:
        kc = 1 / math.sqrt(C1)
        f = min(1.0, 1 - 0.5 * (1 - kc) * (1 - 2 * (lam - 0.8) ** 2))
        chi_mod = min(chi_LT / f, 1.0)
        steps.append(
            f"kc = 1/sqrt(C1) = 1/sqrt({C1}) = {kc:.3f}   [EC3 6.3.2.3(2), NA.2.18]"
        )
        steps.append(
            f"f = min(1, 1 - 0.5 (1 - {kc:.3f}) (1 - 2 ({lam:.3f} - 0.8)^2)) "
            f"= {f:.3f}   [EC3 6.3.2.3(2)]"
        )
        steps.append(
            f"chi_LT,mod = min(chi_LT / f, 1.0) = min({chi_LT:.3f}/{f:.3f}, 1.0) "
            f"= {chi_mod:.3f}   [EC3 Eq 6.58]"
        )
    else:
        f = 1.0
        chi_mod = chi_LT
        steps.append("No C1 given: chi_LT,mod = chi_LT (f = 1.0)")

    Mb_Rd = chi_mod * Wpl * fy / gamma_M1 / 1e6
    steps.append(
        f"Mb,Rd = chi_LT,mod Wpl,y fy / gM1 = {chi_mod:.3f} x {Wpl_y} x 1e3 x "
        f"{fy} / {gamma_M1} = {Mb_Rd:.1f} kNm   [EC3 6.3.2.1(3) Eq 6.55]"
    )
    steps.append(
        f"MEd / Mb,Rd = {MEd} / {Mb_Rd:.1f} = {MEd / Mb_Rd:.3f}"
        f"   [EC3 6.3.2.1(1) Eq 6.54]"
    )

    return {
        "result": Mb_Rd,
        "unit": "kNm",
        "steps": steps,
        "governing": "MEd / Mb,Rd <= 1.0",
        "lam_bar_LT": lam,
        "curve": curve,
        "alpha_LT": alpha_LT,
        "phi_LT": phi_LT,
        "chi_LT": chi_LT,
        "f": f,
        "chi_mod": chi_mod,
    }
