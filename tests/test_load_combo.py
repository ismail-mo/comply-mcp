"""Known-answer tests for formulas.load_combo.

Oracles: SCI P364 Example 2 sheets 2-3 and Example 3 sheet 2.
"""
from formulas.load_combo import load_combo, simply_supported_effects


def test_ex2_udl():
    r = load_combo(15, 30)
    assert abs(r["result"] - 63.73125) < 1e-6
    assert round(r["result"], 1) == 63.7


def test_ex2_point():
    r = load_combo(40, 50)
    assert abs(r["result"] - 124.95) < 1e-6
    assert round(r["result"], 1) == 125.0


def test_ex3():
    r1 = load_combo(3, 0)
    assert abs(r1["result"] - 3.74625) < 1e-6
    assert round(r1["result"], 1) == 3.7

    r2 = load_combo(40, 60)
    assert abs(r2["result"] - 139.95) < 1e-6
    assert round(r2["result"], 1) == 140.0

    r3 = load_combo(20, 30)
    assert abs(r3["result"] - 69.975) < 1e-6
    assert round(r3["result"], 1) == 70.0


def test_effects():
    eff = simply_supported_effects(w=63.7, P_mid=125.0, L=6.5)
    assert abs(eff["MEd"] - 539.5) < 0.15
    assert abs(eff["VEd"] - 269.5) < 0.1
    assert isinstance(eff["steps"], list) and eff["steps"]


def test_6_10():
    r = load_combo(15, 30, use_6_10b=False)
    assert r["result"] == 1.35 * 15 + 1.5 * 30 == 65.25


def test_contract():
    r = load_combo(15, 30)
    assert r["unit"] == "same as inputs"
    assert r["governing"] == "Ed per EN 1990 Eq 6.10b (UK NA Table NA.A1.2(B))"
    assert r["gamma_G"] == 1.35 and r["gamma_Q"] == 1.50 and r["xi"] == 0.925
    assert isinstance(r["steps"], list) and r["steps"]
