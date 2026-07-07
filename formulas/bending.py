"""EC3 cross-section bending resistance, Class 1/2 (plastic).

Governing clause: EN 1993-1-1 6.2.5(2), Eq 6.13 — Mc,Rd = Wpl fy / gamma_M0.
Oracle sources: SCI P364 worked examples 2 & 3 (sheet 6 of each).
"""


def bending(MEd, Wpl_y, fy, gamma_M0=1.0):
    """Mc,Rd for a Class 1/2 section in major-axis bending.

    MEd kNm, Wpl_y cm3, fy N/mm2. Returns Mc,Rd in kNm.
    """
    Mc_Rd = Wpl_y * 1e3 * fy / gamma_M0 / 1e6  # kNm
    ratio = round(MEd / Mc_Rd, 2)
    steps = [
        f"Mc,Rd = Wpl,y fy / gM0 = ({Wpl_y} x 10^3 x {fy}) / {gamma_M0} = "
        f"{Mc_Rd:.2f} kNm   [EC3 6.2.5(2) Eq 6.13]",
        f"MEd / Mc,Rd = {MEd} / {Mc_Rd:.2f} = {ratio:.2f} <= 1.0   [EC3 6.2.5(1) Eq 6.12]",
    ]
    return {
        "result": Mc_Rd,
        "unit": "kNm",
        "steps": steps,
        "governing": "MEd / Mc,Rd <= 1.0",
        "ratio": ratio,
    }
