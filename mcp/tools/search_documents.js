import { embedQuery, vectorSearch } from "../lib/firebase.js";

export const search_documents = {
  name: "search_documents",
  description: `Free-form semantic search across design_chunks or code_chunks (or both).
    Use for code lookups or open questions not covered by the audit workflow.`,
  inputSchema: {
    type: "object",
    properties: {
      query: {
        type: "string",
        description: "Natural language search query",
      },
      source_filter: {
        type: "string",
        description: "'design' to search only design reports, 'eurocode' for code only, omit for both",
      },
      top_k: {
        type: "number",
        description: "Number of results to return. Default 5.",
      },
    },
    required: ["query"],
  },

  handler: async ({ query, source_filter, top_k = 5 }) => {
    const queryEmbed = await embedQuery(query);

    let collections = ["design_chunks", "code_chunks"];
    if (source_filter === "design") collections = ["design_chunks"];
    if (source_filter === "eurocode") collections = ["code_chunks"];

    const allResults = [];
    for (const col of collections) {
      const chunks = await vectorSearch(col, queryEmbed, top_k);
      allResults.push(...chunks.map((c) => ({ ...c, collection: col })));
    }

    return {
      query,
      results: allResults.map((c) => ({
        collection: c.collection,
        source: c.source,
        page: c.page ?? null,
        clause_number: c.clause_number ?? null,
        text: c.text,
      })),
    };
  },
};
