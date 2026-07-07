"""Imperfection factors — pure DATA, no logic.

Transcribed from BS EN 1993-1-1:2005 Table 6.1 (imperfection factor alpha
for the flexural buckling curves) and Table 6.3 (alpha_LT for the
lateral-torsional buckling curves — same numeric values per curve letter).

Independent confirmations in the reference set:
- SCI P364 Example 9 sheet 4: "For buckling curve 'c' the imperfection
  factor is alpha = 0.49"  (flexural, Table 6.1)
- SCI P364 Example 3 sheet 7: "For buckling curve 'c', alpha_LT = 0.49"
  (LTB, NA.2.16 & Table 6.5)
"""

IMPERFECTION_FACTOR = {
    "a0": 0.13,
    "a": 0.21,
    "b": 0.34,
    "c": 0.49,
    "d": 0.76,
}
