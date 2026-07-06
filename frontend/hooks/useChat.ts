'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { streamChat } from '../lib/api';
import type { ActiveCitation, ChatMessage, ChatRequest, ComplianceRow, UploadedFile } from '../lib/types';

interface ProjectRef {
  file_id: string;
  filename: string;
}

interface StandardRef {
  file_id: string;
  filename: string;
}

const cleanContent = (content: string): string =>
  content.replace(/<table>[\s\S]*?<\/table>/g, '[compliance table omitted]').trim();

const stripStreamingTable = (content: string): string => {
  const complete = content.replace(/<table>[\s\S]*?<\/table>/g, '');
  const openIndex = complete.indexOf('<table>');
  return (openIndex === -1 ? complete : complete.slice(0, openIndex)).trimEnd();
};

const COMPLIANCE_AUDIT_PREFIX = '[COMPLIANCE_AUDIT]';
const STATUS_ORDER: Record<string, number> = { FAIL: 0, WARN: 1, PASS: 2 };

const getVisibleContent = (message: string, visibleMessage?: string): string => {
  if (visibleMessage) return visibleMessage;
  if (message.trim().startsWith(COMPLIANCE_AUDIT_PREFIX)) {
    return message.replace(COMPLIANCE_AUDIT_PREFIX, '').trim();
  }
  return message;
};

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [projectRefs, setProjectRefs] = useState<ProjectRef[]>([]);
  const [standardRefs, setStandardRefs] = useState<StandardRef[]>([]);
  const [streaming, setStreaming] = useState(false);
  const messagesRef = useRef(messages);
  const projectRefsRef = useRef(projectRefs);
  const standardRefsRef = useRef(standardRefs);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    projectRefsRef.current = projectRefs;
  }, [projectRefs]);

  useEffect(() => {
    standardRefsRef.current = standardRefs;
  }, [standardRefs]);

  useEffect(() => () => {
    abortRef.current?.abort();
  }, []);

  const getMessages = useCallback((): ChatMessage[] => {
    return messages;
  }, [messages]);

  const injectFileContext = useCallback(
    (file: UploadedFile): void => {
      const isStandard = file.classification === 'STANDARD';

      if (isStandard) {
        setStandardRefs((prev) => [
          ...prev.filter((ref) => ref.file_id !== file.file_id),
          { file_id: file.file_id, filename: file.filename },
        ]);
      } else {
        const noticeMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `[PROJECT DOCUMENT — ${file.filename}]`,
          isStreaming: false,
        };
        setMessages((prev) => [...prev, noticeMsg]);

        setProjectRefs((prev) => [
          ...prev.filter((ref) => ref.file_id !== file.file_id),
          { file_id: file.file_id, filename: file.filename },
        ]);
      }
    },
    []
  );

  const sendMessage = useCallback(
    async (message: string, visibleMessage?: string, activeFileId?: string | null): Promise<void> => {
      if (streaming) return;
      const visibleContent = getVisibleContent(message, visibleMessage);

      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: visibleContent,
      };

      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        isStreaming: true,
      };

      const snapshotMessages = messagesRef.current;
      const snapshotProjectRefs = projectRefsRef.current;
      const snapshotStandardRefs = standardRefsRef.current;

      setMessages((prev) => [...prev, userMsg, assistantMsg]);

      // Build history
      const history: Array<{ role: 'user' | 'assistant'; content: string }> = [];

      // Collapsed STANDARD refs as a single prepended message
      if (snapshotStandardRefs.length > 0) {
        history.push({
          role: 'user',
          content: `[STANDARD DOCUMENTS AVAILABLE: ${snapshotStandardRefs
            .map((ref) => `file_id=${ref.file_id} filename="${ref.filename}"`)
            .join('; ')} — query via retrieve_code_clauses tool only. Use matching file_id values for standard_file_id citations.]`,
        });
      }

      if (snapshotProjectRefs.length > 0) {
        history.push({
          role: 'user',
          content: `[PROJECT DOCUMENTS AVAILABLE: ${snapshotProjectRefs
            .map((ref) => `file_id=${ref.file_id} filename="${ref.filename}"`)
            .join('; ')} — query project_chunks via extract_design_values(file_id=...) or search_documents(source_filter="project", file_id=...). Use matching file_id values for project_file_id citations.]`,
        });
      }

      // Last 6 conversation messages (3 exchanges), table JSON stripped
      const recentMessages = snapshotMessages.slice(-6);
      for (const msg of recentMessages) {
        if (msg.content.startsWith('📄')) continue;
        history.push({ role: msg.role, content: cleanContent(msg.content) });
      }

      const request: ChatRequest = {
        message,
        file_id: activeFileId ?? null,
        history,
      };

      setStreaming(true);
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const onTable = (table: ComplianceRow[]) => {
        const indexedTable = table.map((row, index) => ({ row, originalIndex: index }));
        indexedTable.sort(
          (a, b) => (STATUS_ORDER[a.row.status] ?? 3) - (STATUS_ORDER[b.row.status] ?? 3)
        );
        const sortedTable = indexedTable.map((item) => item.row);
        const citationMap = new Map<number, number>();
        indexedTable.forEach((item, sortedIndex) => {
          citationMap.set(item.originalIndex + 1, sortedIndex + 1);
        });

        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === 'assistant') {
            const citations: ActiveCitation[] = [];
            const remappedContent = stripStreamingTable(last.content).replace(/\[(\d+)\]/g, (match, raw) => {
              const next = citationMap.get(parseInt(raw, 10));
              return next ? `[${next}]` : match;
            });
            const matches = Array.from(remappedContent.matchAll(/\[(\d+)\]/g));

            for (const match of matches) {
              const n = parseInt(match[1]);
              const row = sortedTable[n - 1];

              if (!row) continue;
              if (!row.project_file_id) continue;
              if (!row.source_page) continue;
              if (!row.highlight_start) continue;
              if (!row.highlight_end) continue;

              if (citations.find(
                (c) => c.file_id === row.project_file_id && c.page === row.source_page
              )) continue;

              citations.push({
                type: 'project',
                file_id: row.project_file_id,
                page: row.source_page,
                highlight_start: row.highlight_start,
                highlight_end: row.highlight_end,
              });
            }

            updated[updated.length - 1] = {
              ...last,
              content: remappedContent,
              table: sortedTable,
              citations,
            };
          }
          return updated;
        });
      };

      await streamChat(
        request,
        (token) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = {
              ...last,
              content: stripStreamingTable(last.content + token),
            };
            return updated;
          });
        },
        onTable,
        () => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = { ...last, isStreaming: false };
            return updated;
          });
          setStreaming(false);
        },
        (errorMessage) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = {
              ...last,
              content: `Error: ${errorMessage}`,
              isStreaming: false,
            };
            return updated;
          });
          setStreaming(false);
        },
        controller.signal
      );
    },
    [streaming]
  );

  const clearHistory = useCallback((): void => {
    setMessages([]);
    setProjectRefs([]);
    setStandardRefs([]);
  }, []);

  return { messages, getMessages, sendMessage, injectFileContext, clearHistory, streaming, standardRefs };
}
