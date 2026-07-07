"""Tests for formulas.deflection — oracle: SCI P364 Ex 2 sheet 10
(UB 533x210x92, Iy=55200 cm4, L=6500 mm, variable actions only
q1=30 kN/m, Q2=50 kN)."""

from formulas.deflection import deflection


def test_p364_ex2_sheet10():
    r = deflection(q=30, P=50, L=6500, Iy=55200)
    assert abs(r["result"] - 8.5) < 0.1      # sheet: 8.5 mm
    assert abs(r["w_lim"] - 18.1) < 0.1      # sheet: 6500/360 = 18.1 mm
    assert r["unit"] == "mm"
    assert r["governing"] == "w <= L/360"
    assert abs(r["ratio"] - round(r["result"] / r["w_lim"], 2)) < 1e-9
    assert isinstance(r["steps"], list) and len(r["steps"]) >= 3


def test_limit_variants():
    r = deflection(q=30, P=50, L=6500, Iy=55200, limit_denominator=250)
    assert r["w_lim"] == 26.0
    assert r["governing"] == "w <= L/250"
