"""EC3 flexural buckling resistance Nb,Rd — BS EN 1993-1-1:2005 clause 6.3.1.

Governing clauses: 6.3.1.1 (Eq 6.46/6.47), 6.3.1.2(1) (Eq 6.49, phi and chi),
6.3.1.3(1) (non-dimensional slenderness, lambda_1 = 93.9 epsilon), Table 6.1
(imperfection factor alpha), Table 6.2 (buckling curve selection).

Oracle sources:
- SCI P364 Example 9 (UKC 356x368x129, S355): Nb,Rd = 3678 kN (sheet;
  Blue Book 3670 kN), curve c, alpha 0.49, lam_bar 0.82, chi 0.65.
- Coursework Check 8 hand arithmetic for the phi->chi core.
"""

import math

from tables.buckling_curves import BUCKLING_CURVE
from tables.imperfection import IMPERFECTION_FACTOR
from tables.partial_factors import lambda_1


def phi_factor(alpha: float, lam_bar: float) -> float:
    """phi = 0.5 (1 + alpha (lam_bar - 0.2) + lam_bar^2) — EC3 6.3.1.2(1)."""
    return 0.5 * (1.0 + alpha * (lam_bar - 0.2) + lam_bar ** 2)


def chi_from_phi(phi: float, lam_bar: float) -> float:
    """chi = 1 / (phi + sqrt(phi^2 - lam_bar^2)), capped at 1.0 — Eq 6.49."""
    return min(1.0, 1.0 / (phi + math.sqrt(phi ** 2 - lam_bar ** 2)))


def flexural_buckling(NEd: float, A: float, iz: float, Le: float, fy: float,
                      section_type: str, axis: str,
                      gamma_M1: float = 1.0) -> dict:
    """Flexural buckling resistance Nb,Rd to EC3 6.3.1.

    Units: A cm2, iz cm, Le m, fy N/mm2, NEd kN. result = Nb,Rd in kN.
    """
    curve = BUCKLING_CURVE[(section_type, axis)]
    alpha = IMPERFECTION_FACTOR[curve]
    Npl_Rd = A * 100.0 * fy / gamma_M1 / 1000.0  # kN
    lam = (Le * 1000.0) / (iz * 10.0)
    lam_1 = lambda_1(fy)
    lam_bar = lam / lam_1
    phi = phi_factor(alpha, lam_bar)
    chi = chi_from_phi(phi, lam_bar)
    Nb_Rd = chi * Npl_Rd

    steps = [
        f"Buckling curve ({section_type}, {axis} axis) = '{curve}'   [EC3 Table 6.2]",
        f"alpha = {alpha}   [EC3 Table 6.1]",
        f"Npl,Rd = A fy / gM1 = ({A * 100.0:.0f} x {fy}) / {gamma_M1} = {Npl_Rd:.1f} kN   [EC3 6.3.1.1 Eq 6.47]",
        f"lambda = Le / i = {Le * 1000.0:.0f} / {iz * 10.0:.1f} = {lam:.2f}   [EC3 6.3.1.3(1)]",
        f"lambda_1 = 93.9 epsilon = 93.9 x sqrt(235/{fy}) = {lam_1:.2f}   [EC3 6.3.1.3(1)]",
        f"lambda_bar = {lam:.2f} / {lam_1:.2f} = {lam_bar:.3f}   [EC3 6.3.1.3(1) Eq 6.50]",
        f"phi = 0.5 (1 + {alpha} ({lam_bar:.3f} - 0.2) + {lam_bar:.3f}^2) = {phi:.3f}   [EC3 6.3.1.2(1)]",
        f"chi = 1 / ({phi:.3f} + sqrt({phi:.3f}^2 - {lam_bar:.3f}^2)) = {chi:.3f}   [EC3 6.3.1.2(1) Eq 6.49]",
        f"Nb,Rd = chi Npl,Rd = {chi:.3f} x {Npl_Rd:.1f} = {Nb_Rd:.1f} kN   [EC3 6.3.1.1 Eq 6.47]",
        f"NEd / Nb,Rd = {NEd} / {Nb_Rd:.1f} = {NEd / Nb_Rd:.3f}   [EC3 6.3.1.1 Eq 6.46]",
    ]

    return {
        "result": Nb_Rd,
        "unit": "kN",
        "steps": steps,
        "governing": "NEd / Nb,Rd <= 1.0",
        "chi": chi,
        "lam_bar": lam_bar,
        "phi": phi,
        "curve": curve,
        "alpha": alpha,
        "Npl_Rd": Npl_Rd,
    }
