'use client';

import { useCallback, useEffect, useState } from 'react';
import { deleteFile, getFiles, uploadFile } from '../lib/api';
import type { UploadedFile } from '../lib/types';

export function useFiles() {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const fetchFiles = useCallback(async () => {
    try {
      const data = await getFiles();
      setFiles(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch files');
    } finally {
      setLoading(false);
    }
  }, []);

  const upload = useCallback(
    async (file: File): Promise<UploadedFile | null> => {
      setUploading(true);
      try {
        const uploaded = await uploadFile(file);
        const els = uploaded.indexed_elements;
        if (els && els.length > 0) {
          const parts = els.map((e) =>
            e.designation ? `${e.type} (${e.designation})` : e.type
          );
          setNotice(
            `Ready. ${els.length} element${els.length === 1 ? '' : 's'} indexed: ${parts.join(', ')}.`
          );
        }
        await fetchFiles();
        return uploaded;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed');
        return null;
      } finally {
        setUploading(false);
      }
    },
    [fetchFiles]
  );

  const remove = useCallback(
    async (file_id: string): Promise<void> => {
      try {
        await deleteFile(file_id);
        await fetchFiles();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Delete failed');
      }
    },
    [fetchFiles]
  );

  const clearError = useCallback(() => setError(null), []);
  const clearNotice = useCallback(() => setNotice(null), []);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  // While any file is still indexing (rag_status pending), poll for updates.
  useEffect(() => {
    if (!files.some((f) => f.rag_status === 'pending')) return;
    const timer = setInterval(fetchFiles, 3000);
    return () => clearInterval(timer);
  }, [files, fetchFiles]);

  return {
    files, loading, error, notice, uploading,
    fetchFiles, upload, remove, clearError, clearNotice,
  };
}
