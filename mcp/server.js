import { config } from "dotenv";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
config({ path: join(dirname(fileURLToPath(import.meta.url)), "../.env") });
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import { extract_design_values } from "./tools/extract_design_values.js";
import { retrieve_code_clauses } from "./tools/retrieve_code_clauses.js";
import { compare_value_to_clause } from "./tools/compare_value_to_clause.js";
import { search_documents } from "./tools/search_documents.js";
import { write_audit_report } from "./tools/write_audit_report.js";

const tools = [
  extract_design_values,
  retrieve_code_clauses,
  compare_value_to_clause,
  search_documents,
  write_audit_report,
];

const server = new Server(
  { name: "vc-compliance-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: tools.map((t) => ({
    name: t.name,
    description: t.description,
    inputSchema: t.inputSchema,
  })),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const tool = tools.find((t) => t.name === request.params.name);
  if (!tool) throw new Error(`Unknown tool: ${request.params.name}`);
  const result = await tool.handler(request.params.arguments ?? {});
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("vc-compliance-mcp ready — 5 tools loaded");
