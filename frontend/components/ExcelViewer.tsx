'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as XLSX from 'xlsx';

interface ExcelViewerProps { fileId: string; }

interface CellStyle {
  bold?: boolean; italic?: boolean; underline?: boolean;
  align?: 'left' | 'center' | 'right';
  fontFamily?: string; fontSize?: number; format?: string; wrap?: boolean;
  background?: string; color?: string;
}

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const COL_WIDTH = 120;
const ROW_NUM_WIDTH = 50;
const RIBBON_TABS = ['File','Home','Insert','Share','Page Layout','Formulas','Data','Review','View','Draw'];

function colIndexToLabel(i: number): string {
  if (i < 26) return String.fromCharCode(65 + i);
  return String.fromCharCode(65 + Math.floor(i / 26) - 1) + String.fromCharCode(65 + (i % 26));
}

function colLabelToIndex(label: string): number {
  label = label.toUpperCase();
  let n = 0;
  for (let i = 0; i < label.length; i++) n = n * 26 + (label.charCodeAt(i) - 64);
  return n - 1;
}

function cellKey(sheet: string, row: number, col: number) { return `${sheet}:${row}:${col}`; }

const rbBtn = (extra?: React.CSSProperties): React.CSSProperties => ({
  height: 28, minWidth: 28, padding: '0 6px', display: 'flex', alignItems: 'center',
  justifyContent: 'center', gap: 4, fontSize: 11, color: '#212121', background: 'transparent',
  border: '1px solid transparent', borderRadius: 2, cursor: 'pointer', whiteSpace: 'nowrap', ...extra,
});

const rbDrop: React.CSSProperties = {
  height: 22, fontSize: 11, border: '1px solid #ababab', background: 'white',
  borderRadius: 2, padding: '0 4px', cursor: 'pointer', color: '#212121',
};

function Divider() {
  return <div style={{ width: 1, height: 28, background: '#d0d0d0', margin: '0 6px', flexShrink: 0 }} />;
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>{children}</div>
      <span style={{ fontSize: 9, color: '#666', textAlign: 'center', marginTop: 2 }}>{label}</span>
    </div>
  );
}

function makeEmptySheet(rows = 50, cols = 26): unknown[][] {
  const arr: unknown[][] = [];
  const header: string[] = Array.from({ length: cols }, (_, i) => colIndexToLabel(i));
  arr.push(header);
  for (let r = 0; r < rows; r++) arr.push(Array(cols).fill(''));
  return arr;
}

export function ExcelViewer({ fileId }: ExcelViewerProps) {
  const [sheets, setSheets] = useState<Map<string, unknown[][]>>(new Map());
  const [activeSheet, setActiveSheet] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [selectedCell, setSelectedCell] = useState<{ row: number; col: number } | null>(null);
  const [activeCell, setActiveCell] = useState<{ row: number; col: number } | null>(null);
  const [selectionRange, setSelectionRange] = useState<{ start: { row: number; col: number }; end: { row: number; col: number } } | null>(null);
  const [formulaBarValue, setFormulaBarValue] = useState('');
  const [cellStyles, setCellStyles] = useState<Map<string, CellStyle>>(new Map());
  const [activeCellEditValue, setActiveCellEditValue] = useState('');
  const [activeRibbonTab, setActiveRibbonTab] = useState('Home');
  const [zoom, setZoom] = useState(100);
  const [showFormulas, setShowFormulas] = useState(false);
  const [showComments, setShowComments] = useState(false);
  const [showGridlines, setShowGridlines] = useState(true);
  const [drawTool, setDrawTool] = useState<'pen' | 'highlighter' | null>(null);
  const [drawColour, setDrawColour] = useState('#ffff00');
  const [drawSize, setDrawSize] = useState(2);
  const [filterActive, setFilterActive] = useState(false);
  const [filterValue, setFilterValue] = useState('');
  const [frozenRows, setFrozenRows] = useState(0);
  const [frozenCols, setFrozenCols] = useState(0);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [comments, setComments] = useState<Map<string, string>>(new Map());
  const [hoveredCommentCell, setHoveredCommentCell] = useState<{ row: number; col: number } | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);

  const gridRef = useRef<HTMLDivElement>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeCellInputRef = useRef<HTMLInputElement>(null);
  const colHeaderRef = useRef<HTMLDivElement>(null);
  const rowNumRef = useRef<HTMLDivElement>(null);
  const dataGridRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const gridWrapperRef = useRef<HTMLDivElement>(null);

  function showToast(msg: string) {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToastMessage(msg);
    toastTimerRef.current = setTimeout(() => setToastMessage(null), 2500);
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true); setError(null);
      try {
        const res = await fetch(`${BASE_URL}/uploads/${encodeURIComponent(fileId)}`);
        if (!res.ok) throw new Error(`Failed to fetch file: ${res.status}`);
        const buffer = await res.arrayBuffer();
        if (cancelled) return;
        await new Promise<void>((r) => setTimeout(r, 0)); // yield before sync parse
        if (cancelled) return;
        const wb = XLSX.read(buffer, { type: 'array' });
        const map = new Map<string, unknown[][]>();
        for (const name of wb.SheetNames)
          map.set(name, XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1 }) as unknown[][]);
        if (!cancelled) { setSheets(map); setActiveSheet(wb.SheetNames[0] ?? ''); setSelectedCell(null); setActiveCell(null); }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to read file');
      } finally { if (!cancelled) setLoading(false); }
    }
    load();
    return () => { cancelled = true; };
  }, [fileId]);

  useEffect(() => { if (!loading && gridRef.current) gridRef.current.focus(); }, [loading]);

  function setStatus(s: SaveStatus, d?: number) {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    setSaveStatus(s);
    if (d) saveTimerRef.current = setTimeout(() => setSaveStatus('idle'), d);
  }

  const getRows = useCallback(() => sheets.get(activeSheet) ?? [], [sheets, activeSheet]);
  const getHeader = useCallback(() => getRows()[0] ?? [], [getRows]);
  const getBody = useCallback(() => getRows().slice(1), [getRows]);

  function getCellValue(row: number, col: number): string {
    const v = getBody()[row]?.[col];
    return v != null && v !== '' ? String(v) : '';
  }

  function getCellStyle(row: number, col: number): CellStyle {
    return cellStyles.get(cellKey(activeSheet, row, col)) ?? {};
  }

  function setCellStyleProp<K extends keyof CellStyle>(row: number, col: number, key: K, val: CellStyle[K]) {
    setCellStyles(prev => {
      const next = new Map(prev);
      const k = cellKey(activeSheet, row, col);
      next.set(k, { ...(prev.get(k) ?? {}), [key]: val });
      return next;
    });
  }

  async function saveCell(row: number, col: number, value: string) {
    setStatus('saving');
    try {
      const res = await fetch(`${BASE_URL}/files/${encodeURIComponent(fileId)}/cell`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sheet: activeSheet, row, col, value }),
      });
      if (!res.ok) throw new Error();
      setStatus('saved', 2000);
    } catch { setStatus('error', 3000); }
  }

  function updateCellInState(row: number, col: number, value: string) {
    setSheets(prev => {
      const next = new Map(prev);
      const rows = prev.get(activeSheet) ?? [];
      next.set(activeSheet, rows.map((r, ri) => {
        if (ri !== row + 1) return r;
        const nr = [...r]; nr[col] = value; return nr;
      }));
      return next;
    });
  }

  function commitEdit(row: number, col: number, value: string, original: string) {
    if (value !== original) { updateCellInState(row, col, value); saveCell(row, col, value); }
    setActiveCell(null); setSelectedCell({ row, col }); setFormulaBarValue(value);
    setTimeout(() => gridRef.current?.focus(), 0);
  }

  function selectCell(row: number, col: number) {
    setSelectedCell({ row, col }); setSelectionRange(null);
    setFormulaBarValue(getCellValue(row, col));
  }

  function enterEditMode(row: number, col: number) {
    setActiveCell({ row, col }); setActiveCellEditValue(getCellValue(row, col));
    setTimeout(() => activeCellInputRef.current?.focus(), 0);
  }

  const header = getHeader();
  const body = getBody();
  const totalCols = Math.max(header.length, ...body.map(r => r.length), 1);
  const totalRows = body.length;

  function moveSelection(dr: number, dc: number) {
    if (!selectedCell) { selectCell(0, 0); return; }
    selectCell(Math.max(0, Math.min(totalRows - 1, selectedCell.row + dr)),
               Math.max(0, Math.min(totalCols - 1, selectedCell.col + dc)));
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (activeCell) return;
    if (!selectedCell) { selectCell(0, 0); return; }
    const { row, col } = selectedCell;
    if (e.key === 'ArrowUp') { e.preventDefault(); moveSelection(-1, 0); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); moveSelection(1, 0); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); moveSelection(0, -1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); moveSelection(0, 1); }
    else if (e.key === 'Tab') { e.preventDefault(); e.shiftKey ? moveSelection(0, -1) : moveSelection(0, 1); }
    else if (e.key === 'Enter') { e.preventDefault(); e.shiftKey ? moveSelection(-1, 0) : moveSelection(1, 0); }
    else if (e.key === 'F2') { e.preventDefault(); enterEditMode(row, col); }
    else if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault(); updateCellInState(row, col, ''); saveCell(row, col, ''); setFormulaBarValue('');
    } else if (e.shiftKey && ['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)) {
      e.preventDefault();
      const base = selectionRange?.start ?? selectedCell;
      const end = { ...(selectionRange?.end ?? selectedCell) };
      if (e.key === 'ArrowUp') end.row = Math.max(0, end.row - 1);
      if (e.key === 'ArrowDown') end.row = Math.min(totalRows - 1, end.row + 1);
      if (e.key === 'ArrowLeft') end.col = Math.max(0, end.col - 1);
      if (e.key === 'ArrowRight') end.col = Math.min(totalCols - 1, end.col + 1);
      setSelectionRange({ start: base, end });
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
      enterEditMode(row, col); setActiveCellEditValue(e.key);
    }
  }

  function isInRange(row: number, col: number): boolean {
    if (!selectionRange) return false;
    return row >= Math.min(selectionRange.start.row, selectionRange.end.row) &&
           row <= Math.max(selectionRange.start.row, selectionRange.end.row) &&
           col >= Math.min(selectionRange.start.col, selectionRange.end.col) &&
           col <= Math.max(selectionRange.start.col, selectionRange.end.col);
  }

  function handleDataScroll(e: React.UIEvent<HTMLDivElement>) {
    const el = e.currentTarget;
    if (colHeaderRef.current) colHeaderRef.current.scrollLeft = el.scrollLeft;
    if (rowNumRef.current) rowNumRef.current.scrollTop = el.scrollTop;
  }

  // ── FILE TAB ──────────────────────────────────────────────────────────────
  function handleNew() {
    const map = new Map<string, unknown[][]>();
    map.set('Sheet1', makeEmptySheet());
    setSheets(map); setActiveSheet('Sheet1');
    setSelectedCell(null); setActiveCell(null); setCellStyles(new Map());
    setFormulaBarValue('');
  }

  function handleOpen() { fileInputRef.current?.click(); }

  function handleFileInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const buffer = ev.target?.result as ArrayBuffer;
      const wb = XLSX.read(buffer, { type: 'array' });
      const map = new Map<string, unknown[][]>();
      for (const name of wb.SheetNames)
        map.set(name, XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1 }) as unknown[][]);
      setSheets(map); setActiveSheet(wb.SheetNames[0] ?? '');
      setSelectedCell(null); setActiveCell(null); setCellStyles(new Map());
    };
    reader.readAsArrayBuffer(file);
    e.target.value = '';
  }

  function handleSave(filename?: string) {
    const name = filename ?? fileId.replace(/^[^_]+_/, '');
    const wb = XLSX.utils.book_new();
    for (const [sheetName, rows] of Array.from(sheets.entries())) {
      const ws = XLSX.utils.aoa_to_sheet(rows as unknown[][]);
      XLSX.utils.book_append_sheet(wb, ws, sheetName);
    }
    XLSX.writeFile(wb, name.endsWith('.xlsx') ? name : name + '.xlsx');
  }

  function handleSaveAs() {
    const defaultName = fileId.replace(/^[^_]+_/, '');
    const name = window.prompt('Save as:', defaultName);
    if (name == null) return;
    handleSave(name);
  }

  // ── HOME TAB ──────────────────────────────────────────────────────────────
  function handleCopyRibbon() {
    if (!selectedCell) return;
    navigator.clipboard.writeText(getCellValue(selectedCell.row, selectedCell.col));
  }

  async function handlePasteRibbon() {
    try {
      const text = await navigator.clipboard.readText();
      if (selectedCell && text !== undefined) {
        updateCellInState(selectedCell.row, selectedCell.col, text);
        saveCell(selectedCell.row, selectedCell.col, text);
        setFormulaBarValue(text);
      }
    } catch { /* permission denied */ }
  }

  function toggleStyle(key: 'bold' | 'italic' | 'underline' | 'wrap') {
    if (!selectedCell) return;
    const cur = getCellStyle(selectedCell.row, selectedCell.col)[key];
    setCellStyleProp(selectedCell.row, selectedCell.col, key, !cur);
  }

  function setAlign(align: 'left' | 'center' | 'right') {
    if (!selectedCell) return;
    setCellStyleProp(selectedCell.row, selectedCell.col, 'align', align);
  }

  function setFont(fontFamily: string) {
    if (!selectedCell) return;
    setCellStyleProp(selectedCell.row, selectedCell.col, 'fontFamily', fontFamily);
  }

  function setFontSize(size: number) {
    if (!selectedCell) return;
    setCellStyleProp(selectedCell.row, selectedCell.col, 'fontSize', size);
  }

  function setFormat(format: string) {
    if (!selectedCell) return;
    setCellStyleProp(selectedCell.row, selectedCell.col, 'format', format);
  }

  // ── INSERT TAB ────────────────────────────────────────────────────────────
  function handleInsertRow() {
    if (!selectedCell) return;
    setSheets(prev => {
      const next = new Map(prev);
      const rows = [...(prev.get(activeSheet) ?? [])];
      const emptyRow = Array(totalCols).fill('');
      rows.splice(selectedCell.row + 1, 0, emptyRow);
      next.set(activeSheet, rows);
      return next;
    });
    showToast('Row inserted (in-memory only)');
  }

  function handleInsertCol() {
    if (!selectedCell) return;
    setSheets(prev => {
      const next = new Map(prev);
      const rows = (prev.get(activeSheet) ?? []).map(r => {
        const nr = [...r]; nr.splice(selectedCell.col, 0, ''); return nr;
      });
      next.set(activeSheet, rows);
      return next;
    });
    showToast('Column inserted (in-memory only)');
  }

  function handleDeleteRow() {
    if (!selectedCell) return;
    setSheets(prev => {
      const next = new Map(prev);
      const rows = [...(prev.get(activeSheet) ?? [])];
      rows.splice(selectedCell.row + 1, 1);
      next.set(activeSheet, rows);
      return next;
    });
    showToast('Row deleted (in-memory only)');
  }

  function handleDeleteCol() {
    if (!selectedCell) return;
    setSheets(prev => {
      const next = new Map(prev);
      const rows = (prev.get(activeSheet) ?? []).map(r => {
        const nr = [...r]; nr.splice(selectedCell.col, 1); return nr;
      });
      next.set(activeSheet, rows);
      return next;
    });
    showToast('Column deleted (in-memory only)');
  }

  // ── DATA TAB ──────────────────────────────────────────────────────────────
  function handleSort(asc: boolean) {
    const col = selectedCell?.col ?? 0;
    setSheets(prev => {
      const next = new Map(prev);
      const rows = prev.get(activeSheet) ?? [];
      const headerRow = rows[0];
      const dataRows = [...rows.slice(1)];
      dataRows.sort((a, b) => {
        const av = String(a[col] ?? ''); const bv = String(b[col] ?? '');
        return asc ? av.localeCompare(bv) : bv.localeCompare(av);
      });
      next.set(activeSheet, [headerRow, ...dataRows]);
      return next;
    });
  }

  // ── REVIEW TAB ────────────────────────────────────────────────────────────
  function handleAddComment() {
    if (!selectedCell) { showToast('Select a cell first'); return; }
    const key = cellKey(activeSheet, selectedCell.row, selectedCell.col);
    const existing = comments.get(key) ?? '';
    const text = window.prompt('Add comment:', existing);
    if (text === null) return;
    setComments(prev => {
      const next = new Map(prev);
      if (text.trim() === '') next.delete(key); else next.set(key, text);
      return next;
    });
  }

  // ── FORMULAS TAB ─────────────────────────────────────────────────────────
  function handleNameBoxJump(ref: string) {
    const match = ref.trim().match(/^([A-Za-z]+)(\d+)$/);
    if (!match) { showToast('Invalid cell reference'); return; }
    const col = colLabelToIndex(match[1]);
    const row = parseInt(match[2]) - 1;
    if (row < 0 || col < 0 || row >= totalRows || col >= totalCols) {
      showToast('Invalid cell reference'); return;
    }
    selectCell(row, col);
    if (dataGridRef.current) {
      dataGridRef.current.scrollTop = row * 22;
      dataGridRef.current.scrollLeft = col * COL_WIDTH;
    }
  }

  // ── CANVAS / DRAW TAB ─────────────────────────────────────────────────────
  function getCtx() {
    const canvas = canvasRef.current; if (!canvas) return null;
    return canvas.getContext('2d');
  }

  function handleCanvasMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!drawTool) return;
    setIsDrawing(true);
    const ctx = getCtx(); if (!ctx) return;
    const rect = canvasRef.current!.getBoundingClientRect();
    ctx.beginPath();
    ctx.moveTo(e.clientX - rect.left, e.clientY - rect.top);
    ctx.strokeStyle = drawColour;
    ctx.lineCap = 'round';
    if (drawTool === 'highlighter') { ctx.globalAlpha = 0.35; ctx.lineWidth = drawSize * 6; }
    else { ctx.globalAlpha = 1; ctx.lineWidth = drawSize; }
  }

  function handleCanvasMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!isDrawing || !drawTool) return;
    const ctx = getCtx(); if (!ctx) return;
    const rect = canvasRef.current!.getBoundingClientRect();
    ctx.lineTo(e.clientX - rect.left, e.clientY - rect.top);
    ctx.stroke();
  }

  function handleCanvasMouseUp() {
    if (!isDrawing) return;
    setIsDrawing(false);
    const ctx = getCtx(); if (!ctx) return;
    ctx.globalAlpha = 1;
  }

  function handleClearCanvas() {
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx?.clearRect(0, 0, canvas.width, canvas.height);
  }

  const selStyle = selectedCell ? getCellStyle(selectedCell.row, selectedCell.col) : {};
  const cellRef = selectedCell ? `${colIndexToLabel(selectedCell.col)}${selectedCell.row + 1}` : '';

  // filtered body
  const filteredBody = filterActive && filterValue
    ? body.filter(row => {
        const col = selectedCell?.col ?? 0;
        return String(row[col] ?? '').toLowerCase().includes(filterValue.toLowerCase());
      })
    : body;

  // ── RIBBON CONTENT ────────────────────────────────────────────────────────
  function renderRibbonContent() {
    switch (activeRibbonTab) {
      case 'File': return (
        <Group label="File">
          <button style={rbBtn()} onClick={handleNew}>📄 New</button>
          <button style={rbBtn()} onClick={handleOpen}>📂 Open</button>
          <button style={rbBtn()} onClick={() => handleSave()}>💾 Save</button>
          <button style={rbBtn()} onClick={handleSaveAs}>💾+ Save As</button>
        </Group>
      );

      case 'Home': return (
        <>
          <Group label="Clipboard">
            <button style={rbBtn()} onClick={handleCopyRibbon}>⎘ Copy</button>
            <button style={rbBtn()} onClick={handlePasteRibbon}>⎗ Paste</button>
          </Group>
          <Divider />
          <Group label="Font">
            <select value={selStyle.fontFamily ?? 'Calibri'} onChange={e => setFont(e.target.value)} style={rbDrop}>
              {['Arial','Calibri','Times New Roman','Courier New'].map(f => <option key={f}>{f}</option>)}
            </select>
            <select value={selStyle.fontSize ?? 11} onChange={e => setFontSize(Number(e.target.value))} style={{ ...rbDrop, width: 44 }}>
              {[8,10,11,12,14,16,18,20,24].map(s => <option key={s}>{s}</option>)}
            </select>
            <button onClick={() => toggleStyle('bold')} style={rbBtn({ fontWeight: 'bold', background: selStyle.bold ? '#d0d7e0' : undefined })}>B</button>
            <button onClick={() => toggleStyle('italic')} style={rbBtn({ fontStyle: 'italic', background: selStyle.italic ? '#d0d7e0' : undefined })}>I</button>
            <button onClick={() => toggleStyle('underline')} style={rbBtn({ textDecoration: 'underline', background: selStyle.underline ? '#d0d7e0' : undefined })}>U</button>
            <label style={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: 10, color: '#444', cursor: 'pointer' }}>
              Fill
              <input type="color" value={selStyle.background ?? '#ffffff'} onChange={e => { if (selectedCell) setCellStyleProp(selectedCell.row, selectedCell.col, 'background', e.target.value); }} style={{ width: 22, height: 18, border: 'none', padding: 0, cursor: 'pointer' }} />
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: 10, color: '#444', cursor: 'pointer' }}>
              Text
              <input type="color" value={selStyle.color ?? '#212121'} onChange={e => { if (selectedCell) setCellStyleProp(selectedCell.row, selectedCell.col, 'color', e.target.value); }} style={{ width: 22, height: 18, border: 'none', padding: 0, cursor: 'pointer' }} />
            </label>
          </Group>
          <Divider />
          <Group label="Alignment">
            <button onClick={() => setAlign('left')} style={rbBtn({ background: selStyle.align === 'left' ? '#d0d7e0' : undefined })}>≡</button>
            <button onClick={() => setAlign('center')} style={rbBtn({ background: selStyle.align === 'center' ? '#d0d7e0' : undefined })}>☰</button>
            <button onClick={() => setAlign('right')} style={rbBtn({ background: selStyle.align === 'right' ? '#d0d7e0' : undefined })}>≡</button>
            <button onClick={() => toggleStyle('wrap')} style={rbBtn({ background: selStyle.wrap ? '#d0d7e0' : undefined })}>⇥ Wrap</button>
          </Group>
          <Divider />
          <Group label="Number">
            <select value={selStyle.format ?? 'General'} onChange={e => setFormat(e.target.value)} style={rbDrop}>
              {['General','Number','Currency','Percentage','Text'].map(f => <option key={f}>{f}</option>)}
            </select>
          </Group>
        </>
      );

      case 'Insert': return (
        <Group label="Rows & Columns">
          <button style={rbBtn()} onClick={handleInsertRow}>⊞↓ Row</button>
          <button style={rbBtn()} onClick={handleInsertCol}>⊞→ Col</button>
          <button style={rbBtn()} onClick={handleDeleteRow}>⊟↓ Del Row</button>
          <button style={rbBtn()} onClick={handleDeleteCol}>⊟→ Del Col</button>
        </Group>
      );

      case 'Share': return (
        <Group label="Share">
          <button style={rbBtn()} onClick={() => { navigator.clipboard.writeText(window.location.href); showToast('Link copied to clipboard'); }}>🔗 Copy Link</button>
        </Group>
      );

      case 'Page Layout': return (
        <>
          <Group label="Sheet">
            <button onClick={() => setShowGridlines(g => !g)} style={rbBtn({ background: showGridlines ? '#d0d7e0' : undefined })}>⊞ Gridlines</button>
          </Group>
          <Divider />
          <Group label="Scale">
            <input readOnly value={`${zoom}%`} style={{ ...rbDrop, width: 52, textAlign: 'center' }} />
          </Group>
        </>
      );

      case 'Formulas': return (
        <>
          <Group label="Formula Auditing">
            <button onClick={() => setShowFormulas(f => !f)} style={rbBtn({ background: showFormulas ? '#d0d7e0' : undefined })}>fx Show Formulas</button>
          </Group>
          <Divider />
          <Group label="Named Ranges">
            <input
              placeholder="e.g. B5"
              style={{ ...rbDrop, width: 80 }}
              onKeyDown={e => { if (e.key === 'Enter') { handleNameBoxJump(e.currentTarget.value); e.currentTarget.value = ''; } }}
            />
          </Group>
        </>
      );

      case 'Data': return (
        <>
          <Group label="Sort">
            <button style={rbBtn()} onClick={() => handleSort(true)}>↑A Sort A→Z</button>
            <button style={rbBtn()} onClick={() => handleSort(false)}>↓Z Sort Z→A</button>
          </Group>
          <Divider />
          <Group label="Filter">
            <button onClick={() => { setFilterActive(f => !f); setFilterValue(''); }} style={rbBtn({ background: filterActive ? '#d0d7e0' : undefined })}>⊟ Filter</button>
            <button style={rbBtn()} onClick={() => { setFilterActive(false); setFilterValue(''); }}>✕ Clear</button>
          </Group>
        </>
      );

      case 'Review': return (
        <Group label="Comments">
          <button style={rbBtn()} onClick={handleAddComment}>💬 Add Comment</button>
          <button onClick={() => setShowComments(c => !c)} style={rbBtn({ background: showComments ? '#d0d7e0' : undefined })}>💬 Show/Hide</button>
        </Group>
      );

      case 'View': return (
        <>
          <Group label="Freeze">
            <button style={rbBtn()} onClick={() => { setFrozenRows(selectedCell?.row ?? 1); showToast(`Rows frozen at row ${selectedCell?.row ?? 1}`); }}>❄↓ Rows</button>
            <button style={rbBtn()} onClick={() => setFrozenCols(selectedCell?.col ?? 1)}>❄→ Cols</button>
            <button style={rbBtn()} onClick={() => { setFrozenRows(selectedCell?.row ?? 1); setFrozenCols(selectedCell?.col ?? 1); }}>❄ Both</button>
            <button style={rbBtn()} onClick={() => { setFrozenRows(0); setFrozenCols(0); showToast('Panes unfrozen'); }}>✕❄ Unfreeze</button>
          </Group>
          <Divider />
          <Group label="Zoom">
            <button style={rbBtn()} onClick={() => setZoom(z => Math.min(200, z + 10))}>＋</button>
            <button style={rbBtn()} onClick={() => setZoom(z => Math.max(50, z - 10))}>－</button>
            <span style={{ fontSize: 12, color: '#444', minWidth: 36, textAlign: 'center' }}>{zoom}%</span>
          </Group>
        </>
      );

      case 'Draw': return (
        <>
          <Group label="Tools">
            <button onClick={() => setDrawTool(t => t === 'pen' ? null : 'pen')} style={rbBtn({ background: drawTool === 'pen' ? '#d0d7e0' : undefined })}>✏ Pen</button>
            <button onClick={() => setDrawTool(t => t === 'highlighter' ? null : 'highlighter')} style={rbBtn({ background: drawTool === 'highlighter' ? '#d0d7e0' : undefined })}>▮ Highlighter</button>
          </Group>
          <Divider />
          <Group label="Color">
            <input type="color" value={drawColour} onChange={e => setDrawColour(e.target.value)} style={{ width: 32, height: 22, border: 'none', borderRadius: 2, padding: 0, cursor: 'pointer' }} />
          </Group>
          <Divider />
          <Group label="Size">
            <select value={drawSize} onChange={e => setDrawSize(Number(e.target.value))} style={rbDrop}>
              {[1,2,3,4].map(s => <option key={s} value={s}>{s}px</option>)}
            </select>
          </Group>
          <Divider />
          <Group label="Clear">
            <button style={rbBtn()} onClick={handleClearCanvas}>🗑 Clear</button>
          </Group>
        </>
      );

      default: return null;
    }
  }

  if (loading) return (
    <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', background: '#f2f2f2' }}>
      <span style={{ fontSize: 12, color: '#595959' }}>Reading file...</span>
    </div>
  );
  if (error) return (
    <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', background: '#f2f2f2' }}>
      <span style={{ fontSize: 12, color: '#cc0000' }}>{error}</span>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#ffffff', fontFamily: 'Calibri, Arial, sans-serif' }}>

      {/* Hidden file input */}
      <input ref={fileInputRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: 'none' }} onChange={handleFileInputChange} />

      {/* RIBBON */}
      <div style={{ background: '#f3f3f3', borderBottom: '1px solid #d0d0d0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', height: 28, paddingLeft: 4 }}>
          {RIBBON_TABS.map(tab => (
            <button key={tab} onClick={() => setActiveRibbonTab(tab)} style={{
              padding: '0 16px', fontSize: 11, cursor: 'pointer', height: 28,
              display: 'flex', alignItems: 'center',
              background: activeRibbonTab === tab ? '#ffffff' : 'transparent',
              color: activeRibbonTab === tab ? '#217346' : '#444',
              fontWeight: activeRibbonTab === tab ? 600 : 400,
              borderTop: activeRibbonTab === tab ? '2px solid #217346' : '2px solid transparent',
              borderLeft: activeRibbonTab === tab ? '1px solid #d0d0d0' : '1px solid transparent',
              borderRight: activeRibbonTab === tab ? '1px solid #d0d0d0' : '1px solid transparent',
              borderBottom: 'none', marginBottom: activeRibbonTab === tab ? -1 : 0,
              outline: 'none', whiteSpace: 'nowrap',
            }}
            onMouseEnter={e => { if (activeRibbonTab !== tab) (e.currentTarget as HTMLButtonElement).style.background = '#e8e8e8'; }}
            onMouseLeave={e => { if (activeRibbonTab !== tab) (e.currentTarget as HTMLButtonElement).style.background = 'transparent'; }}
            >{tab}</button>
          ))}
        </div>
        <div style={{ background: '#ffffff', borderBottom: '1px solid #d0d0d0', height: 40, padding: '0 8px', display: 'flex', alignItems: 'center', gap: 2, overflowX: 'auto' }}>
          {renderRibbonContent()}
        </div>
      </div>

      {/* FORMULA BAR */}
      <div style={{ height: 28, background: '#f2f2f2', borderBottom: '1px solid #d0d0d0', display: 'flex', alignItems: 'center', flexShrink: 0 }}>
        <div style={{ width: 60, borderRight: '1px solid #d0d0d0', textAlign: 'center', fontSize: 12, color: '#212121', padding: '0 4px', flexShrink: 0 }}>{cellRef}</div>
        <span style={{ padding: '0 8px', fontSize: 11, fontStyle: 'italic', color: '#595959', flexShrink: 0 }}>fx</span>
        <input
          value={formulaBarValue}
          onChange={e => { setFormulaBarValue(e.target.value); if (selectedCell) updateCellInState(selectedCell.row, selectedCell.col, e.target.value); }}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              e.preventDefault();
              if (selectedCell) { const orig = getCellValue(selectedCell.row, selectedCell.col); if (formulaBarValue !== orig) saveCell(selectedCell.row, selectedCell.col, formulaBarValue); }
              gridRef.current?.focus();
            } else if (e.key === 'Escape') {
              if (selectedCell) { const orig = getCellValue(selectedCell.row, selectedCell.col); setFormulaBarValue(orig); updateCellInState(selectedCell.row, selectedCell.col, orig); }
              gridRef.current?.focus();
            }
          }}
          style={{ flex: 1, border: 'none', outline: 'none', background: '#ffffff', fontSize: 12, padding: '0 8px', height: '100%', color: '#212121' }}
        />
      </div>

      {/* SHEET TABS */}
      <div style={{ height: 24, background: '#f2f2f2', borderTop: '1px solid #d0d0d0', display: 'flex', alignItems: 'flex-end', paddingLeft: 4, gap: 2, flexShrink: 0, overflowX: 'auto' }}>
        {(['‹','›'] as const).map(ch => (
          <button key={ch} style={{ width: 24, height: 24, background: 'transparent', border: 'none', color: '#595959', fontSize: 14, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 2, flexShrink: 0 }}
            onMouseEnter={e => (e.currentTarget.style.background = '#e0e0e0')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >{ch}</button>
        ))}
        {Array.from(sheets.keys()).map(name => (
          <button key={name} onClick={() => { setActiveSheet(name); setSelectedCell(null); setFormulaBarValue(''); }}
            style={{ height: 22, padding: '0 12px', fontSize: 11, cursor: 'pointer', borderRadius: '2px 2px 0 0', whiteSpace: 'nowrap', outline: 'none', display: 'flex', alignItems: 'center', background: activeSheet === name ? '#ffffff' : '#e8e8e8', color: activeSheet === name ? '#212121' : '#595959', fontWeight: activeSheet === name ? 600 : 400, border: activeSheet === name ? '1px solid #d0d0d0' : '1px solid transparent', borderBottom: activeSheet === name ? '2px solid #217346' : '1px solid transparent' }}
            onMouseEnter={e => { if (activeSheet !== name) { (e.currentTarget as HTMLButtonElement).style.background = '#d8d8d8'; (e.currentTarget as HTMLButtonElement).style.borderColor = '#d0d0d0'; } }}
            onMouseLeave={e => { if (activeSheet !== name) { (e.currentTarget as HTMLButtonElement).style.background = '#e8e8e8'; (e.currentTarget as HTMLButtonElement).style.borderColor = 'transparent'; } }}
          >{name}</button>
        ))}
        <button onClick={() => showToast('Add sheet')} style={{ width: 24, height: 24, background: 'transparent', border: 'none', color: '#595959', fontSize: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 2, flexShrink: 0 }}
          onMouseEnter={e => (e.currentTarget.style.background = '#e0e0e0')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
        >+</button>
      </div>

      {/* FILTER BAR */}
      {filterActive && (
        <div style={{ display: 'flex', alignItems: 'center', height: 26, background: '#f9f9f9', borderBottom: '1px solid #d0d0d0', padding: '0 8px', flexShrink: 0, gap: 6 }}>
          <span style={{ fontSize: 10, color: '#595959', flexShrink: 0 }}>Filter {selectedCell ? colIndexToLabel(selectedCell.col) : ''}:</span>
          <input
            value={filterValue}
            onChange={e => setFilterValue(e.target.value)}
            placeholder={`Filter column ${selectedCell ? colIndexToLabel(selectedCell.col) : ''}...`}
            style={{ flex: 1, height: 20, fontSize: 11, border: '1px solid #ababab', borderRadius: 2, padding: '0 6px', outline: 'none' }}
          />
        </div>
      )}

      {/* GRID */}
      <div ref={gridRef} tabIndex={0} onKeyDown={handleKeyDown}
        style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', outline: 'none', position: 'relative' }}
      >
        {/* Column headers (frozen top) */}
        <div style={{ display: 'flex', flexShrink: 0 }}>
          <div style={{ width: ROW_NUM_WIDTH, minWidth: ROW_NUM_WIDTH, maxWidth: ROW_NUM_WIDTH, height: 24, flexShrink: 0, background: '#f2f2f2', borderRight: '1px solid #a0a0a0', borderBottom: '1px solid #a0a0a0' }} />
          <div ref={colHeaderRef} style={{ flex: 1, overflowX: 'hidden', display: 'flex', borderBottom: '1px solid #a0a0a0' }}>
            {Array.from({ length: totalCols }).map((_, ci) => {
              const colSel = selectedCell?.col === ci || (selectionRange && ci >= Math.min(selectionRange.start.col, selectionRange.end.col) && ci <= Math.max(selectionRange.start.col, selectionRange.end.col));
              return (
                <div key={ci} style={{ width: COL_WIDTH, minWidth: COL_WIDTH, maxWidth: COL_WIDTH, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: colSel ? '#2566c8' : '#595959', background: colSel ? '#cce8ff' : '#f2f2f2', borderRight: '1px solid #d0d0d0', flexShrink: 0, userSelect: 'none' }}>
                  {colIndexToLabel(ci)}
                </div>
              );
            })}
          </div>
        </div>

        {/* Scrollable body */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', position: 'relative' }}>
          {/* Row numbers (frozen left) */}
          <div ref={rowNumRef} style={{ width: ROW_NUM_WIDTH, minWidth: ROW_NUM_WIDTH, maxWidth: ROW_NUM_WIDTH, overflowY: 'hidden', flexShrink: 0 }}>
            {filteredBody.map((_, ri) => {
              const rowSel = selectedCell?.row === ri || (selectionRange && ri >= Math.min(selectionRange.start.row, selectionRange.end.row) && ri <= Math.max(selectionRange.start.row, selectionRange.end.row));
              const isFrozenRow = frozenRows > 0 && ri < frozenRows;
              return (
                <div key={ri} style={{ width: ROW_NUM_WIDTH, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: rowSel ? '#2566c8' : '#595959', background: isFrozenRow ? '#fffde7' : rowSel ? '#cce8ff' : '#f2f2f2', borderRight: '1px solid #a0a0a0', borderBottom: '1px solid #d0d0d0', userSelect: 'none', flexShrink: 0, ...(isFrozenRow ? { position: 'sticky' as const, top: 0, zIndex: 2 } : {}) }}>
                  {ri + 1}
                </div>
              );
            })}
          </div>

          {/* Data cells */}
          <div ref={dataGridRef} onScroll={handleDataScroll} style={{ flex: 1, overflow: 'auto', position: 'relative' }}>
            {/* Canvas overlay */}
            <canvas
              ref={canvasRef}
              width={totalCols * COL_WIDTH}
              height={filteredBody.length * 22}
              style={{ position: 'absolute', top: 0, left: 0, zIndex: 10, pointerEvents: drawTool ? 'all' : 'none', cursor: drawTool ? 'crosshair' : 'default' }}
              onMouseDown={handleCanvasMouseDown}
              onMouseMove={handleCanvasMouseMove}
              onMouseUp={handleCanvasMouseUp}
              onMouseLeave={handleCanvasMouseUp}
            />

            <div style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top left', width: `${100 * 100 / zoom}%` }}>
              {filteredBody.map((row, ri) => (
                <div key={ri} style={{ display: 'flex' }}>
                  {Array.from({ length: totalCols }).map((_, ci) => {
                    const val = row[ci];
                    const valStr = val != null && val !== '' ? String(val) : '';
                    const isSelected = selectedCell?.row === ri && selectedCell?.col === ci;
                    const isActive = activeCell?.row === ri && activeCell?.col === ci;
                    const inRange = isInRange(ri, ci);
                    const style = getCellStyle(ri, ci);
                    const isFrozenRow = frozenRows > 0 && ri < frozenRows;
                    const isFrozenCol = frozenCols > 0 && ci < frozenCols;
                    const commentK = cellKey(activeSheet, ri, ci);
                    const hasComment = comments.has(commentK);
                    const isHoveredComment = hoveredCommentCell?.row === ri && hoveredCommentCell?.col === ci;

                    const cellStyle: React.CSSProperties = {
                      width: COL_WIDTH, minWidth: COL_WIDTH, maxWidth: COL_WIDTH,
                      height: style.wrap ? 'auto' : 22, flexShrink: 0,
                      borderRight: showGridlines ? '1px solid #d0d0d0' : '1px solid transparent',
                      borderBottom: showGridlines ? '1px solid #d0d0d0' : '1px solid transparent',
                      padding: '0 6px', fontSize: style.fontSize ? `${style.fontSize}px` : 12,
                      color: style.color ?? '#212121',
                      overflow: 'hidden', textOverflow: 'ellipsis',
                      whiteSpace: style.wrap ? 'normal' : 'nowrap',
                      cursor: isActive ? 'text' : 'cell',
                      fontWeight: style.bold ? 'bold' : 'normal',
                      fontStyle: style.italic ? 'italic' : 'normal',
                      textDecoration: style.underline ? 'underline' : 'none',
                      textAlign: style.align ?? 'left',
                      fontFamily: style.fontFamily ?? 'inherit',
                      backgroundColor: style.background ?? (isFrozenRow || isFrozenCol ? '#fffde7' : isActive ? '#ffffff' : isSelected ? 'rgba(204,232,255,0.3)' : inRange ? 'rgba(204,232,255,0.5)' : '#ffffff'),
                      outline: isSelected || isActive ? '2px solid #2566c8' : 'none',
                      outlineOffset: '-2px', boxSizing: 'border-box',
                      display: 'flex', alignItems: 'center', position: 'relative',
                      ...(isFrozenRow ? { position: 'sticky' as const, top: 0, zIndex: 2 } : {}),
                      ...(isFrozenCol ? { position: 'sticky' as const, left: ci * COL_WIDTH + ROW_NUM_WIDTH, zIndex: 2 } : {}),
                    };

                    if (isActive) return (
                      <div key={ci} style={cellStyle}>
                        <input
                          ref={activeCellInputRef}
                          value={activeCellEditValue}
                          onChange={e => { setActiveCellEditValue(e.target.value); setFormulaBarValue(e.target.value); }}
                          onKeyDown={e => {
                            if (e.key === 'Enter') { e.preventDefault(); commitEdit(ri, ci, activeCellEditValue, valStr); moveSelection(1, 0); }
                            else if (e.key === 'Escape') { e.preventDefault(); setActiveCell(null); setActiveCellEditValue(''); setTimeout(() => gridRef.current?.focus(), 0); }
                            else if (e.key === 'Tab') { e.preventDefault(); commitEdit(ri, ci, activeCellEditValue, valStr); moveSelection(0, e.shiftKey ? -1 : 1); }
                          }}
                          onBlur={() => commitEdit(ri, ci, activeCellEditValue, valStr)}
                          style={{ width: '100%', border: 'none', outline: 'none', background: 'transparent', fontSize: style.fontSize ?? 12, fontFamily: style.fontFamily ?? 'inherit', fontWeight: style.bold ? 'bold' : undefined, fontStyle: style.italic ? 'italic' : undefined, textDecoration: style.underline ? 'underline' : undefined, textAlign: style.align ?? 'left', color: style.color ?? '#212121', padding: 0 }}
                        />
                      </div>
                    );

                    return (
                      <div key={ci} style={cellStyle}
                        onClick={() => selectCell(ri, ci)}
                        onDoubleClick={() => enterEditMode(ri, ci)}
                        onMouseEnter={e => {
                          if (hasComment && showComments) setHoveredCommentCell({ row: ri, col: ci });
                          if (!isSelected && !isActive && !inRange && !style.background) (e.currentTarget as HTMLDivElement).style.backgroundColor = '#e8f0fe';
                        }}
                        onMouseLeave={e => {
                          setHoveredCommentCell(null);
                          if (!isSelected && !isActive && !inRange && !style.background) (e.currentTarget as HTMLDivElement).style.backgroundColor = '#ffffff';
                        }}
                      >
                        {showFormulas ? valStr : valStr}
                        {hasComment && showComments && (
                          <div style={{ position: 'absolute', top: 0, right: 0, width: 0, height: 0, borderStyle: 'solid', borderWidth: '0 6px 6px 0', borderColor: 'transparent #cc0000 transparent transparent' }} />
                        )}
                        {isHoveredComment && showComments && (
                          <div style={{ position: 'absolute', top: 22, left: 0, background: '#ffffc0', border: '1px solid #cc0000', padding: '4px 8px', fontSize: 11, zIndex: 100, maxWidth: 200, whiteSpace: 'pre-wrap', pointerEvents: 'none' }}>
                            {comments.get(commentK)}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* STATUS BAR */}
      <div style={{ height: 20, background: '#f2f2f2', borderTop: '1px solid #d0d0d0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 12px', flexShrink: 0 }}>
        <span style={{ fontSize: 10, color: '#595959' }}>
          {selectionRange
            ? `${(Math.abs(selectionRange.end.row - selectionRange.start.row) + 1) * (Math.abs(selectionRange.end.col - selectionRange.start.col) + 1)} cells selected`
            : selectedCell ? `Cell ${cellRef}` : `${totalRows} rows`}
        </span>
        {saveStatus !== 'idle' && (
          <span style={{ fontSize: 10, color: saveStatus === 'saving' ? '#595959' : saveStatus === 'saved' ? '#217346' : '#cc0000' }}>
            {saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? 'Saved ✓' : 'Save failed'}
          </span>
        )}
      </div>

      {/* TOAST */}
      {toastMessage && (
        <div style={{ position: 'fixed', bottom: 24, right: 24, background: '#323130', color: '#ffffff', fontSize: 12, padding: '8px 12px', borderRadius: 4, zIndex: 1000, pointerEvents: 'none' }}>
          {toastMessage}
        </div>
      )}
    </div>
  );
}
