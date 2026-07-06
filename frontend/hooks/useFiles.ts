'use client';

import { useCallback, useEffect, useState } from 'react';
import { deleteFile, getFiles, uploadFile } from '../lib/api';
import type { UploadedFile } from '../lib/types';

export function useFiles() {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  return { files, loading, error, uploading, fetchFiles, upload, remove, clearError };
}
