# Quick Answer Skill

A **format contract** for direct questions, not compliance-check requests.

## Trigger
A direct question about a value, section, clause, or fix: "what is a better
section size", "what does clause 6.3.1 say", "why did the column fail",
"what is chi", "how do I fix the buckling check".

## Output rules
- Flowing professional prose, full sentences, full words — the overview voice,
  BUT including quantities and aimed at suggesting actions.
- NOT five short clipped sentences; two long comma-separated sentences is the
  target shape when suggesting a fix, quantifying the improvement (areas,
  radii of gyration, slenderness, chi, resistances).
- Include the specific value or answer, with units.
- Cite the clause in full when relevant ("Eurocode 3, Section 6.3.1"); the
  clickable clause badge MAY surface on isolated questions (the backend emits
  `quick_refs` with clause/source/page from `search_documents`).
- No table, no overview block, no title block, no summary pills, NO em dashes.
- If the answer genuinely requires a fresh check to be run, say so and point
  at the compliance audit instead of guessing.

## Pipeline (backend-owned)
`search_documents` (retrieval over code_chunks) → one streamed prose call with
the excerpts as grounding. This is the only feature that touches the vector
store.
