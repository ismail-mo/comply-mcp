# Compliance Audit Skill

## When to use
The user asks for a full compliance check, audit, or sweep — phrases like
"audit the design report against Eurocode", "check all values for compliance",
"run a full flag check". This is the headline workflow.

## What this skill does
Performs a structured audit by extracting every quantitative claim from the
design report, retrieving the matching Eurocode clause for each, comparing
the two, and writing a single .txt audit report to /audits.

## Tool sequence (mandatory order)
1. `extract_design_values`       — pulls every numeric design claim from the report
2. For each value returned: `retrieve_code_clauses`  — fetches the relevant
   Eurocode clause(s) that govern that value
3. For each pair: `compare_value_to_clause`  — runs the pass/fail comparison
4. `write_audit_report`          — writes all results to /audits/audit-<timestamp>.txt

## Output contract
A single .txt file. Each finding follows this exact format:

    [PASS/FAIL/REVIEW] — <check name>
       Design value:     <value> <unit>          (source: <doc>, p.<page>)
       Code requirement: <value> <unit>          (source: <code>, clause <X.Y.Z>)
       Delta:            <signed delta> <unit>
       Verdict:          <one-line engineering interpretation>

## Critical rules
- NEVER fabricate clause numbers. If retrieve_code_clauses returns nothing,
  output [REVIEW] — manual check required, do not invent a clause.
- Always cite the exact page number and clause. Engineers need an audit trail.
- If a design value has no matching clause, flag as [REVIEW], never [PASS].
- Group findings by element type (beams, columns, connections, slabs).
