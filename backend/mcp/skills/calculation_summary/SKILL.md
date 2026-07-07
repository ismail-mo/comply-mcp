# Calculation Summary Skill

A **format contract** for the collapsible working appended to every audit.

## Trigger
Automatically appended at the end of compliance_audit output. Never triggered
directly by a user prompt.

## Input contract
Everything is already computed by the deterministic engine and travels inside
each finding's `calc` block: input values (with units, source page or Steel
Blue Book citation), every intermediate formula step with actual numbers, and
the result line with the ratio and the limit.

## Output contract
One collapsible block per computed check. Closed by default.
Label: "<Check name> — Calculation summary — N lines".
Expanded view: bordered monospace block with three sections:

    Input values
    ------------------------------------------
    NEd     = 6,896.25 kN   > document.pdf . p.15
    A       = 168 cm2       > Steel Blue Book . SCI P363 pp.74-75

    Formula — Eurocode 3, Section 6.3.1
    <engine steps verbatim — never paraphrase or simplify>

    Result
    NEd / Nb,Rd = 6,896.25 / 3,751.5 = 1.84 > 1.0   [FAIL]

## Rules
- One block per check that ran a formula; order matches the findings table.
- All values include units; all document references include the page.
- Formula steps match the engine output exactly.
- Section property values cite the Steel Blue Book, not the design PDF.
