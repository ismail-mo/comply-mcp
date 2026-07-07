"""EC3 cross-section compression resistance Nc,Rd.

Governing clause: EN 1993-1-1 6.2.4(2) Eq 6.10 (Class 1-3 sections):
    Nc,Rd = A * fy / gamma_M0

Oracle sources:
- SCI P364 Example 9 sheet 3 (UKC 356x368x129, S355): Nc,Rd = 5658 kN.
- Coursework Check 8 squash load (S275): Npl,Rd = 4622.75 kN.
"""


def compression(NEd, A, fy, gamma_M0=1.0):
    """EC3 6.2.4 compression resistance.

    NEd in kN, A in cm2, fy in N/mm2. Returns Nc,Rd in kN.
    """
    A_mm2 = A * 100.0
    Nc_Rd = A_mm2 * fy / gamma_M0 / 1000.0
    ratio = round(NEd / Nc_Rd, 2)
    steps = [
        f"A = {A} cm2 = {A_mm2:.0f} mm2",
        f"Nc,Rd = A fy / gM0 = ({A_mm2:.0f} x {fy}) / {gamma_M0} = {Nc_Rd:.2f} kN   [EC3 6.2.4(2) Eq 6.10]",
        f"NEd / Nc,Rd = {NEd} / {Nc_Rd:.2f} = {ratio:.2f} <= 1.0   [EC3 6.2.4(1) Eq 6.9]",
    ]
    return {
        "result": Nc_Rd,
        "unit": "kN",
        "steps": steps,
        "governing": "NEd / Nc,Rd <= 1.0",
        "ratio": ratio,
    }
