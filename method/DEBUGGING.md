# Debugging Methods — Lessons From The PDF Freeze

## What Went Wrong (The Circle)

We spent hours applying fixes to `@react-pdf-viewer` — hoisting the Worker, adding/removing `key` props, creating a `PdfPanel` wrapper, removing `defaultLayoutPlugin`, reverting all of it — without ever confirming which layer of the stack was actually responsible.

Every fix was based on reasoning about what *should* cause a freeze, not on evidence about what *was* causing it.

The result: each fix changed symptoms without resolving the root cause, and some changes (removing `defaultLayoutPlugin`) actively made things worse by removing page virtualisation, causing an OOM crash.

---

## What Finally Worked

**Binary isolation:** Replace the suspected component with the simplest possible thing that still exercises the same render path.

```tsx
// Replaced @react-pdf-viewer's entire stack with:
<iframe src={fileUrl} style={{ flex: 1, border: 'none', width: '100%' }} />
```

One change. One answer. Freeze gone → confirmed `@react-pdf-viewer` is the cause, not state management, not React.memo, not the effect dependencies, not CORS, not the Worker file, not the Next.js config.

---

## The Two-Pronged Diagnostic Condition

Before writing any fix, define two things:

1. **What the fix predicts** — "if this is the cause, the freeze should disappear after this change"
2. **What the fallback predicts** — "if the freeze persists after the fix, the cause is elsewhere"

Then make the smallest change that produces a clear yes/no answer. Do not combine multiple fixes in one attempt — you lose the signal.

---

## Fast-Track Troubleshooting Rules

### 1. Isolate before you fix
When a component freezes, swap it for a stub (empty div, iframe, `<p>Loading</p>`) before touching any logic. If the freeze disappears, the component is the culprit. If it persists, the problem is in the parent or state.

### 2. One variable per attempt
Never combine fixes. "I'll stabilise the plugins AND hoist the Worker AND add React.memo" tests three hypotheses simultaneously. When it doesn't work you learn nothing. When it does work you don't know which one fixed it.

### 3. Read the error code first
- `RESULT_CODE_HUNG` = renderer OOM or JS timeout. Likely causes: rendering all canvas pages at once, infinite render loop, or synchronous blocking on main thread.
- `Page Unresponsive` = JS blocked. Likely: heavy synchronous init, unguarded infinite loop, or memory pressure.
- Blank panel + responsive UI = async load not completing (Worker error, fetch error, bad fileUrl).
- These are different problems. Do not treat them the same.

### 4. Check what changed since it last worked
If the user says "it used to work," ask or check what changed before reaching for a fix. Compare the current code against the last known-good state rather than reasoning from first principles. This avoids fixing things that were never broken.

### 5. Never remove a feature without understanding why it was there
`defaultLayoutPlugin` was removed because it was suspected as the freeze cause. It was actually providing page virtualisation — the essential feature that prevents rendering 100 PDF pages as canvas simultaneously. Removing it turned a slow freeze into an OOM crash. Before removing anything from a working codebase, know what it does.

### 6. Distinguish library bugs from architecture bugs
The `@react-pdf-viewer` freeze was a library problem, not an architecture problem. Restructuring React.memo, Worker placement, and key props were architecture changes applied to a library problem. They changed the rendering path but couldn't fix the underlying library behaviour.

### 7. Use the browser's own tools as diagnostic stubs
- **iframe** for any document viewer — no JS overhead, shows whether the fetch/CORS path works
- **`<div>rendered</div>`** for any complex component — confirms the render path reaches the component
- **`console.time` / `console.timeEnd`** around a suspected blocking call — confirms whether it's synchronous

---

## Fixes That Were Correct And Should Stay

These came from the COMPLY freeze diagnosis and are valid:

| Fix | File | Why |
|-----|------|-----|
| `React.memo` on `FileViewer` | FileViewer.tsx | Stops streaming tokens from re-rendering the PDF viewer on every SSE event |
| `React.memo` on `FileSidebar` | FileSidebar.tsx | Same — FileSidebar doesn't need messages or streaming, memo prevents unnecessary work |
| Dynamic `ExcelViewer` import | FileViewer.tsx | Keeps SheetJS out of the main bundle for PDF-only sessions |
| RAF-throttled scroll | ChatSidebar.tsx | Prevents `scrollIntoView` from blocking the main thread on every token |
| `AbortController` on coordinates fetch | PdfViewer.tsx | Cancels stale requests on file switch |
| `onDone()` in AbortError catch | api.ts | Clears `streaming` state when SSE fetch is aborted |
| Always-visible textarea | ChatSidebar.tsx | Input is available before a file is selected; send/chips disabled instead of hidden |

---

## Current State: PDF Viewer

`PdfViewer.tsx` is now a bare `<iframe>` pointing at the backend upload URL. This:
- Has zero JS overhead
- Uses the browser's native PDF renderer
- Cannot be used for `jumpToPage` or highlight overlays (those require programmatic control)

The next step (when ready) is to replace the iframe with a lighter library that supports page navigation and canvas overlays without the `@react-pdf-viewer` initialisation cost. Candidates: `react-pdf` (lower-level, more control), or a custom PDF.js wrapper.

Citation jumps and highlights are currently non-functional. Core compliance chat and file switching work.
