"""Known-answer tests for formulas.shear (EC3 6.2.6 plastic shear resistance).

Oracles: SCI P364 worked examples — Ex 2 sheet 5 (UB 533x210x92, S275),
Ex 3 sheet 5 (UKB 457x191x67, S275).
"""
from formulas.shear import shear


def test_p364_example2():
    r = shear(VEd=269.5, A=117, b=209.3, tf=15.6, tw=10.1, r=12.7,
              hw=501.9, fy=275)
    assert abs(r["Av"] - 5723.6) < 1.0
    assert abs(r["result"] - 909) < 1.0
    assert r["ratio"] == 0.30
    assert r["unit"] == "kN"
    assert r["governing"] == "VEd / Vpl,Rd <= 1.0"
    assert isinstance(r["steps"], list) and len(r["steps"]) >= 2


def test_p364_example3():
    r = shear(VEd=137, A=85.5, b=189.9, tf=12.7, tw=8.5, r=10.2,
              hw=428.0, fy=275)
    assert abs(r["Av"] - 4093.57) < 1.0
    assert abs(r["result"] - 650.0) < 1.0
    assert r["ratio"] == 0.21
