# Single Value Check Skill

## When to use
User asks about one specific value — "is the beam size compliant?",
"check the column axial load", "is the slope of pipe 34 ok?".
Faster path than the full audit.

## Tool sequence
1. `retrieve_code_clauses`       — get the clause for the asked-about parameter
2. `extract_design_values`       — get the matching design value (filter by parameter)
3. `compare_value_to_clause`     — pass/fail
4. `write_audit_report`          — append to /audits/single-checks.txt (mode: "append")

## Output
One block in the standard format, appended to single-checks.txt.
