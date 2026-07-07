"""Known-answer tests for formulas.bending (EC3 6.2.5, Eq 6.13).

Oracles: SCI P364 worked examples 2 & 3 (sheet 6 of each).
"""
from formulas.bending import bending


def test_p364_example2():
    # Ex 2 sheet 6 (UB 533x210x92, S275)
    r = bending(MEd=539.5, Wpl_y=2360, fy=275)
    assert abs(r["result"] - 649.0) < 0.5
    assert r["ratio"] == 0.83


def test_p364_example3():
    # Ex 3 sheet 6 (UKB 457x191x67, S275)
    r = bending(MEd=260, Wpl_y=1470, fy=275)
    assert abs(r["result"] - 404.25) < 0.5  # sheet prints 404; Blue Book 405
    assert r["ratio"] == 0.64


def test_contract_keys():
    r = bending(MEd=260, Wpl_y=1470, fy=275)
    assert r["unit"] == "kNm"
    assert r["governing"] == "MEd / Mc,Rd <= 1.0"
    assert isinstance(r["steps"], list) and all(isinstance(s, str) for s in r["steps"])
