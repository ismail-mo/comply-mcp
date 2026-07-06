'use client';

import { memo, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import type { UploadedFile } from '../lib/types';

interface FileSidebarProps {
  files: UploadedFile[];
  loading: boolean;
  uploading: boolean;
  activeFile: UploadedFile | null;
  onSelect: (file: UploadedFile) => void;
  onUpload: (file: File) => Promise<UploadedFile | null>;
  onDelete: (file_id: string) => Promise<void>;
  error: string | null;
  clearError: () => void;
}

interface FileItemProps {
  file: UploadedFile;
  active: boolean;
  onSelect: (file: UploadedFile) => void;
  onDelete: (file_id: string) => Promise<void>;
}

function FileItem({ file, active, onSelect, onDelete }: FileItemProps) {
  const isPdf = file.type === 'pdf';

  return (
    <div
      className="group relative flex w-full cursor-pointer items-center gap-2 px-3 py-2 transition-colors duration-150"
      style={{
        borderLeft: `2px solid ${active ? 'var(--accent)' : 'transparent'}`,
        background: active ? 'var(--bg-hover)' : 'transparent',
      }}
      onMouseEnter={(e) => {
        if (!active) (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-hover)';
      }}
      onMouseLeave={(e) => {
        if (!active) (e.currentTarget as HTMLDivElement).style.background = 'transparent';
      }}
      onClick={() => onSelect(file)}
    >
      <span
        className="shrink-0 text-base leading-none"
        style={{ color: isPdf ? 'var(--danger)' : 'var(--success)' }}
      >
        ▪
      </span>

      <div className="min-w-0 flex-1">
        <p
          className="truncate text-[12px] leading-snug"
          style={{ color: 'var(--text-primary)' }}
        >
          {file.filename}
        </p>
        <p
          className="text-[9px] uppercase leading-tight"
          style={{ color: isPdf ? 'var(--danger)' : 'var(--success)' }}
        >
          {isPdf ? 'PDF' : 'XLS'}
        </p>
      </div>

      {file.rag_status === 'pending' && (
        <span
          className="shrink-0 animate-pulse text-[8px] uppercase"
          style={{ color: 'var(--warning)' }}
          title="Indexing document for search…"
        >
          ●
        </span>
      )}
      {file.rag_status === 'failed' && (
        <span
          className="shrink-0 text-[8px] uppercase"
          style={{ color: 'var(--danger)' }}
          title={`Indexing failed${file.rag_error ? `: ${file.rag_error}` : ''}`}
        >
          ●
        </span>
      )}
      <span
        className="shrink-0 text-[8px] uppercase px-1.5 py-0.5"
        style={
          file.classification === 'STANDARD'
            ? { color: '#a78bfa', border: '1px solid rgba(167, 139, 250, 0.45)' }
            : file.classification === 'UNKNOWN'
              ? { color: 'var(--text-muted)', border: '1px solid var(--border)' }
              : { color: 'var(--accent)', border: '1px solid rgba(232, 240, 74, 0.4)' }
        }
        title={
          file.classification === 'STANDARD'
            ? 'Standard document'
            : file.classification === 'UNKNOWN'
              ? 'Unclassified document'
              : 'Project document'
        }
      >
        {file.classification === 'STANDARD' ? 'STD' : file.classification === 'UNKNOWN' ? 'UNK' : 'PRJ'}
      </span>

      <button
        className="shrink-0 text-[14px] leading-none opacity-0 transition-opacity group-hover:opacity-100"
        style={{ color: 'var(--text-muted)' }}
        onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.color = 'var(--danger)')}
        onMouseLeave={(e) =>
          ((e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)')
        }
        onClick={(e) => {
          e.stopPropagation();
          onDelete(file.file_id);
        }}
      >
        ×
      </button>
    </div>
  );
}

export const FileSidebar = memo(function FileSidebar({
  files,
  loading,
  uploading,
  activeFile,
  onSelect,
  onUpload,
  onDelete,
  error,
  clearError,
}: FileSidebarProps) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length > 0 && !uploading) {
        onUpload(accepted[0]);
      }
    },
    [onUpload, uploading]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'text/csv': ['.csv'],
    },
    multiple: false,
    disabled: uploading,
  });

  return (
    <div className="flex h-full w-full flex-col" style={{ background: 'var(--bg-panel)' }}>
      {/* Header */}
      <div
        className="shrink-0 px-4 py-3"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <span
          className="text-[10px] uppercase tracking-widest"
          style={{ color: 'var(--text-secondary)' }}
        >
          Files
        </span>
      </div>

      {/* Error bar */}
      {error && (
        <div
          className="shrink-0 flex items-center justify-between px-3 py-2"
          style={{
            background: 'rgba(248, 113, 113, 0.15)',
            borderBottom: '1px solid rgba(248, 113, 113, 0.4)',
          }}
        >
          <span className="text-[11px]" style={{ color: 'var(--danger)' }}>
            {error}
          </span>
          <button
            className="ml-2 shrink-0 text-[14px] leading-none"
            style={{ color: 'var(--danger)' }}
            onClick={clearError}
          >
            ×
          </button>
        </div>
      )}

      {/* File list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <p
            className="p-4 text-center text-[11px]"
            style={{ color: 'var(--text-muted)' }}
          >
            Loading...
          </p>
        ) : files.length === 0 ? (
          <p
            className="p-4 text-center text-[11px]"
            style={{ color: 'var(--text-muted)' }}
          >
            No files uploaded
          </p>
        ) : (
          files.map((file) => (
            <FileItem
              key={file.file_id}
              file={file}
              active={activeFile?.file_id === file.file_id}
              onSelect={onSelect}
              onDelete={onDelete}
            />
          ))
        )}
      </div>

      {/* Upload zone */}
      <div
        className="shrink-0"
        style={{ borderTop: '1px solid var(--border)', height: '110px' }}
      >
        <div
          {...getRootProps()}
          className="flex h-full cursor-pointer flex-col items-center justify-center gap-1 m-2 rounded"
          style={{
            border: `1px dashed ${isDragActive ? 'var(--accent)' : 'var(--border)'}`,
            background: isDragActive ? 'var(--accent-dim)' : 'var(--bg-base)',
            transition: 'border-color 150ms, background 150ms',
          }}
        >
          <input {...getInputProps()} />
          {uploading ? (
            <p
              className="animate-pulse text-[11px]"
              style={{ color: 'var(--accent)' }}
            >
              Uploading...
            </p>
          ) : (
            <>
              <span
                className="text-[18px] leading-none"
                style={{ color: 'var(--text-muted)' }}
              >
                ↑
              </span>
              <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                Drop file here
              </p>
              <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                PDF, Excel
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
});
