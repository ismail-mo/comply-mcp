'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { streamChat } from '../lib/api';
import type { ChatMessage, ChatRequest } from '../lib/types';

const COMPLIANCE_AUDIT_PREFIX = '[COMPLIANCE_AUDIT]';

const getVisibleContent = (message: string, visibleMessage?: string): string => {
  if (visibleMessage) return visibleMessage;
  if (message.trim().startsWith(COMPLIANCE_AUDIT_PREFIX)) {
    return message.replace(COMPLIANCE_AUDIT_PREFIX, '').trim();
  }
  return message;
};

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  useEffect(() => () => abortRef.current?.abort(), []);

  const patchLast = useCallback(
    (patch: Partial<ChatMessage> | ((last: ChatMessage) => Partial<ChatMessage>)) => {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (!last || last.role !== 'assistant') return prev;
        const delta = typeof patch === 'function' ? patch(last) : patch;
        updated[updated.length - 1] = { ...last, ...delta };
        return updated;
      });
    },
    []
  );

  const sendMessage = useCallback(
    async (
      message: string,
      visibleMessage?: string,
      activeFileId?: string | null
    ): Promise<void> => {
      if (streaming) return;
      const visibleContent = getVisibleContent(message, visibleMessage);

      const history = messagesRef.current
        .filter((m) => m.content)
        .map((m) => ({ role: m.role, content: m.content.slice(0, 4000) }));

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
        status: null,
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const request: ChatRequest = {
        message,
        file_id: activeFileId ?? null,
        history,
      };

      await streamChat(
        request,
        {
          onToken: (token) =>
            patchLast((last) => ({ content: last.content + token, status: null })),
          onStatus: (status) => patchLast({ status }),
          onFindings: (data) => patchLast({ auditFindings: data }),
          onOverview: (data) => patchLast({ auditOverview: data, status: null }),
          onQuickRefs: (refs) => patchLast({ quickRefs: refs }),
          onDone: (timing) =>
            patchLast({ isStreaming: false, status: null, timing: timing ?? null }),
          onError: (msg) =>
            patchLast((last) => ({
              content: last.content || `⚠ ${msg}`,
              isStreaming: false,
              status: null,
            })),
        },
        controller.signal
      );

      setStreaming(false);
      abortRef.current = null;
    },
    [patchLast, streaming]
  );

  const clearHistory = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setStreaming(false);
  }, []);

  return { messages, sendMessage, clearHistory, streaming };
}
