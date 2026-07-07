'use client';

/**
 * ExcelViewer — minimal, fast spreadsheet viewer/editor.
 *
 * Replaces the former 915-line Excel clone that froze the tab:
 * - Rows are WINDOWED (only visible rows render; spacer divs keep scroll extent).
 * - The workbook parses after first paint, wrapped in try/catch.
 * - No canvas, no ribbon, no cosmetic features — every control works.
 * - First sheet row is shown as a fixed header; PATCH row index is body-relative
 *   (backend maps body row -> physical row + 2).
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import * as XLSX from 'xlsx';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const ROW_HEIGHT = 26;
const COL_WIDTH = 118;
const ROW_NUM_WIDTH = 48;
const OVERSCAN = 10;
const MAX_ROWS = 20000;
const MAX_COLS = 60;

interface SheetData {
  name: string;
  header: string[];
  body: string[][];
  cols: number;
  truncatedRows: boolean;
  truncatedCols: boolean;
}

type Status =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready' };

function colLabel(index: number): string {
  let label = '';
  let n = index;
  while (n >= 0) {
    label = String.fromCharCode(65 + (n % 26)) + label;
    n = Math.floor(n / 26) - 1;
  }
  return label;
}

function parseWorkbook(buffer: ArrayBuffer): SheetData[] {
  const wb = XLSX.read(buffer, { type: 'array' });
  return wb.SheetNames.map((name) => {
    const raw: unknown[][] = XLSX.utils.sheet_to_json(wb.Sheets[name], {
      header: 1,
      defval: '',
      raw: false,
    });
    const rows = raw.map((row) => row.map((cell) => String(cell ?? '')));
    const header = rows[0] ?? [];
    let body = rows.slice(1);
    const truncatedRows = body.length > MAX_ROWS;
    if (truncatedRows) body = body.slice(0, MAX_ROWS);
    let cols = Math.max(header.length, ...body.map((r) => r.length), 1);
    const truncatedCols = cols > MAX_COLS;
    if (truncatedCols) cols = MAX_COLS;
    return { name, header, body, cols, truncatedRows, truncatedCols };
  });
}

/* --- style constants (module scope: never re-created per render) --- */

const S = {
  root: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--surface-0)',
    color: 'var(--text-primary)',
    fontSize: 12,
  } as React.CSSProperties,
  centered: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'var(--text-muted)',
    fontSize: 12,
  } as React.CSSProperties,
  formulaBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '5px 10px',
    borderBottom: '1px solid var(--border)',
    background: 'var(--surface-1)',
    flexShrink: 0,
  } as React.CSSProperties,
  cellRef: {
    minWidth: 52,
    textAlign: 'center',
    fontSize: 11,
    color: 'var(--text-accent)',
    border: '1px solid var(--border-strong)',
    borderRadius: 3,
    padding: '3px 6px',
    background: 'var(--surface-2)',
    fontFamily: 'var(--font-mono)',
  } as React.CSSProperties,
  formulaInput: {
    flex: 1,
    background: 'var(--surface-2)',
    border: '1px solid var(--border-strong)',
    borderRadius: 3,
    color: 'var(--text-primary)',
    fontSize: 12,
    padding: '3px 8px',
    outline: 'none',
    fontFamily: 'var(--font-mono)',
  } as React.CSSProperties,
  gridWrap: {
    flex: 1,
    overflow: 'auto',
    position: 'relative',
    outline: 'none',
  } as React.CSSProperties,
  headerRow: {
    display: 'flex',
    position: 'sticky',
    top: 0,
    zIndex: 3,
    background: 'var(--surface-1)',
    borderBottom: '1px solid var(--border)',
    width: 'max-content',
    minWidth: '100%',
  } as React.CSSProperties,
  cornerCell: {
    width: ROW_NUM_WIDTH,
    minWidth: ROW_NUM_WIDTH,
    height: ROW_HEIGHT,
    position: 'sticky',
    left: 0,
    zIndex: 4,
    background: 'var(--surface-1)',
    borderRight: '1px solid var(--border)',
  } as React.CSSProperties,
  colHead: {
    width: COL_WIDTH,
    minWidth: COL_WIDTH,
    height: ROW_HEIGHT,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-start',
    padding: '0 8px',
    color: 'var(--text-secondary)',
    fontSize: 11,
    borderRight: '1px solid var(--border)',
    background: 'var(--surface-1)',
    overflow: 'hidden',
    whiteSpace: 'nowrap',
  } as React.CSSProperties,
  rowNum: {
    width: ROW_NUM_WIDTH,
    minWidth: ROW_NUM_WIDTH,
    height: ROW_HEIGHT,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'var(--text-muted)',
    fontSize: 10,
    fontFamily: 'var(--font-mono)',
    position: 'sticky',
    left: 0,
    zIndex: 2,
    background: 'var(--surface-1)',
    borderRight: '1px solid var(--border)',
    borderBottom: '1px solid var(--border)',
  } as React.CSSProperties,
  cell: {
    width: COL_WIDTH,
    minWidth: COL_WIDTH,
    height: ROW_HEIGHT,
    lineHeight: `${ROW_HEIGHT - 1}px`,
    padding: '0 8px',
    borderRight: '1px solid var(--border)',
    borderBottom: '1px solid var(--border)',
    overflow: 'hidden',
    whiteSpace: 'nowrap',
    textOverflow: 'ellipsis',
    cursor: 'default',
    fontSize: 12,
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-primary)',
  } as React.CSSProperties,
  cellSelected: {} as React.CSSProperties, // assigned below
  cellInput: {
    width: COL_WIDTH,
    minWidth: COL_WIDTH,
    height: ROW_HEIGHT,
    border: '2px solid var(--text-accent)',
    background: 'var(--surface-2)',
    color: 'var(--text-primary)',
    fontSize: 12,
    padding: '0 6px',
    outline: 'none',
    fontFamily: 'var(--font-mono)',
    boxSizing: 'border-box',
  } as React.CSSProperties,
  tabs: {
    display: 'flex',
    gap: 2,
    padding: '4px 8px',
    borderTop: '1px solid var(--border)',
    background: 'var(--surface-1)',
    flexShrink: 0,
    overflowX: 'auto',
  } as React.CSSProperties,
  notice: {
    padding: '4px 12px',
    fontSize: 10,
    color: 'var(--error-fg)',
    background: 'var(--error-bg)',
    borderBottom: '1px solid var(--border)',
    flexShrink: 0,
  } as React.CSSProperties,
  toast: {
    position: 'absolute',
    bottom: 46,
    right: 16,
    padding: '6px 12px',
    fontSize: 11,
    borderRadius: 4,
    border: '1px solid var(--border-strong)',
    background: 'var(--surface-2)',
    boxShadow: '0 2px 8px rgba(26, 26, 24, 0.10)',
    zIndex: 20,
  } as React.CSSProperties,
};

S.cellSelected = {
  ...S.cell,
  outline: '2px solid var(--text-accent)',
  outlineOffset: -2,
  background: 'rgba(24, 95, 165, 0.06)',
};

interface RowProps {
  row: string[];
  rowIndex: number;
  cols: number;
  selectedCol: number | null; // null = no selection on this row
  editingCol: number | null;
  editValue: string;
  onEditValueChange: (value: string) => void;
  onCommit: (move: 'down' | 'right' | 'none') => void;
  onCancel: () => void;
}

const GridRow = React.memo(function GridRow({
  row,
  rowIndex,
  cols,
  selectedCol,
  editingCol,
  editValue,
  onEditValueChange,
  onCommit,
  onCancel,
}: RowProps) {
  const cells = [];
  for (let c = 0; c < cols; c++) {
    if (editingCol === c) {
      cells.push(
        <input
          key={c}
          autoFocus
          style={S.cellInput}
          value={editValue}
          onChange={(e) => onEditValueChange(e.target.value)}
          onBlur={() => onCommit('none')}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              onCommit('down');
            } else if (e.key === 'Tab') {
              e.preventDefault();
              onCommit('right');
            } else if (e.key === 'Escape') {
              onCancel();
            }
            e.stopPropagation();
          }}
        />
      );
    } else {
      cells.push(
        <div
          key={c}
          data-row={rowIndex}
          data-col={c}
          style={selectedCol === c ? S.cellSelected : S.cell}
        >
          {row[c] ?? ''}
        </div>
      );
    }
  }
  return (
    <div className="xl-row" style={{ display: 'flex', width: 'max-content', minWidth: '100%' }}>
      <div style={S.rowNum}>{rowIndex + 1}</div>
      {cells}
    </div>
  );
});

export function ExcelViewer({ fileId }: { fileId: string }) {
  const [status, setStatus] = useState<Status>({ kind: 'loading' });
  const [sheets, setSheets] = useState<SheetData[]>([]);
  const [activeSheet, setActiveSheet] = useState(0);
  const [selected, setSelected] = useState<{ r: number; c: number } | null>(null);
  const [editing, setEditing] = useState<{ r: number; c: number } | null>(null);
  const [editValue, setEditValue] = useState('');
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportH, setViewportH] = useState(600);
  const [toast, setToast] = useState<{ text: string; ok: boolean } | null>(null);

  const gridRef = useRef<HTMLDivElement>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* --- load + parse (after paint) --- */
  useEffect(() => {
    let cancelled = false;
    setStatus({ kind: 'loading' });
    setSheets([]);
    setActiveSheet(0);
    setSelected(null);
    setEditing(null);

    fetch(`${BASE_URL}/uploads/${encodeURIComponent(fileId)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.arrayBuffer();
      })
      .then(
        (buffer) =>
          new Promise<SheetData[]>((resolve, reject) => {
            // Yield a frame so the loading state paints before the parse.
            setTimeout(() => {
              try {
                resolve(parseWorkbook(buffer));
              } catch (err) {
                reject(err);
              }
            }, 30);
          })
      )
      .then((parsed) => {
        if (cancelled) return;
        setSheets(parsed);
        setStatus({ kind: 'ready' });
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus({
          kind: 'error',
          message: err instanceof Error ? err.message : 'Failed to load spreadsheet',
        });
      });
    return () => {
      cancelled = true;
    };
  }, [fileId]);

  /* --- viewport tracking --- */
  useEffect(() => {
    const el = gridRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setViewportH(el.clientHeight));
    observer.observe(el);
    setViewportH(el.clientHeight);
    return () => observer.disconnect();
  }, [status.kind]);

  const sheet: SheetData | undefined = sheets[activeSheet];

  const showToast = useCallback((text: string, ok: boolean) => {
    setToast({ text, ok });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2200);
  }, []);

  /* --- editing --- */
  const startEdit = useCallback(
    (r: number, c: number, initial?: string) => {
      if (!sheet) return;
      setEditing({ r, c });
      setEditValue(initial ?? sheet.body[r]?.[c] ?? '');
    },
    [sheet]
  );

  const commitEdit = useCallback(
    (move: 'down' | 'right' | 'none') => {
      if (!editing || !sheet) return;
      const { r, c } = editing;
      const previous = sheet.body[r]?.[c] ?? '';
      setEditing(null);

      if (editValue !== previous) {
        // Optimistic local update — immutable on the changed row only.
        setSheets((prev) =>
          prev.map((s, i) => {
            if (i !== activeSheet) return s;
            const body = s.body.slice();
            const row = (body[r] ?? []).slice();
            while (row.length <= c) row.push('');
            row[c] = editValue;
            body[r] = row;
            return { ...s, body };
          })
        );
        fetch(`${BASE_URL}/files/${encodeURIComponent(fileId)}/cell`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sheet: sheet.name, row: r, col: c, value: editValue }),
        })
          .then((res) => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            showToast('Saved', true);
          })
          .catch(() => showToast('Save failed', false));
      }

      if (move === 'down' && r < sheet.body.length - 1) setSelected({ r: r + 1, c });
      else if (move === 'right' && c < sheet.cols - 1) setSelected({ r, c: c + 1 });
      else setSelected({ r, c });
      gridRef.current?.focus();
    },
    [editing, editValue, sheet, activeSheet, fileId, showToast]
  );

  const cancelEdit = useCallback(() => {
    setEditing(null);
    gridRef.current?.focus();
  }, []);

  /* --- delegated grid interaction --- */
  const handleGridMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const target = (e.target as HTMLElement).closest('[data-row]') as HTMLElement | null;
      if (!target) return;
      const r = Number(target.dataset.row);
      const c = Number(target.dataset.col);
      if (editing) commitEdit('none');
      setSelected({ r, c });
    },
    [editing, commitEdit]
  );

  const handleGridDoubleClick = useCallback(
    (e: React.MouseEvent) => {
      const target = (e.target as HTMLElement).closest('[data-row]') as HTMLElement | null;
      if (!target) return;
      startEdit(Number(target.dataset.row), Number(target.dataset.col));
    },
    [startEdit]
  );

  const handleGridKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!sheet || !selected || editing) return;
      const { r, c } = selected;
      const maxR = sheet.body.length - 1;
      const maxC = sheet.cols - 1;
      if (e.key === 'ArrowDown') setSelected({ r: Math.min(r + 1, maxR), c });
      else if (e.key === 'ArrowUp') setSelected({ r: Math.max(r - 1, 0), c });
      else if (e.key === 'ArrowRight') setSelected({ r, c: Math.min(c + 1, maxC) });
      else if (e.key === 'ArrowLeft') setSelected({ r, c: Math.max(c - 1, 0) });
      else if (e.key === 'Enter') startEdit(r, c);
      else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey) startEdit(r, c, e.key);
      else return;
      e.preventDefault();
    },
    [sheet, selected, editing, startEdit]
  );

  /* --- windowing --- */
  const totalRows = sheet?.body.length ?? 0;
  const firstRow = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const visibleCount = Math.ceil(viewportH / ROW_HEIGHT) + OVERSCAN * 2;
  const lastRow = Math.min(totalRows, firstRow + visibleCount);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  /* --- render states --- */
  if (status.kind === 'loading') {
    return (
      <div style={S.root}>
        <div style={S.centered}>Loading spreadsheet…</div>
      </div>
    );
  }
  if (status.kind === 'error') {
    return (
      <div style={S.root}>
        <div style={{ ...S.centered, color: 'var(--fail-fg)' }}>
          Failed to load spreadsheet — {status.message}
        </div>
      </div>
    );
  }
  if (!sheet) {
    return (
      <div style={S.root}>
        <div style={S.centered}>No sheets found in this workbook</div>
      </div>
    );
  }

  const selectedValue =
    editing !== null
      ? editValue
      : selected
        ? sheet.body[selected.r]?.[selected.c] ?? ''
        : '';

  const rows = [];
  for (let r = firstRow; r < lastRow; r++) {
    rows.push(
      <GridRow
        key={r}
        row={sheet.body[r] ?? []}
        rowIndex={r}
        cols={sheet.cols}
        selectedCol={selected?.r === r ? selected.c : null}
        editingCol={editing?.r === r ? editing.c : null}
        editValue={editValue}
        onEditValueChange={setEditValue}
        onCommit={commitEdit}
        onCancel={cancelEdit}
      />
    );
  }

  return (
    <div style={{ ...S.root, position: 'relative' }}>
      <style>{`.xl-row:hover { background: #F1EFE9; }`}</style>
      {/* Formula bar */}
      <div style={S.formulaBar}>
        <span style={S.cellRef}>
          {selected ? `${colLabel(selected.c)}${selected.r + 1}` : '—'}
        </span>
        <input
          style={S.formulaInput}
          value={selectedValue}
          placeholder={selected ? '' : 'Select a cell'}
          disabled={!selected}
          onFocus={() => {
            if (selected && !editing) startEdit(selected.r, selected.c);
          }}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitEdit('none');
            else if (e.key === 'Escape') cancelEdit();
          }}
        />
      </div>

      {(sheet.truncatedRows || sheet.truncatedCols) && (
        <div style={S.notice}>
          {sheet.truncatedRows && `Showing first ${MAX_ROWS.toLocaleString()} rows. `}
          {sheet.truncatedCols && `Showing first ${MAX_COLS} columns.`}
        </div>
      )}

      {/* Grid */}
      {totalRows === 0 ? (
        <div style={S.centered}>Empty sheet</div>
      ) : (
        <div
          ref={gridRef}
          style={S.gridWrap}
          tabIndex={0}
          onScroll={handleScroll}
          onMouseDown={handleGridMouseDown}
          onDoubleClick={handleGridDoubleClick}
          onKeyDown={handleGridKeyDown}
        >
          {/* Column letters + sheet header row */}
          <div style={S.headerRow}>
            <div style={S.cornerCell} />
            {Array.from({ length: sheet.cols }, (_, c) => (
              <div key={c} style={S.colHead} title={sheet.header[c] ?? ''}>
                <span>{colLabel(c)}</span>
                {sheet.header[c] ? (
                  <span
                    style={{
                      marginLeft: 6,
                      color: 'var(--text-secondary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {sheet.header[c]}
                  </span>
                ) : null}
              </div>
            ))}
          </div>

          {/* Top spacer */}
          <div style={{ height: firstRow * ROW_HEIGHT }} />
          {rows}
          {/* Bottom spacer */}
          <div style={{ height: Math.max(0, (totalRows - lastRow) * ROW_HEIGHT) }} />
        </div>
      )}

      {/* Sheet tabs */}
      <div style={S.tabs}>
        {sheets.map((s, i) => (
          <button
            key={s.name}
            onClick={() => {
              setActiveSheet(i);
              setSelected(null);
              setEditing(null);
              setScrollTop(0);
              if (gridRef.current) gridRef.current.scrollTop = 0;
            }}
            style={{
              background: i === activeSheet ? 'var(--surface-2)' : 'transparent',
              border:
                i === activeSheet ? '1px solid var(--border-strong)' : '1px solid var(--border)',
              color: i === activeSheet ? 'var(--text-primary)' : 'var(--text-muted)',
              fontSize: 11,
              padding: '3px 12px',
              cursor: 'pointer',
              borderRadius: '3px 3px 0 0',
              whiteSpace: 'nowrap',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {s.name}
          </button>
        ))}
      </div>

      {toast && (
        <div
          style={{
            ...S.toast,
            color: toast.ok ? 'var(--pass-fg)' : 'var(--fail-fg)',
          }}
        >
          {toast.text}
        </div>
      )}
    </div>
  );
}
