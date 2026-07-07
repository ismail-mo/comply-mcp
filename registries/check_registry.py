"""The check registry — static DATA read by run_audit(). Never called by the LLM.

This is what deterministically produces MISSING rows: the engine loops over
the complete required set for an element type and anything whose inputs are
absent becomes a MISSING (or the check's declared missing_status) finding.

Field notes:
  formula        key into formulas.FORMULAS, or None for engine-builtin checks
                 (qualitative / material checks that are not resistance formulas)
  kind           resistance      -> ratio = demand / result
                 demand_vs_limit -> ratio = result / limit value (e.g. deflection)
                 recompute       -> engine recomputes the value and compares to the
                                    engineer's stated figure (PASS / ERROR)
                 qualitative     -> no number can satisfy it -> WARNING
                 material        -> fy vs EN 10025-2 band -> PASS / ERROR / ASSUMED
  inputs         names gathered from section properties (authoritative) first,
                 then from the AI-extracted values; extracted-only names drive
                 MISSING when absent
  demand_key     the extracted action effect compared against the resistance
"""

CHECK_REGISTRY = {
    "column": [
        {
            "id": "load_combo", "name": "Load combinations",
            "clause": "EN 1990, Section A1.3", "formula": "load_combo",
            "kind": "recompute", "inputs": ["Gk", "Qk"],
            "engineer_key": "NEd",
            "limit": "1.35Gk + 1.50Qk", "missing_status": "MISSING",
            "category_sub": "Structural . ULS",
            "capacity_symbol": "NEd", "unit": "kN",
            "action_fix": "Reapply the ULS combination with gamma_G = 1.35 and gamma_Q = 1.50 per EN 1990, Section A1.3, then carry the corrected axial load through all downstream checks.",
        },
        {
            "id": "compression", "name": "Column compression",
            "clause": "Eurocode 3, Section 6.2.4", "formula": "compression",
            "kind": "resistance", "inputs": ["NEd", "A", "fy"],
            "demand_key": "NEd", "demand_symbol": "NEd",
            "capacity_symbol": "Nc,Rd", "unit": "kN",
            "limit": "NEd / Nc,Rd <= 1.0", "missing_status": "MISSING",
            "category_sub": "Structural . resistance",
            "action_fix": "Upsize the section or reduce the axial load until NEd / Nc,Rd <= 1.0 per Eurocode 3, Section 6.2.4.",
        },
        {
            "id": "flex_buckling", "name": "Column buckling",
            "clause": "Eurocode 3, Section 6.3.1", "formula": "flexural_buckling",
            "kind": "resistance",
            "inputs": ["NEd", "A", "iz", "Le", "fy", "section_type", "axis"],
            "demand_key": "NEd", "demand_symbol": "NEd",
            "capacity_symbol": "Nb,Rd", "unit": "kN",
            "limit": "NEd / Nb,Rd <= 1.0", "missing_status": "MISSING",
            "category_sub": "Structural . ULS",
            "action_fix": "Upsize the column section to raise the radius of gyration and reduce slenderness, then recheck chi and Nb,Rd per Eurocode 3, Section 6.3.1.",
        },
        {
            "id": "shear", "name": "Column shear",
            "clause": "Eurocode 3, Section 6.2.6", "formula": "shear",
            "kind": "resistance",
            "inputs": ["VEd", "A", "b", "tf", "tw", "r", "hw", "fy"],
            "demand_key": "VEd", "demand_symbol": "VEd",
            "capacity_symbol": "Vpl,Rd", "unit": "kN",
            "limit": "VEd / Vpl,Rd <= 1.0", "missing_status": "MISSING",
            "category_sub": "Structural . ULS",
            "action_fix": "Compute the design shear force and verify VEd / Vpl,Rd <= 1.0 per Eurocode 3, Section 6.2.6.",
        },
        {
            "id": "section_class", "name": "Cross-section class",
            "clause": "Eurocode 3, Section 5.5", "formula": None,
            "kind": "qualitative", "inputs": ["tf", "tw", "fy"],
            "limit": "qualitative", "missing_status": "WARNING",
            "category_sub": "Structural . classification",
            "capacity_symbol": "c/t", "unit": "",
            "action_fix": "Calculate the c/t ratios for flange and web and verify the claimed class against Eurocode 3, Section 5.5, Table 5.2 before relying on plastic resistance.",
        },
        {
            "id": "steel_grade", "name": "Steel grade",
            "clause": "EN 10025-2", "formula": None,
            "kind": "material", "inputs": ["grade", "tf", "fy"],
            "limit": "fy per EN 10025-2 thickness band", "missing_status": "ASSUMED",
            "category_sub": "Structural . material",
            "capacity_symbol": "fy", "unit": "N/mm2",
            "action_fix": "Confirm the steel grade on the section order and take fy from the EN 10025-2 thickness band for the actual flange thickness.",
        },
    ],
    "beam": [
        {
            "id": "load_combo", "name": "Load combinations",
            "clause": "EN 1990, Section A1.3", "formula": "load_combo",
            "kind": "recompute", "inputs": ["Gk", "Qk"],
            "engineer_key": "MEd",
            "limit": "1.35Gk + 1.50Qk", "missing_status": "MISSING",
            "category_sub": "Structural . ULS",
            "capacity_symbol": "Ed", "unit": "kN",
            "action_fix": "Reapply the ULS combination with gamma_G = 1.35 and gamma_Q = 1.50 per EN 1990, Section A1.3.",
        },
        {
            "id": "bending", "name": "Bending resistance",
            "clause": "Eurocode 3, Section 6.2.5", "formula": "bending",
            "kind": "resistance", "inputs": ["MEd", "Wpl_y", "fy"],
            "demand_key": "MEd", "demand_symbol": "MEd",
            "capacity_symbol": "Mc,Rd", "unit": "kNm",
            "limit": "MEd / Mc,Rd <= 1.0", "missing_status": "MISSING",
            "category_sub": "Structural . ULS",
            "action_fix": "Upsize the section or reduce the span moment until MEd / Mc,Rd <= 1.0 per Eurocode 3, Section 6.2.5.",
        },
        {
            "id": "shear", "name": "Shear resistance",
            "clause": "Eurocode 3, Section 6.2.6", "formula": "shear",
            "kind": "resistance",
            "inputs": ["VEd", "A", "b", "tf", "tw", "r", "hw", "fy"],
            "demand_key": "VEd", "demand_symbol": "VEd",
            "capacity_symbol": "Vpl,Rd", "unit": "kN",
            "limit": "VEd / Vpl,Rd <= 1.0", "missing_status": "MISSING",
            "category_sub": "Structural . ULS",
            "action_fix": "Verify VEd / Vpl,Rd <= 1.0 per Eurocode 3, Section 6.2.6.",
        },
        {
            "id": "ltb", "name": "Lateral torsional buckling",
            "clause": "Eurocode 3, Section 6.3.2", "formula": "ltb",
            "kind": "resistance",
            "inputs": ["MEd", "Wpl_y", "fy", "Mcr", "h", "b"],
            "demand_key": "MEd", "demand_symbol": "MEd",
            "capacity_symbol": "Mb,Rd", "unit": "kNm",
            "limit": "MEd / Mb,Rd <= 1.0", "missing_status": "MISSING",
            "category_sub": "Structural . ULS",
            "action_fix": "Verify the buckling moment resistance with lambda_LT, chi_LT and Mb,Rd per Eurocode 3, Section 6.3.2, or provide lateral restraint.",
        },
        {
            "id": "deflection", "name": "Deflection",
            "clause": "Eurocode 3, Section 7.2.1", "formula": "deflection",
            "kind": "demand_vs_limit", "inputs": ["q", "P", "L", "Iy"],
            "capacity_symbol": "w", "unit": "mm",
            "limit": "w <= L/360", "missing_status": "MISSING",
            "category_sub": "Structural . SLS",
            "action_fix": "Perform the SLS deflection check under variable actions and verify w <= L/360 per Eurocode 3, Section 7.2.1.",
        },
        {
            "id": "section_class", "name": "Cross-section class",
            "clause": "Eurocode 3, Section 5.5", "formula": None,
            "kind": "qualitative", "inputs": ["tf", "tw", "fy"],
            "limit": "qualitative", "missing_status": "WARNING",
            "category_sub": "Structural . classification",
            "capacity_symbol": "c/t", "unit": "",
            "action_fix": "Calculate the c/t ratios and confirm the section class against Eurocode 3, Section 5.5, Table 5.2.",
        },
        {
            "id": "steel_grade", "name": "Steel grade",
            "clause": "EN 10025-2", "formula": None,
            "kind": "material", "inputs": ["grade", "tf", "fy"],
            "limit": "fy per EN 10025-2 thickness band", "missing_status": "ASSUMED",
            "category_sub": "Structural . material",
            "capacity_symbol": "fy", "unit": "N/mm2",
            "action_fix": "Confirm the steel grade against the section order and the EN 10025-2 thickness band.",
        },
    ],
}
