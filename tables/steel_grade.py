"""Nominal yield strength by grade and thickness band — pure DATA.

Transcribed from BS EN 10025-2 Table 7 (ReH by product thickness band).

Independently confirmed points in the reference set:
- S275, t <= 16 mm  -> fy = 275 N/mm2  (P364 Ex 2 sheet 3, Ex 3 sheet 4)
- S355, 16 < t <= 40 -> fy = 345 N/mm2 (P364 Ex 9 sheet 2)
- S275, 16 < t <= 40 -> fy = 265 N/mm2 (spec Part 6.6 exemplar)
Remaining bands transcribed from EN 10025-2 Table 7 directly.
"""

# grade -> list of (max_thickness_mm, fy_N_per_mm2), ascending
FY_BY_GRADE = {
    "S235": [(16, 235), (40, 225), (63, 215)],
    "S275": [(16, 275), (40, 265), (63, 255)],
    "S355": [(16, 355), (40, 345), (63, 335)],
    "S450": [(16, 450), (40, 430), (63, 410)],
}


def fy_for(grade: str, t_mm: float) -> float:
    """Nominal fy for a grade and governing element thickness (EN 10025-2 T7)."""
    bands = FY_BY_GRADE[grade.upper().replace(" ", "")]
    for t_max, fy in bands:
        if t_mm <= t_max:
            return float(fy)
    raise ValueError(f"{grade}: thickness {t_mm} mm beyond transcribed bands")
