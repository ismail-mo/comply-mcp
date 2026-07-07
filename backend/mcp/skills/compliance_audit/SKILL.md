# Compliance Audit Skill

A **format contract** — it shapes what the model outputs. It does not
orchestrate, fire tools, run in parallel, or monitor anything; that logic
lives in the backend pipeline (`backend/main.py`, Stages 0–7).

## Trigger
A request to check, audit, or flag compliance on a structural element:
"check the column", "run a beam check", "audit the primary beam against
Eurocode 3", "flag all violations", or any chip message carrying the
`[COMPLIANCE_AUDIT]` prefix.

## Output structure (in order, always)
1. Title block — "Column compliance check", document . designation subtitle
2. Summary pills — one coloured pill per status with a count
3. Overview — one full-sentence paragraph (see `write_overview` contract in
   `backend/mcp/server.py`: S1 what was checked … S8 soft close; no em
   dashes; counts as words; values as digits; code references in full)
4. Recommended actions — 2–4 arrow bullets, **bold verb + subject** — values
5. Findings table — 5 columns: STATUS . CATEGORY . ISSUE . REFERENCE . ACTION,
   rows ordered FAIL → ERROR → CONFLICT → MISSING → ASSUMED → WARNING → PASS
6. Calculation summary — collapsible blocks appended per computed check

## Who produces what
- Findings, statuses, ratios, calc steps: the **deterministic engine**
  (`engine/run_audit.py`) — the AI never computes or re-judges them.
- Overview + recommended actions prose: the `write_overview` tool (AI call #2),
  narration only.

## Does NOT
- Orchestrate tools. The backend runs the engine and the two AI calls.
  This skill governs the FORMAT of the final rendered output only.
