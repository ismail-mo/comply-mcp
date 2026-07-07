"""Lateral-torsional buckling parameters — UK National Annex, rolled sections.

Transcribed from the UK National Annex to BS EN 1993-1-1 (NA.2.17), for the
rolled-sections method of clause 6.3.2.3:

    lambda_bar_LT,0 = 0.4
    beta            = 0.75
    buckling curve (rolled doubly-symmetric I/H, by h/b):
        h/b <= 2.0        -> curve b
        2.0 < h/b <= 3.1  -> curve c
        h/b > 3.1         -> curve d

Independent confirmation in the reference set:
- SCI P364 Example 3 sheet 7 (457x191x67 UKB): "From the UK National
  Annex, lambda_LT,0 = 0.4 and beta = 0.75"; "h/b = 453.4/189.9 = 2.39;
  2 < 2.39 < 3.1, therefore use buckling curve 'c'"; "for buckling curve
  'c', alpha_LT = 0.49".
The h/b <= 2 and > 3.1 bands are transcribed from the same NA table row
set; only the middle band is exercised by the known-answer tests.
"""

LAMBDA_LT0 = 0.4
BETA_LT = 0.75


def ltb_curve(h_over_b: float) -> str:
    if h_over_b <= 2.0:
        return "b"
    if h_over_b <= 3.1:
        return "c"
    return "d"
