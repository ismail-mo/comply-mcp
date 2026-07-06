# COMPLY — Current Active Step
Last updated: [date]
Status: ACTIVE

## Current Step: Step 10 — PDF Viewer

## Overview
The PDF viewer is responsible for turning a citation object into a visible
document jump and highlight. The key path is:

`ChatSidebar badge click → page.tsx activeCitation → FileViewer routes by file_id → PdfViewer jumpToPage → fetch _coords.json → locate highlight text → draw rectangle in the PDF page layer`

The current code already renders PDFs with `@react-pdf-viewer`, fetches
coordinate JSON, jumps to citation pages, and injects a soft lavender highlight
into the rendered page layer. This step is about hardening and verifying that
path against real uploaded PROJECT and STANDARD PDFs.

## Visual References
Use `media/reference/` to understand the target citation-jump behaviour:

- `media/reference/reference code highlight sidebar.png`
  Shows an answer panel on the right and the cited PDF page on the left. The
  PDF jumps to the cited page and applies a broad lavender highlight over the
  relevant paragraph/section.
- `media/reference/table citations sidebar.png`
  Shows table citation badges on the right. Clicking a badge should move the
  left PDF to the cited page and highlight the corresponding source block.

Use `media/prototype/` to understand the current COMPLY shell:

- `media/prototype/ui three part viewer design.png`
  Shows the current dark three-panel layout: file list, PDF viewer, and
  compliance chat. Step 10 keeps this layout, but adds the reference-style
  citation jump and highlight behaviour.

Design target:
- Keep COMPLY's dark prototype shell.
- Behaviour should match the reference: badge click → correct PDF → correct
  page → visible source highlight.
- Highlight should read as a soft lavender source block, not a tiny word-only
  marker or a detached overlay.

---

## Stage 1 — Confirm PDF render baseline
Verify `PdfViewer.tsx` loads the selected PDF from:

```text
GET /uploads/{file_id}
```

Current code:
- Builds `fileUrl` from `NEXT_PUBLIC_API_URL`
- Uses `Worker` and `Viewer`
- Loads `defaultLayoutPlugin`
- Loads `pageNavigationPlugin`

Pass condition:
- Selecting a PDF in the file sidebar renders the PDF in the centre panel.
- No blank viewer.
- No worker error.

Status: [x] implemented in code; pending browser smoke test

---

## Stage 2 — Fetch coordinate JSON on file change
Verify `PdfViewer.tsx` fetches:

```text
GET /files/{file_id}/coordinates
```

Current code:
- Clears old highlight when `fileId` changes
- Sets `coordinates` to null before fetch
- Shows `Loading coordinates...`
- Stores parsed `PdfCoordinates`

Pass condition:
- Network tab shows one coordinates request per selected PDF.
- Successful response contains `page_count` and `pages`.
- Missing coordinate file fails gracefully without crashing viewer.

Status: [x] implemented in code; pending browser smoke test

---

## Stage 3 — Route citation file_id to correct viewer
This lives in `FileViewer.tsx`, but it is required for PDF highlighting.

Current code:
- Watches `activeCitation`
- Finds matching file by `activeCitation.file_id`
- Switches `activeFile` if the cited file is not currently open

Pass condition:
- Clicking a PROJECT badge opens the PROJECT PDF.
- Clicking a STANDARD badge opens the STANDARD PDF.
- If the cited file is already open, the viewer does not unnecessarily switch.

Status: [x] implemented in code; pending browser smoke test

---

## Stage 4 — Jump to citation page
Verify citation page numbers are converted correctly:

```text
activeCitation.page → jumpToPage(activeCitation.page - 1)
```

Current code:
- Waits until `activeCitation`, matching `fileId`, and `coordinates` exist
- Calls `jumpToPage(page - 1)`
- Retries highlight drawing after 300ms and 700ms

Pass condition:
- Clicking a badge jumps to the expected 1-based page from the table.
- Page jumps work for both PROJECT and STANDARD citations.
- Repeated clicks to different rows jump reliably.

Status: [x] implemented in code; pending browser smoke test

---

## Stage 5 — Match citation text to PDF words
Verify the text locator works from:

```text
highlight_start + highlight_end → pageData.words[]
```

Current code:
- Normalises text to lowercase ASCII word tokens
- Searches for the full `highlight_start` phrase first
- Falls back to the first word match
- Searches from the start index for `highlight_end`
- Falls back to a 15-word span when the end phrase is missing

Known risk:
- Current normalisation strips non-ASCII letters and symbols.
- Engineering symbols, section names, or copied PDF ligatures may fail to match.

Pass condition:
- Typical generated `highlight_start` and `highlight_end` locate the correct source text.
- If `highlight_end` fails, the fallback highlight still lands near the cited phrase.

Status: [x] implemented in code; pending real-document verification

---

## Stage 6 — Draw highlight inside active page layer
Verify highlight placement is relative to the rendered PDF page, not the outer
viewer shell.

Current code:
- Looks for `[data-page-number="{page}"] .rpv-core__page-layer`
- Falls back to `[aria-label="Page {page}"] .rpv-core__page-layer`
- Falls back to indexed `.rpv-core__page-layer`
- Scales PDF coordinates to rendered page dimensions
- Appends an absolutely positioned lavender source highlight to the page layer

Pass condition:
- Highlight appears on the correct page.
- Highlight appears over the cited words, not offset into the viewer chrome.
- Highlight remains visible after page jump completes.
- Highlight visually resembles the lavender reference highlight in
  `media/reference/reference code highlight sidebar.png`.

Status: [x] implemented in code; pending browser smoke test

---

## Stage 7 — Clear and persist highlight correctly
Verify only one active highlight exists at a time.

Current code:
- Removes the previous highlight before drawing a new one
- Removes highlight on file change
- Keeps the current highlight until another citation or file change

Pass condition:
- Clicking row 1 highlights row 1 text.
- Clicking row 2 removes row 1 highlight and shows row 2 highlight.
- Switching files clears stale highlights.

Status: [x] implemented in code; pending browser smoke test

---

## Stage 8 — Improve error visibility
Replace console-only failures with small viewer UI states.

Current code:
- Uses `coordsError` state for failed coordinate fetch.
- Uses `highlightStatus` for missing page, missing text, empty page text, and page render failures.
- Renders a small non-blocking message in the bottom-right viewer overlay.

Pass condition:
- If coordinates are missing, the engineer sees "Coordinates unavailable".
- If text cannot be found, the engineer sees "Citation text not found on page".
- Viewer remains usable.

Status: [x] implemented in code; pending browser smoke test

---

## Stage 9 — Smoke test PROJECT citation
Use a real compliance table row with full PROJECT fields:

```text
project_file_id
source_page
highlight_start
highlight_end
```

Pass condition:
- PROJECT badge opens the project PDF.
- Viewer jumps to `source_page`.
- Lavender highlight covers the quoted `reference_text`.

Status: [ ] pending browser smoke test

---

## Stage 10 — Smoke test STANDARD citation
Use a real compliance table row with full STANDARD fields:

```text
standard_file_id
standard_page
standard_text
```

The frontend derives:

```text
highlight_start = first 5 words of standard_text
highlight_end = last 5 words of standard_text
```

Pass condition:
- STANDARD badge opens the standard PDF.
- Viewer jumps to `standard_page`.
- Lavender highlight covers the relevant clause text.

Status: [ ] pending browser smoke test

---

## Next Step After This
Step 13 — FileViewer Citation Routing
Most routing code already exists, but after Step 10 smoke testing we should
verify the full `activeCitation.file_id` handoff across PROJECT and STANDARD
documents.
