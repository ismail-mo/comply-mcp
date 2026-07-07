'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Viewer,
  Worker,
  SpecialZoomLevel,
  type RenderPageProps,
} from '@react-pdf-viewer/core';
import { pageNavigationPlugin } from '@react-pdf-viewer/page-navigation';
import { zoomPlugin } from '@react-pdf-viewer/zoom';
import '@react-pdf-viewer/core/lib/styles/index.css';
import type { ActiveCitation, PdfCoordinates, PdfWord } from '../lib/types';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface PdfViewerProps {
  fileId: string;
  activeCitation: ActiveCitation | null;
}

interface HighlightRect {
  // Percentages of the page dimensions — zoom-independent.
  left: number;
  top: number;
  width: number;
  height: number;
}

const normalize = (value: string): string =>
  value.toLowerCase().replace(/[^a-z0-9]/g, '');

const tokenize = (phrase: string): string[] =>
  phrase.split(/\s+/).map(normalize).filter(Boolean);

/** Find the first index where the token sequence matches the page words. */
function matchSequence(words: PdfWord[], tokens: string[], from = 0): number {
  if (tokens.length === 0) return -1;
  outer: for (let i = from; i <= words.length - tokens.length; i++) {
    for (let j = 0; j < tokens.length; j++) {
      const w = normalize(words[i + j].text);
      if (w !== tokens[j] && !w.includes(tokens[j]) && !tokens[j].includes(w)) {
        continue outer;
      }
    }
    return i;
  }
  return -1;
}

/** Locate the word range for a citation, shrinking the phrases if needed. */
function findWordRange(
  words: PdfWord[],
  startPhrase: string,
  endPhrase: string
): [number, number] | null {
  const startTokens = tokenize(startPhrase);
  const endTokens = tokenize(endPhrase);

  let startIdx = -1;
  let startLen = 0;
  for (let take = Math.min(5, startTokens.length); take >= 2; take--) {
    startIdx = matchSequence(words, startTokens.slice(0, take));
    if (startIdx !== -1) {
      startLen = take;
      break;
    }
  }
  if (startIdx === -1) return null;

  let endIdx = -1;
  let endLen = 0;
  for (let take = Math.min(5, endTokens.length); take >= 2; take--) {
    const tokens = endTokens.slice(-take);
    endIdx = matchSequence(words, tokens, startIdx);
    if (endIdx !== -1 && endIdx - startIdx < 220) {
      endLen = take;
      break;
    }
    endIdx = -1;
  }

  const last = endIdx !== -1 ? endIdx + endLen - 1 : startIdx + startLen - 1;
  return [startIdx, last];
}

/** Merge a run of words into one rect per text line (percent coordinates). */
function buildRects(
  words: PdfWord[],
  range: [number, number],
  pageWidth: number,
  pageHeight: number
): HighlightRect[] {
  const slice = words.slice(range[0], range[1] + 1);
  if (slice.length === 0) return [];

  const lines: PdfWord[][] = [];
  for (const word of slice) {
    const line = lines[lines.length - 1];
    if (line) {
      const ref = line[0];
      const mid = (word.y0 + word.y1) / 2;
      if (mid >= ref.y0 - 2 && mid <= ref.y1 + 2) {
        line.push(word);
        continue;
      }
    }
    lines.push([word]);
  }

  return lines.map((line) => {
    const x0 = Math.min(...line.map((w) => w.x0));
    const x1 = Math.max(...line.map((w) => w.x1));
    const y0 = Math.min(...line.map((w) => w.y0));
    const y1 = Math.max(...line.map((w) => w.y1));
    const padX = 1.5;
    const padY = 1;
    return {
      left: Math.max(0, ((x0 - padX) / pageWidth) * 100),
      top: Math.max(0, ((y0 - padY) / pageHeight) * 100),
      width: Math.min(100, ((x1 - x0 + padX * 2) / pageWidth) * 100),
      height: Math.min(100, ((y1 - y0 + padY * 2) / pageHeight) * 100),
    };
  });
}

const toolbarButtonStyle: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border-strong)',
  color: 'var(--text-secondary)',
  width: 24,
  height: 22,
  fontSize: 12,
  lineHeight: 1,
  cursor: 'pointer',
  borderRadius: 3,
};

export function PdfViewer({ fileId, activeCitation }: PdfViewerProps) {
  const fileUrl = `${BASE_URL}/uploads/${encodeURIComponent(fileId)}`;

  const [coords, setCoords] = useState<PdfCoordinates | null>(null);
  const [docLoaded, setDocLoaded] = useState(false);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [notice, setNotice] = useState<string | null>(null);
  const [scale, setScale] = useState<number | null>(null); // null = fit width
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Plugin factories call hooks internally — invoke at the top level.
  const pageNavigation = pageNavigationPlugin();
  const zoom = zoomPlugin();

  // Reset per-file state when the displayed file changes.
  useEffect(() => {
    setCoords(null);
    setDocLoaded(false);
    setPageCount(0);
    setCurrentPage(1);
    setNotice(null);
    setScale(null);

    let cancelled = false;
    fetch(`${BASE_URL}/files/${encodeURIComponent(fileId)}/coordinates`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled) setCoords(data);
      })
      .catch(() => {
        if (!cancelled) setCoords(null);
      });
    return () => {
      cancelled = true;
    };
  }, [fileId]);

  const showNotice = useCallback((text: string) => {
    setNotice(text);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), 3200);
  }, []);

  // Compute highlight rects for the active citation.
  const highlight = useMemo(() => {
    if (!activeCitation || activeCitation.file_id !== fileId || !coords) return null;
    const page = coords.pages?.[String(activeCitation.page)];
    if (!page || !page.words?.length) return null;
    const range = findWordRange(
      page.words,
      activeCitation.highlight_start || '',
      activeCitation.highlight_end || ''
    );
    if (!range) return null;
    return {
      pageIndex: activeCitation.page - 1,
      rects: buildRects(page.words, range, page.width, page.height),
    };
  }, [activeCitation, coords, fileId]);

  // Navigate to the cited page once the document is ready.
  useEffect(() => {
    if (!activeCitation || activeCitation.file_id !== fileId || !docLoaded) return;
    const target = Math.min(Math.max(activeCitation.page - 1, 0), Math.max(pageCount - 1, 0));
    pageNavigation.jumpToPage(target);
    if (coords && !highlight) {
      showNotice('Cited text could not be located on the page');
    } else if (!coords) {
      showNotice('No highlight data for this document');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCitation, docLoaded, fileId]);

  const applyZoom = useCallback(
    (next: number | null) => {
      setScale(next);
      zoom.zoomTo(next ?? SpecialZoomLevel.PageWidth);
    },
    [zoom]
  );

  const renderPage = useCallback(
    (props: RenderPageProps) => (
      <>
        {props.canvasLayer.children}
        {highlight && props.pageIndex === highlight.pageIndex && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              pointerEvents: 'none',
              zIndex: 2,
            }}
          >
            {highlight.rects.map((rect, index) => (
              <div
                key={index}
                className="comply-highlight"
                style={{
                  position: 'absolute',
                  left: `${rect.left}%`,
                  top: `${rect.top}%`,
                  width: `${rect.width}%`,
                  height: `${rect.height}%`,
                  background: 'rgba(24, 95, 165, 0.22)',
                  outline: '1px solid rgba(24, 95, 165, 0.65)',
                  borderRadius: 2,
                  mixBlendMode: 'multiply',
                }}
              />
            ))}
          </div>
        )}
        {props.textLayer.children}
        {props.annotationLayer.children}
      </>
    ),
    [highlight]
  );

  return (
    <div
      style={{
        height: '100%',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--surface-0)',
      }}
    >
      <style>{`
        @keyframes comply-highlight-pulse {
          0% { box-shadow: 0 0 0 6px rgba(24, 95, 165, 0.35); }
          100% { box-shadow: 0 0 0 0 rgba(24, 95, 165, 0); }
        }
        .comply-highlight { animation: comply-highlight-pulse 1.2s ease-out 2; }
        .rpv-core__inner-page { background: var(--surface-0) !important; }
      `}</style>

      {/* Slim toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '4px 12px',
          borderBottom: '1px solid var(--border)',
          background: 'var(--surface-1)',
          flexShrink: 0,
          gap: 8,
        }}
      >
        <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
          {pageCount > 0 ? `Page ${currentPage} / ${pageCount}` : 'Loading…'}
        </span>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <button
            style={toolbarButtonStyle}
            onClick={() => applyZoom(Math.max(0.5, (scale ?? 1) - 0.2))}
            title="Zoom out"
          >
            −
          </button>
          <button
            style={{ ...toolbarButtonStyle, width: 'auto', padding: '0 8px', fontSize: 10 }}
            onClick={() => applyZoom(null)}
            title="Fit width"
          >
            FIT
          </button>
          <button
            style={toolbarButtonStyle}
            onClick={() => applyZoom(Math.min(3, (scale ?? 1) + 0.2))}
            title="Zoom in"
          >
            +
          </button>
        </div>
      </div>

      {/* Notice toast */}
      {notice && (
        <div
          style={{
            position: 'absolute',
            top: 48,
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'var(--surface-2)',
            border: '1px solid var(--border-strong)',
            color: 'var(--text-secondary)',
            fontSize: 11,
            padding: '6px 12px',
            borderRadius: 4,
            boxShadow: '0 2px 8px rgba(26, 26, 24, 0.10)',
            zIndex: 10,
          }}
        >
          {notice}
        </div>
      )}

      <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
        <Worker workerUrl="/pdf.worker.min.js">
          <Viewer
            fileUrl={fileUrl}
            defaultScale={SpecialZoomLevel.PageWidth}
            plugins={[pageNavigation, zoom]}
            renderPage={renderPage}
            theme="light"
            onDocumentLoad={(e) => {
              setDocLoaded(true);
              setPageCount(e.doc.numPages);
            }}
            onPageChange={(e) => setCurrentPage(e.currentPage + 1)}
            renderError={() => (
              <div
                style={{
                  display: 'flex',
                  height: '100%',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--fail-fg)',
                  fontSize: 12,
                }}
              >
                Failed to load PDF
              </div>
            )}
            renderLoader={() => (
              <div
                style={{
                  display: 'flex',
                  height: '100%',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--text-muted)',
                  fontSize: 12,
                }}
              >
                Loading document…
              </div>
            )}
          />
        </Worker>
      </div>
    </div>
  );
}
