# COMPLY — Current Active Step
Last updated: [date]
Status: ACTIVE

## Current Step: Step 12 — Chat Sidebar Rendering

## Overview
The rendering fix is the blocker for everything else. Citations can't be tested until the table renders correctly, and the table can't render correctly until the raw JSON is stripped.

---

## Stage 1 — Strip <table> tags from display
Add getSummaryText helper to ChatSidebar.tsx. Apply to all message.content renders in both streaming and settled states. Confirm no raw JSON visible in chat.

Pass condition: clean summary text only, no <table> block visible anywhere.

Status: [ ] pending

---

## Stage 2 — Verify message.table is being attached
In browser devtools console, log messages state after a compliance response. Confirm the last assistant message has table: [...] populated not null. If null — the onTable callback in useChat.ts is not firing or not finding the last assistant message.

Pass condition: message.table is a populated array on the assistant message.

Status: [ ] pending

---

## Stage 3 — Render summary with inline [n] badges
Confirm SummaryText component parses [n] markers and renders blue PROJECT citation badges inline. Confirm clicking a badge fires onCitationClick upward to page.tsx.

Pass condition: [2]● appears inline in summary text, clickable.

Status: [ ] pending

---

## Stage 4 — Render compliance table below summary
Confirm ComplianceTable renders when message.table exists. FAIL rows first, WARN second, PASS last. Each row shows status badge, category, issue, reference text, clause, party, action.

Pass condition: table visible below summary, correctly sorted.

Status: [ ] pending

---

## Stage 5 — Verify PROJECT badge fires correctly
Click a PROJECT badge in the reference column. Confirm onCitationClick fires with type: "project", correct file_id, source_page, highlight_start, highlight_end. Check in React devtools or console log.

Pass condition: activeCitation in page.tsx updates with correct PROJECT fields.

Status: [ ] pending

---

## Stage 6 — Verify STANDARD badge fires correctly
Click a STANDARD badge in the clause column. Confirm onCitationClick fires with type: "standard", correct standard_file_id, standard_page, and highlight_start/highlight_end derived from first/last 5 words of standard_text.

Pass condition: activeCitation updates with correct STANDARD fields.

Status: [ ] pending

---

## Stage 7 — Smoke test full render flow
Upload a PROJECT file, send "Check EC3 Compliance", confirm the complete output matches the ASCII mock — clean summary with badges, table below, correct row ordering, both badge types present and clickable.

Pass condition: output matches the ASCII mock exactly. No raw JSON. No asterisks. No missing table.

Status: [ ] pending

---

## Stage 8 — Hidden Pre-Prompt + Dual Response Mode
Objective: chip clicks send hidden prompts seamlessly,
normal chat returns plain text not structured tables.

Tasks:
- Refactor chip onClick to send immediately without
  showing prompt text in chat (Tool 1)
- Add response mode detection to backend (Tool 2)
- Confirm normal questions return plain conversational text
- Confirm chip clicks return Summary + Table only

Pass condition:
- Engineer clicks "Check EC3" → sees "Check EC3 Compliance"
  as their message, not the full prompt
- Engineer types "what does clause 6.2.6 mean?" → gets
  plain conversational answer, no table
- Both response types render correctly in chat

Status: [ ] pending

---

## Next Step After This
Step 13 — FileViewer Citation Routing
activeCitation routes by file_id to the correct viewer (PDF or Excel).
See WORKFLOW.md for full task list.
