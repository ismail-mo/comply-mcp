# Compliance Audit Skill

## When To Use
Triggered when the engineer clicks a compliance check button:
Check EC1 Compliance, Check EC3 Compliance, Check Client Reqs,
Summarise Risks, or What's Missing.

This skill is for structured compliance audit responses only.
Never use it for general conversation or normal typed questions.

## Trigger
The frontend injects a hidden `[COMPLIANCE_AUDIT]` prefix when a chip is
clicked. The prefix is never shown to the engineer. The engineer sees only
the chip label they clicked.

## Tool Sequence
Always call tools in this exact order. Never skip a step.

1. `extract_design_values`
   Extract all design parameters from PROJECT document chunks. Call with
   `file_id` set to the uploaded PROJECT document file_id.

2. `retrieve_code_clauses`
   Retrieve matching clauses from Firestore for each extracted parameter and
   the relevant standard.

3. `compare_value_to_clause`
   Compare each extracted value against its retrieved clause requirement.

4. `write_audit_report`
   Only call this if the engineer explicitly requests a downloadable or saved
   report. Never call it automatically for a compliance chip.

## Response Format
Return exactly two parts. No exceptions.

PART 1 - SUMMARY:
A narrative paragraph of 150 words maximum. Every factual claim must include
a `[n]` citation marker. Citation `[n]` maps to row `n` in the table below.
State document count and overall compliance status first.

PART 2 - TABLE:
A JSON array wrapped in `<table></table>` tags. One object per finding.
The frontend renders the JSON as this visible table:

```text
Status | Category | Issue | Reference | Clause | Party | Action
```

Full column names:

```text
Status   — FAIL / WARN / PASS verdict
Category — engineering domain e.g. "Foundation Design", "Slope Stability"
Issue    — plain language description of what is wrong
Reference — verbatim excerpt from the source document with PROJECT badge 🔵
Clause   — standard clause number e.g. "EC3 §6.2.6" with STANDARD badge 🟣
Party    — who owns the issue e.g. "Design Engineer", "Contractor"
Action   — specific technical recommendation
```

Return these JSON fields exactly:

```text
status: "FAIL" | "WARN" | "PASS"
category: string
issue: string
reference_text: verbatim excerpt from PROJECT document
source_page: integer or null
highlight_start: first 5 words of reference_text
highlight_end: last 5 words of reference_text
project_file_id: file_id of PROJECT document
standard_clause: e.g. "EC3 §6.2.6"
standard_page: integer or null
standard_text: verbatim excerpt from Firestore chunk
standard_file_id: file_id of uploaded STANDARD document
party_affected: string
recommendation: string
```

Column mapping:

```text
Status    = status
Category  = category
Issue     = issue
Reference = reference_text + PROJECT badge when project_file_id/source_page/highlights exist
Clause    = standard_clause + STANDARD badge when standard_file_id/standard_page/standard_text exist
Party     = party_affected
Action    = recommendation
```

## Critical Rules
- Row order: FAIL first, WARN second, PASS last.
- Never return a row without `reference_text`.
- Never guess page numbers. Use null if unknown.
- Never fabricate clause numbers or standard text.
- Use `project_chunks` via MCP tools for PROJECT evidence; do not rely on
  large PROJECT text being injected into chat history.
- If extra PROJECT context is needed, call `search_documents` with
  `source_filter="project"` and the relevant `file_id`.
- Do not include markdown fences inside `<table>` tags.
