'use client';

import type { ActiveCitation } from '../lib/types';

interface PdfViewerProps {
  fileId: string;
  activeCitation: ActiveCitation | null;
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export function PdfViewer({ fileId }: PdfViewerProps) {
  const fileUrl = `${BASE_URL}/uploads/${encodeURIComponent(fileId)}`;

  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column' }}>
      <iframe
        src={fileUrl}
        style={{ flex: 1, border: 'none', width: '100%' }}
        title="PDF Viewer"
      />
    </div>
  );
}
