"""Section properties — pure DATA, transcribed from SCI P363 (the Blue Book).

Numeric section properties are physical facts (not copyrightable); the
source PDF itself lives gitignored in reference/. Each entry cites where
the numbers were read. Units: mm for dimensions; cm-based section
constants exactly as the Blue Book publishes them (A cm2, I cm4, i cm,
W cm3, Iw dm6, IT cm4).

AUTHORITATIVE RULE (spec Part 5.3): section properties come from here,
never from the design PDF under audit.
"""

E_MODULUS = 210_000.0  # N/mm2 — BS EN 1993-1-1 3.2.6(1)
G_MODULUS = 81_000.0   # N/mm2 — BS EN 1993-1-1 3.2.6(1)

SBB_URL = "https://www.steelforlifebluebook.co.uk/"

SECTION_PROPERTIES = {
    # P363 pp. 74-75 (UKC dimensions + properties rows, read from the PDF)
    "UC 254x254x132": {
        "family": "UC", "h": 276.3, "b": 261.3, "tw": 15.3, "tf": 25.3,
        "r": 12.7, "d": 200.3, "A": 168.0, "Iy": 22500.0, "Iz": 7530.0,
        "iy": 11.6, "iz": 6.69, "Wel_y": 1630.0, "Wpl_y": 1870.0,
        "Wel_z": 576.0, "Wpl_z": 878.0, "IT": 319.0, "Iw": 1.19,
        "source": "SCI P363 pp.74-75",
    },
    # P364 Example 9 sheet 2 (values printed there, cited to P363)
    "UC 356x368x129": {
        "family": "UC", "h": 355.6, "b": 368.6, "tw": 10.4, "tf": 17.5,
        "r": 15.2, "d": 290.2, "A": 164.0, "iy": 15.6, "iz": 9.43,
        "IT": 153.0, "Iw": 4.18,
        "source": "SCI P364 Ex 9 sheet 2 (P363)",
    },
    # P364 Example 2 sheet 3 (values printed there, cited to P363)
    "UB 533x210x92": {
        "family": "UB", "h": 533.1, "b": 209.3, "tw": 10.1, "tf": 15.6,
        "r": 12.7, "d": 476.5, "A": 117.0, "Iy": 55200.0, "Wpl_y": 2360.0,
        "source": "SCI P364 Ex 2 sheet 3 (P363)",
    },
    # P363 pp.68-69 (UKB dimensions + properties rows, read from the PDF)
    "UB 610x178x100": {
        "family": "UB", "h": 607.4, "b": 179.2, "tw": 11.3, "tf": 17.2,
        "r": 12.7, "d": 547.6, "A": 128.0, "Iy": 72500.0, "Iz": 1660.0,
        "iy": 23.8, "iz": 3.60, "Wel_y": 2390.0, "Wpl_y": 2790.0,
        "Wel_z": 185.0, "Wpl_z": 296.0, "IT": 95.0, "Iw": 1.44,
        "source": "SCI P363 pp.68-69",
    },
    # P364 Example 3 sheet 3 (values printed there, cited to P363).
    # r = 10.2 is not on sheet 3's property list; it appears in the sheet 4/5
    # arithmetic ("189.9 - 8.5 - 2x10.2", Av term "(2x10.2)") and matches P363.
    "UB 457x191x67": {
        "family": "UB", "h": 453.4, "b": 189.9, "tw": 8.5, "tf": 12.7,
        "r": 10.2, "d": 407.6, "A": 85.5, "Wpl_y": 1470.0,
        "source": "SCI P364 Ex 3 sheets 3-5 (P363)",
    },
}


def normalize_designation(raw: str) -> str:
    """'UC254X254X132' / '610 x 178 x 100 UB' / 'UKB 457x191x67' -> canonical key."""
    s = raw.upper().replace("×", "X").replace(" ", "")
    s = s.replace("UKC", "UC").replace("UKB", "UB")
    import re
    m = re.search(r"(UC|UB)?(\d{3})X(\d{2,3})X(\d{2,3})(UC|UB)?", s)
    if not m:
        return raw.strip()
    fam = m.group(1) or m.group(5) or ""
    return f"{fam} {m.group(2)}x{m.group(3)}x{m.group(4)}".strip()


def get_section(designation: str) -> dict | None:
    return SECTION_PROPERTIES.get(normalize_designation(designation))
