"""Engine tests — the golden Check-8 audit.

The fixture reproduces the spec Part 2.1 extraction example (coursework
Check 8: UC 254x254x132, S275). The engine computes CODE-CORRECT values from
the authoritative tables; where the report's figures differ (its Nb,Rd was
derived with buckling curve b and lambda_1 without epsilon; its fy ignores
the EN 10025-2 thickness band) the engine flags ERROR — that is the product
working as designed.

Golden snapshot: tests/golden/check8.json. Regenerate ONLY deliberately:
    REGEN_GOLDEN=1 backend/venv/bin/python -m pytest tests/test_engine.py -q
"""

import json
import os
from pathlib import Path

from engine.run_audit import run_audit, summarize
from engine.cross_reference import cross_reference
from tables.section_properties import get_section

GOLDEN = Path(__file__).parent / "golden" / "check8.json"

CHECK8_EXTRACT = {
    "element": "column",
    "designation": "UC 254x254x132",
    "document": "column_check_8.pdf",
    "values": {
        "NEd": {"value": 6896.25, "unit": "kN", "page": 15,
                "quote": "Total Axial Load = 6896.25", "confidence": 0.98,
                "flag": None},
        "Le": {"value": 3.22, "unit": "m", "page": 9,
               "quote": "Le = 0.7 x 4.6 = 3.22 m", "confidence": 0.96,
               "flag": "ASSUMED",
               "note": "effective length assumed fixed-pinned"},
        "fy": {"value": 275, "unit": "N/mm2", "page": 8,
               "quote": "grade S275", "confidence": 0.72, "flag": "ASSUMED",
               "note": "grade stated, thickness band not verified"},
        "grade": {"value": "S275", "unit": "", "page": 8,
                  "quote": "grade S275", "confidence": 0.72, "flag": "ASSUMED"},
        "section_class": {"value": 1, "unit": "", "page": 8,
                          "quote": "Class 1 steel", "confidence": 0.9,
                          "flag": None},
        "flex_buckling_result": {"value": 4059.17, "unit": "kN", "page": 10,
                                 "quote": "Nb,Rd = 0.878 x 4622.75 = 4059.17 kN",
                                 "confidence": 0.97, "flag": None},
    },
    "not_found": ["VEd", "Gk", "Qk"],
}


def _audit():
    props = get_section("UC 254x254x132")
    assert props is not None
    return run_audit("column", CHECK8_EXTRACT, props)


def test_check8_statuses():
    findings = _audit()
    by_id = {f["check_id"]: f for f in findings}
    assert by_id["compression"]["status"] == "FAIL"
    assert by_id["flex_buckling"]["status"] == "ERROR"
    assert by_id["steel_grade"]["status"] == "ERROR"
    assert by_id["section_class"]["status"] == "WARNING"
    assert by_id["load_combo"]["status"] == "MISSING"
    assert by_id["shear"]["status"] == "MISSING"
    # severity ordering: FAIL -> ERROR -> MISSING -> ... -> WARNING last-ish
    statuses = [f["status"] for f in findings]
    assert statuses == sorted(statuses, key=["FAIL", "ERROR", "CONFLICT",
                                             "MISSING", "ASSUMED", "WARNING",
                                             "PASS"].index)


def test_check8_numbers():
    findings = _audit()
    by_id = {f["check_id"]: f for f in findings}
    comp = by_id["compression"]["metrics"]
    assert abs(comp["capacity"] - 4620.0) < 1.0        # A=168 (P363) x 275
    assert comp["ratio"] == 1.49
    buck = by_id["flex_buckling"]["metrics"]
    assert abs(buck["computed"] - 3751.5) < 2.0        # engine-correct, curve c
    assert buck["engineer"] == 4059.17                 # report's figure
    assert abs(buck["discrepancy_pct"] - 8.2) < 0.3
    grade = by_id["steel_grade"]["metrics"]
    assert grade["correct_fy"] == 265.0                # S275, tf=25.3 (16<t<=40)
    assert grade["claimed_fy"] == 275


def test_check8_calc_blocks_have_sources():
    findings = _audit()
    buck = next(f for f in findings if f["check_id"] == "flex_buckling")
    lines = "\n".join(buck["calc"]["lines"])
    assert "Steel Blue Book" in lines                  # authoritative props cited
    assert "column_check_8.pdf" in lines               # extracted values cited
    assert "Result" in lines and "Formula" in lines


def test_summary_counts():
    counts = summarize(_audit())
    assert counts == {"FAIL": 1, "ERROR": 2, "MISSING": 2, "WARNING": 1}


def test_fy_fallback_from_grade():
    """No numeric fy in the document, but grade + Blue Book tf determine it
    deterministically via EN 10025-2 — bending must compute, not go MISSING."""
    extract = {
        "element": "beam", "designation": "UB 610x178x100",
        "document": "doc.pdf",
        "values": {
            "MEd": {"value": 812.1, "unit": "kNm", "page": 13,
                    "quote": "maximum bending moment equal to 812.1kNm",
                    "confidence": 0.95, "flag": None},
            "grade": {"value": "S355", "unit": "", "page": 13,
                      "quote": "Class 1 steel of grade S355",
                      "confidence": 0.9, "flag": None},
        },
        "not_found": ["fy", "VEd", "Gk", "Qk", "q", "P", "L", "Mcr", "C1"],
    }
    props = get_section("UB 610x178x100")
    findings = run_audit("beam", extract, props)
    bending = next(f for f in findings if f["check_id"] == "bending")
    assert bending["status"] == "PASS"          # 812.1 / (2790e3*345/1e6=962.55) = 0.84
    assert abs(bending["metrics"]["capacity"] - 962.6) < 1.0
    lines = "\n".join(bending["calc"]["lines"])
    assert "EN 10025-2" in lines                # fy provenance cited


def test_cross_reference_conflict():
    a = {"values": {"grade": {"value": "S275", "page": 8}}}
    b = {"values": {"grade": {"value": "S355", "page": 2}}}
    out = cross_reference({"column": a, "beam": b})
    assert len(out) == 1 and out[0]["status"] == "CONFLICT"
    assert "S275" in out[0]["issue"] and "S355" in out[0]["issue"]


def test_golden_snapshot():
    findings = _audit()
    payload = {"findings": findings, "summary": summarize(findings)}
    if os.environ.get("REGEN_GOLDEN") == "1" or not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(payload, indent=2, sort_keys=True))
    expected = json.loads(GOLDEN.read_text())
    assert json.loads(json.dumps(payload, sort_keys=True)) == expected
