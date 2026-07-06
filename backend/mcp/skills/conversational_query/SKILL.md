# Conversational Query Skill

## When To Use
Triggered for all messages that are not compliance audit chip clicks.
This includes normal engineer questions, follow-ups, clarifications, general
queries about documents, and requests for explanation.

## Trigger
Any message that does not have the hidden `[COMPLIANCE_AUDIT]` prefix.

## Tool Usage
Tools are optional. Use them only when genuinely needed for accuracy.

Examples:
- "What does EC3 6.2.6 say?" can call `retrieve_code_clauses`.
- "What was the FoS in my report?" can call `search_documents` with
  `source_filter="project"` and the relevant uploaded PROJECT `file_id`.

Never force the compliance audit tool sequence for conversational responses.

## Response Format
Plain conversational text only.

Do not output:
- `<table>` tags
- JSON
- `[n]` citation markers
- citation badge references

Answer directly and concisely using appropriate engineering terminology.
