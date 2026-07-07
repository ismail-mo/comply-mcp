"""Tests for formulas.flexural_buckling — EC3 6.3.1 flexural buckling Nb,Rd.

Oracles:
- SCI P364 Example 9 (UKC 356x368x129, S355): sheet value Nb,Rd = 3678 kN
  (Blue Book 3670 kN), curve c, alpha 0.49, lam_bar 0.82, chi 0.65.
- Coursework Check 8 hand arithmetic (phi/chi core, alpha=0.34, lam_bar=0.513).
- Check 8 through the full engine with correct EC3 tables (see divergence
  note on test_check8_engine_correct).
"""

from formulas.flexural_buckling import (
    chi_from_phi,
    flexural_buckling,
    phi_factor,
)


def test_p364_example9():
    """SCI P364 Ex 9: UKC 356x368x129, S355, Le = 6.0 m, minor axis."""
    r = flexural_buckling(NEd=3500, A=164, iz=9.43, Le=6.0, fy=345,
                          section_type="UC", axis="minor")
    assert r["curve"] == "c" and r["alpha"] == 0.49
    assert round(r["lam_bar"], 2) == 0.82
    assert round(r["chi"], 2) == 0.65
    assert abs(r["result"] - 3678) < 10        # sheet 3678; Blue Book 3670


def test_check8_arithmetic_core():
    """Coursework Check 8 hand arithmetic — validates phi -> chi exactly as
    hand-worked (the coursework used alpha = 0.34 and lam_bar = 0.513)."""
    assert round(phi_factor(0.34, 0.513), 3) == 0.685
    assert round(chi_from_phi(0.685, 0.513), 3) == 0.878
    assert abs(0.878 * 4622.75 - 4059.2) < 0.5


def test_check8_engine_correct():
    """Check-8 inputs through the FULL formula with correct EC3 tables.

    This intentionally DIVERGES from the coursework's 4059.2 kN: the
    coursework used curve b (alpha = 0.34) and lambda_1 = 93.9 without the
    epsilon factor, which reproduces 4059.2. EC3 Table 6.2 gives curve c
    for a UC about the minor axis, and clause 6.3.1.3(1) gives
    lambda_1 = 93.9 * sqrt(235/fy); with those the code-correct resistance
    is 3753.7 kN, and the product flags the report's figure as an ERROR.
    """
    r = flexural_buckling(NEd=6896.25, A=168.1, iz=6.69, Le=3.22, fy=275,
                          section_type="UC", axis="minor")
    assert r["curve"] == "c"
    assert round(r["chi"], 3) == 0.812
    assert abs(r["result"] - 3753.7) < 2.0
