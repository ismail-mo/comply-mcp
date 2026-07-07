"""Partial factors and slenderness constant — pure DATA.

Sources (each printed on the cited P364 calculation sheet):
- gamma_M0 = 1.0, gamma_M1 = 1.0 : UK NA to BS EN 1993-1-1, NA.2.15
  (P364 Ex 2 sheet 4, Ex 3 sheet 4, Ex 9 sheet 3)
- gamma_G = 1.35, gamma_Q = 1.50, xi = 0.925 : BS EN 1990 Table
  NA.A1.2(B) (P364 Ex 2 sheet 2, Ex 3 sheet 2)
- lambda_1 = 93.9 * epsilon, epsilon = sqrt(235/fy) : BS EN 1993-1-1
  clause 6.3.1.3(1) (P364 Ex 9 sheet 4: lambda_1 = 93.9 x 0.83 = 77.94)
"""

GAMMA_M0 = 1.0
GAMMA_M1 = 1.0

GAMMA_G = 1.35
GAMMA_Q = 1.50
XI = 0.925

LAMBDA_1_COEFFICIENT = 93.9  # lambda_1 = 93.9 * sqrt(235 / fy)


def epsilon(fy: float) -> float:
    """epsilon = sqrt(235/fy) — EC3 Table 5.2 / clause 6.3.1.3."""
    return (235.0 / fy) ** 0.5


def lambda_1(fy: float) -> float:
    """lambda_1 = 93.9 * epsilon — EC3 clause 6.3.1.3(1)."""
    return LAMBDA_1_COEFFICIENT * epsilon(fy)
