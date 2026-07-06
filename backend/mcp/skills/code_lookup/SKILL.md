# Code Lookup Skill

## When to use
User wants to read or understand a Eurocode requirement without comparing to
their design. "What does Eurocode 3 say about lateral torsional buckling?",
"Show me the ULS load combination clause."

## Tool sequence
1. `search_documents` with source_filter = "eurocode"
2. Return the most relevant clause text directly to the user
3. Do NOT write to /audits — this is a read-only lookup
