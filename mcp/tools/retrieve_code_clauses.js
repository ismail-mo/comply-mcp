import { embedQuery, vectorSearch } from "../lib/firebase.js";

export const retrieve_code_clauses = {
  name: "retrieve_code_clauses",
  description: `Given an engineering parameter, retrieve the relevant Eurocode clauses that govern it.
    Returns clause text, clause number, code reference, and page.
    Use before compare_value_to_clause.`,
  inputSchema: {
    type: "object",
    properties: {
      parameter: {
        type: "string",
        description: "e.g. 'minimum slope', 'lateral torsional buckling', 'shear resistance'",
      },
      element_type: {
        type: "string",
        description: "Optional: beam, column, slab, etc.",
      },
      code: {
        type: "string",
        description: "Optional: 'eurocode1' or 'eurocode3' to restrict to one code",
      },
    },
    required: ["parameter"],
  },

  handler: async ({ parameter, element_type, code }) => {
    const query = `${parameter} ${element_type || ""} requirement minimum maximum limit`.trim();
    const queryEmbed = await embedQuery(query);
    const chunks = await vectorSearch("code_chunks", queryEmbed, 8);

    const filtered = code
      ? chunks.filter((c) => (c.source || "").toLowerCase().includes(code.toLowerCase()))
      : chunks;

    return {
      parameter,
      clauses: filtered.map((c) => ({
        clause_text: c.text,
        clause_number: c.clause_number ?? "see source",
        code: c.source,
        page: c.page ?? null,
      })),
    };
  },
};
