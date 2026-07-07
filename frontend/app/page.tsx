'use client';

import { useState } from 'react';
import { FileSidebar } from '../components/FileSidebar';
import { FileViewer } from '../components/FileViewer';
import { Splitter } from '../components/Splitter';
import { useChat } from '../hooks/useChat';
import { useFiles } from '../hooks/useFiles';
import type { ActiveCitation, UploadedFile } from '../lib/types';
import ChatSidebar from '../components/ChatSidebar';

const LEFT_DEFAULT = 250;
const LEFT_MIN = 170;
const LEFT_MAX = 400;
const RIGHT_DEFAULT = 430;
const RIGHT_MIN = 320;
const RIGHT_MAX = 760;

export default function Page() {
  const [activeFile, setActiveFile] = useState<UploadedFile | null>(null);
  const [activeCitation, setActiveCitation] = useState<ActiveCitation | null>(null);
  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT);
  const [rightWidth, setRightWidth] = useState(RIGHT_DEFAULT);

  const {
    files, loading, uploading, upload, remove,
    error, clearError, notice, clearNotice,
  } = useFiles();
  const { messages, sendMessage, clearHistory, streaming } = useChat();

  const handleDelete = async (file_id: string) => {
    await remove(file_id);
    if (activeFile?.file_id === file_id) {
      setActiveFile(null);
    }
  };

  const handleUpload = async (file: File): Promise<UploadedFile | null> => {
    return upload(file);
  };

  const handleCitationClick = (citation: ActiveCitation) => {
    setActiveCitation(citation);
  };

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: 'var(--surface-0)' }}
    >
      <div style={{ width: leftWidth, flexShrink: 0 }} className="overflow-hidden">
        <FileSidebar
          files={files}
          loading={loading}
          uploading={uploading}
          activeFile={activeFile}
          onSelect={setActiveFile}
          onUpload={handleUpload}
          onDelete={handleDelete}
          error={error}
          clearError={clearError}
          notice={notice}
          clearNotice={clearNotice}
        />
      </div>

      <Splitter
        side="left"
        width={leftWidth}
        min={LEFT_MIN}
        max={LEFT_MAX}
        onResize={setLeftWidth}
      />

      <div className="flex-1 min-w-0 overflow-hidden" style={{ minWidth: 300 }}>
        <FileViewer
          activeFile={activeFile}
          activeCitation={activeCitation}
          files={files}
          onViewerSwitch={setActiveFile}
        />
      </div>

      <Splitter
        side="right"
        width={rightWidth}
        min={RIGHT_MIN}
        max={RIGHT_MAX}
        onResize={setRightWidth}
      />

      <div style={{ width: rightWidth, flexShrink: 0 }} className="overflow-hidden">
        <ChatSidebar
          activeFile={activeFile}
          messages={messages}
          onSend={(msg, visibleMsg) =>
            sendMessage(msg, visibleMsg, activeFile?.file_id ?? null)
          }
          streaming={streaming}
          onClearHistory={clearHistory}
          onCitationClick={handleCitationClick}
        />
      </div>
    </div>
  );
}
