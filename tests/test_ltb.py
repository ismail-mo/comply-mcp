"""Known-answer tests for formulas.ltb — EC3 6.3.2.3 rolled-sections LTB.

Oracle: SCI P364 Example 3 sheets 7-9 (UKB 457x191x67, S275, Lcr = 9.0 m,
Mcr = 355.7 kNm from LTBeam, C1 = 2.65 = 355.7/134.2).
"""

from formulas.ltb import ltb


def test_p364_example3_full():
    r = ltb(MEd=260, Wpl_y=1470, fy=275, Mcr=355.7, h=453.4, b=189.9, C1=2.65)
    assert r["curve"] == "c" and r["alpha_LT"] == 0.49  # h/b=2.39 in (2,3.1]
    assert round(r["lam_bar_LT"], 2) == 1.07
    assert round(r["phi_LT"], 2) == 1.09
    assert round(r["chi_LT"], 2) == 0.60
    assert round(r["f"], 2) == 0.83
    assert round(r["chi_mod"], 2) == 0.72
    assert abs(r["result"] - 290.5) < 1.5  # sheet 291 (rounded chi); Blue Book 290
    assert r["unit"] == "kNm"
    assert r["governing"] == "MEd / Mb,Rd <= 1.0"


def test_p364_example3_unmodified():
    r = ltb(MEd=260, Wpl_y=1470, fy=275, Mcr=355.7, h=453.4, b=189.9)
    assert round(r["chi_mod"], 2) == 0.60


def test_neglect_below_threshold():
    r = ltb(MEd=100, Wpl_y=1470, fy=275, Mcr=4000, h=453.4, b=189.9)
    assert r["chi_mod"] == 1.0
    assert abs(r["result"] - 404.25) < 0.5
