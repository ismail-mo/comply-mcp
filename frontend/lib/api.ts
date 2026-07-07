import type {
  AuditFindingsPayload,
  AuditOverviewPayload,
  ChatRequest,
  ChatStreamChunk,
  QuickRef,
  UploadedFile,
} from './types';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function getFiles(): Promise<UploadedFile[]> {
  const res = await fetch(`${BASE_URL}/files`);
  if (!res.ok) throw new Error(`Failed to fetch files: ${res.status}`);
  return res.json();
}

export async function uploadFile(file: File): Promise<UploadedFile> {
  const form = new FormData();
  form.append('file', file);

  const res = await fetch(`${BASE_URL}/upload`, { method: 'POST', body: form });

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

export interface StreamHandlers {
  onToken: (token: string) => void;
  onStatus?: (status: string) => void;
  onFindings?: (data: AuditFindingsPayload) => void;
  onOverview?: (data: AuditOverviewPayload) => void;
  onQuickRefs?: (refs: QuickRef[]) => void;
  onDone: (timing?: Record<string, number>) => void;
  onError: (message: string) => void;
}

export async function streamChat(
  request: ChatRequest,
  handlers: StreamHandlers,
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
      handlers.onDone();
      return;
    }
    handlers.onError(err instanceof Error ? err.message : String(err));
    return;
  }

  if (!res.ok) {
    handlers.onError(`Chat request failed: ${res.status}`);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    handlers.onError('No response body');
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

        switch (chunk.type) {
          case 'token':
            if (chunk.content !== undefined) handlers.onToken(chunk.content);
            break;
          case 'status':
            if (chunk.message) handlers.onStatus?.(chunk.message);
            break;
          case 'findings':
            if (chunk.data) handlers.onFindings?.(chunk.data as AuditFindingsPayload);
            break;
          case 'overview':
            if (chunk.data) handlers.onOverview?.(chunk.data as AuditOverviewPayload);
            break;
          case 'quick_refs':
            if (chunk.data) handlers.onQuickRefs?.(chunk.data as QuickRef[]);
            break;
          case 'done':
            terminalReceived = true;
            handlers.onDone(chunk.timing);
            break;
          case 'error': {
            terminalReceived = true;
            const msg = chunk.message ?? 'Unknown error';
            handlers.onError(
              msg.toLowerCase().includes('rate limit')
                ? 'Rate limit reached — please wait a moment and try again.'
                : msg
            );
            break;
          }
          default:
            break; // legacy events ignored
        }
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return;
    terminalReceived = true;
    handlers.onError(err instanceof Error ? err.message : String(err));
  } finally {
    reader.releaseLock();
    if (!terminalReceived) {
      handlers.onDone();
    }
  }
}
