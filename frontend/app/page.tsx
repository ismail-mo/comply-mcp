'use client';

import { useState } from 'react';
import { FileSidebar } from '../components/FileSidebar';
import { FileViewer } from '../components/FileViewer';
import { useChat } from '../hooks/useChat';
import { useFiles } from '../hooks/useFiles';
import type { ActiveCitation, UploadedFile } from '../lib/types';
import ChatSidebar from '../components/ChatSidebar';

export default function Page() {
  const [activeFile, setActiveFile] = useState<UploadedFile | null>(null);
  const [activeCitation, setActiveCitation] = useState<ActiveCitation | null>(null);

  const { files, loading, uploading, upload, remove, error, clearError } = useFiles();
  const { messages, sendMessage, injectFileContext, clearHistory, streaming } = useChat();

  const handleDelete = async (file_id: string) => {
    await remove(file_id);
    if (activeFile?.file_id === file_id) {
      setActiveFile(null);
    }
  };

  const handleUpload = async (file: File): Promise<UploadedFile | null> => {
    const uploaded = await upload(file);
    if (uploaded) {
      injectFileContext(uploaded);
    }
    return uploaded;
  };

  const handleCitationClick = (citation: ActiveCitation) => {
    setActiveCitation(citation);
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="w-[260px] shrink-0 border-r border-[var(--border)]">
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
        />
      </div>

      <div className="flex-1 overflow-hidden">
        <FileViewer
          activeFile={activeFile}
          activeCitation={activeCitation}
          files={files}
          onViewerSwitch={setActiveFile}
        />
      </div>

      <div className="w-[380px] shrink-0 border-l border-[var(--border)]">
        <ChatSidebar
          activeFile={activeFile}
          messages={messages}
          onSend={(msg, visibleMsg) => sendMessage(msg, visibleMsg, activeFile?.file_id ?? null, files)}
          streaming={streaming}
          onClearHistory={clearHistory}
          onCitationClick={handleCitationClick}
        />
      </div>
    </div>
  );
}
