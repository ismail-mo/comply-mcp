"""Flexural buckling curve selection — pure DATA + one lookup function.

Transcribed from BS EN 1993-1-1:2005 Table 6.2 (selection of buckling
curve for a cross-section), hot-rolled I/H sections, S235–S420 column:

    h/b > 1.2 :  tf <= 40 mm   -> y-y: a,  z-z: b
                 40 < tf <= 100 -> y-y: b,  z-z: c
    h/b <= 1.2:  tf <= 100 mm  -> y-y: b,  z-z: c
                 tf > 100      -> y-y: d,  z-z: d

Independent confirmation in the reference set:
- SCI P364 Example 9 sheet 4: UKC 356x368x129, h/b = 355.6/368.6 = 0.96
  < 1.2 and tf = 17.5 mm < 100 mm -> "buckling curve to consider for the
  z-z axis is 'c'" (printed on the sheet).

The simplified (section_type, axis) contract below is the one the spec
(Part 4.2) fixes for the formula layer: UB-family sections have h/b > 1.2
with tf <= 40; UC-family sections have h/b <= 1.2 with tf <= 100.
"""

# Spec-contract lookup: (section_type, axis) -> curve letter.
BUCKLING_CURVE = {
    ("UB", "major"): "a",
    ("UB", "minor"): "b",
    ("UC", "major"): "b",
    ("UC", "minor"): "c",
}


def flexural_curve(h_over_b: float, tf_mm: float, axis: str) -> str:
    """Full EC3 Table 6.2 selection for hot-rolled I/H, S235–S420.

    axis: "major" (y-y) or "minor" (z-z).
    """
    if axis not in ("major", "minor"):
        raise ValueError(f"axis must be 'major' or 'minor', got {axis!r}")
    if h_over_b > 1.2:
        if tf_mm <= 40:
            return "a" if axis == "major" else "b"
        if tf_mm <= 100:
            return "b" if axis == "major" else "c"
        raise ValueError("Table 6.2: rolled I/H with h/b > 1.2, tf > 100 mm not tabulated")
    if tf_mm <= 100:
        return "b" if axis == "major" else "c"
    return "d"
