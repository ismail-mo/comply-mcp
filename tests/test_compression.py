"""Tests for formulas.compression — EC3 6.2.4 Nc,Rd.

Oracles:
- SCI P364 Example 9 sheet 3 (UKC 356x368x129, S355): Nc,Rd = 5658 kN.
- Coursework Check 8 squash load (S275): Npl,Rd = 4622.75 kN.
"""
from formulas.compression import compression


def test_p364_example9():
    r = compression(NEd=3500, A=164, fy=345)
    assert abs(r["result"] - 5658) < 1
    assert r["ratio"] == 0.62
    assert r["unit"] == "kN"
    assert r["governing"] == "NEd / Nc,Rd <= 1.0"
    assert isinstance(r["steps"], list) and r["steps"]


def test_check8_report_value():
    r = compression(NEd=6896.25, A=168.1, fy=275)
    assert abs(r["result"] - 4622.75) < 0.5
