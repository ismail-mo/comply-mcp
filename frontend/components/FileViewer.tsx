'use client';

import { memo, useEffect } from 'react';
import dynamic from 'next/dynamic';
import type { UploadedFile, ActiveCitation } from '../lib/types';

const PdfViewer = dynamic(() => import('./PdfViewer').then((m) => ({ default: m.PdfViewer })), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center">
      <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>Loading viewer...</span>
    </div>
  ),
});

const ExcelViewer = dynamic(
  () => import('./ExcelViewer').then((m) => ({ default: m.ExcelViewer })),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>Loading spreadsheet...</span>
      </div>
    ),
  }
);

interface FileViewerProps {
  activeFile: UploadedFile | null;
  activeCitation: ActiveCitation | null;
  files: UploadedFile[];
  onViewerSwitch: (file: UploadedFile) => void;
}

export const FileViewer = memo(function FileViewer({ activeFile, activeCitation, files, onViewerSwitch }: FileViewerProps) {
  useEffect(() => {
    if (!activeCitation) return;
    const citedFile = files.find((f) => f.file_id === activeCitation.file_id);
    if (!citedFile) return;
    if (!activeFile || activeFile.file_id !== citedFile.file_id) {
      onViewerSwitch(citedFile);
    }
  }, [activeCitation?.file_id, activeFile?.file_id, files, onViewerSwitch]);

  return (
    <div className="flex h-full flex-col" style={{ background: 'var(--surface-0)' }}>
      {/* Header */}
      <div
        className="flex shrink-0 items-center justify-between px-4 py-3"
        style={{ background: 'var(--surface-1)', borderBottom: '1px solid var(--border)' }}
      >
        <span
          className="text-[12px]"
          style={{ color: activeFile ? 'var(--text-primary)' : 'var(--text-muted)' }}
        >
          {activeFile ? activeFile.filename : 'COMPLY'}
        </span>

        {activeFile && (
          <span
            className="text-[9px] uppercase px-2 py-0.5 rounded"
            style={
              activeFile.type === 'pdf'
                ? { color: 'var(--fail-fg)', background: 'var(--fail-bg)' }
                : { color: 'var(--pass-fg)', background: 'var(--pass-bg)' }
            }
          >
            {activeFile.type === 'pdf' ? 'PDF' : 'XLS'}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {!activeFile ? (
          <div className="flex h-full flex-col items-center justify-center">
            <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
              No file selected
            </span>
            <span className="mt-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>
              Upload a file and select it to begin
            </span>
          </div>
        ) : activeFile.type === 'pdf' ? (
          <PdfViewer
            fileId={activeFile.file_id}
            activeCitation={activeCitation}
          />
        ) : (
          <ExcelViewer key={activeFile.file_id} fileId={activeFile.file_id} />
        )}
      </div>
    </div>
  );
});
