import type { ChatRequest, ChatStreamChunk, ComplianceRow, UploadedFile } from './types';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function getFiles(): Promise<UploadedFile[]> {
  const res = await fetch(`${BASE_URL}/files`);
  if (!res.ok) throw new Error(`Failed to fetch files: ${res.status}`);
  return res.json();
}

export async function uploadFile(file: File): Promise<UploadedFile> {
  const form = new FormData();
  form.append('file', file);

  const res = await fetch(`${BASE_URL}/upload`, {
    method: 'POST',
    body: form,
  });

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = body?.detail;
    } catch {
      // ignore parse error
    }
    throw new Error(detail ?? `Upload failed: ${res.status}`);
  }

  return res.json();
}

export async function deleteFile(file_id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/files/${encodeURIComponent(file_id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}

export async function getFileContent(file_id: string): Promise<string> {
  const res = await fetch(`${BASE_URL}/files/${encodeURIComponent(file_id)}/content`);
  if (!res.ok) throw new Error(`Failed to fetch file content: ${res.status}`);
  const data = await res.json();
  return data.content as string;
}

export async function streamChat(
  request: ChatRequest,
  onToken: (token: string) => void,
  onTable: (table: ComplianceRow[]) => void,
  onDone: () => void,
  onError: (message: string) => void,
  signal?: AbortSignal
): Promise<void> {
  let res: Response;

  try {
    res = await fetch(`${BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(request),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      onDone();
      return;
    }
    onError(err instanceof Error ? err.message : String(err));
    return;
  }

  if (!res.ok) {
    onError(`Chat request failed: ${res.status}`);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    onError('No response body');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let terminalReceived = false;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice('data: '.length).trim();
        if (!raw) continue;

        let chunk: ChatStreamChunk;
        try {
          chunk = JSON.parse(raw);
        } catch {
          continue;
        }

        if (chunk.type === 'token' && chunk.content !== undefined) {
          onToken(chunk.content);
        } else if (chunk.type === 'table' && chunk.data) {
          onTable(chunk.data);
        } else if (chunk.type === 'done') {
          terminalReceived = true;
          onDone();
        } else if (chunk.type === 'error') {
          terminalReceived = true;
          const msg = chunk.message ?? 'Unknown error';
          onError(
            msg.toLowerCase().includes('rate limit')
              ? 'Rate limit reached — please wait a moment and try again.'
              : msg
          );
        }
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return;
    terminalReceived = true;
    onError(err instanceof Error ? err.message : String(err));
  } finally {
    reader.releaseLock();
    if (!terminalReceived) {
      onDone();
    }
  }
}
