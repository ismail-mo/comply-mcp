# COMPLY — MCP Server

An AI-powered engineering compliance checker built as an MCP server for Claude Desktop.

Give Claude a structural design report and ask it to audit it against Eurocode standards.
Claude will extract design values, look up the relevant clauses, compare them, and produce
a structured pass/fail audit report.

---

## What it does

- **Extracts** every numeric design claim from an uploaded report
- **Retrieves** the matching Eurocode 1 and Eurocode 3 clauses from a vector database
- **Compares** design values against code requirements and gives a PASS / FAIL / REVIEW verdict
- **Writes** a structured audit report to `/audits/`

---

## Prerequisites

Make sure you have these installed before starting:

- [Node.js](https://nodejs.org/) v18 or higher — check with `node --version`
- [Claude Desktop](https://claude.ai/download) — the app, not the browser

---

## Setup

### 1. Clone the repo

```bash
git clone <repo-url>
cd mcp-server
```

### 2. Install dependencies

```bash
npm install
```

### 3. Add your credentials

You need two things from the project owner — ask them to send these privately:

- `firebase-key.json` — drop this file in the root of `mcp-server/`
- The values for your `.env` file (see next step)

### 4. Set up your `.env`

Copy the example file:

```bash
cp .env.example .env
```

Then open `.env` and fill in the values the project owner sent you:

```
ANTHROPIC_API_KEY=...
FIREBASE_PROJECT_ID=...
GOOGLE_API_KEY=...
```

> The Firestore database is already populated with Eurocode 1, Eurocode 3, and the
> sample design documents — you do not need to run any embedding scripts.

### 5. Connect to Claude Desktop

Claude Desktop needs to know where your MCP server is. Open its config file:

- **Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add this block (replace the path with your actual absolute path):

```json
{
  "mcpServers": {
    "vc-compliance-mcp": {
      "command": "node",
      "args": ["/absolute/path/to/mcp-server/mcp/server.js"]
    }
  }
}
```

To find your absolute path, run this in the `mcp-server` folder:

```bash
# Mac / Linux
pwd

# Windows
cd
```

Then append `/mcp/server.js` to the result.

### 6. Restart Claude Desktop

Fully quit and reopen Claude Desktop. You should see a hammer icon (🔨) in the chat input —
that means the MCP tools loaded successfully.

---

## How to use it

Paste or describe your design report in Claude Desktop, then try prompts like:

- *"Audit this design report against Eurocode"*
- *"Check all beam values for compliance"*
- *"What does Eurocode 3 say about lateral torsional buckling?"*
- *"Run a full compliance sweep and write the audit report"*

Audit reports are saved as `.txt` files in the `/audits/` folder.

---

## Project structure

```
mcp-server/
├── mcp/
│   ├── server.js          # MCP server entry point
│   ├── lib/
│   │   └── firebase.js    # Firestore connection + vector search
│   ├── tools/             # Individual MCP tool handlers
│   │   ├── extract_design_values.js
│   │   ├── retrieve_code_clauses.js
│   │   ├── compare_value_to_clause.js
│   │   ├── search_documents.js
│   │   └── write_audit_report.js
│   └── skills/            # Prompt guides for Claude workflows
├── embed/                 # Scripts used to populate the database (already done)
├── docs/                  # Source PDFs (Eurocode 1, Eurocode 3, design reports)
└── audits/                # Generated audit reports appear here
```

---

## Troubleshooting

**Hammer icon not showing in Claude Desktop**
- Check the path in `claude_desktop_config.json` is the full absolute path
- Make sure `node` is on your PATH: `node --version`
- Fully quit Claude Desktop (not just close the window) and reopen

**"Cannot find module" error**
- Run `npm install` again in the `mcp-server/` folder

**Firestore / auth errors**
- Check `firebase-key.json` is in the root of `mcp-server/` (not inside a subfolder)
- Check `FIREBASE_PROJECT_ID` in your `.env` matches what the project owner gave you
