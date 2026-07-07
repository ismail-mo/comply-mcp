'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import type {
  ActiveCitation,
  ChatMessage,
  QuickRef,
  UploadedFile,
} from '../lib/types';
import AuditView from './AuditView';

/* ── quick-action chips ── */

const QUICK_CHIPS = [
  { label: 'Check the column', msg: '[COMPLIANCE_AUDIT] check the column' },
  { label: 'Check the beam', msg: '[COMPLIANCE_AUDIT] check the beam' },
  { label: 'Full audit', msg: '[COMPLIANCE_AUDIT] check the column and the beam' },
  {
    label: 'What governs buckling?',
    msg: 'what does Eurocode 3 say about flexural buckling resistance of columns?',
  },
] as const;

/* ── markdown-lite prose: **bold** + paragraphs on blank lines ── */

function BoldSpans({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        const m = part.match(/^\*\*([^*]+)\*\*$/);
        if (m) {
          return (
            <strong key={i} style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
              {m[1]}
            </strong>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

function Prose({ text }: { text: string }) {
  const paragraphs = text.split(/\n\s*\n/).filter((p) => p.trim().length > 0);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {paragraphs.map((p, i) => (
        <p
          key={i}
          style={{
            margin: 0,
            fontSize: '13px',
            lineHeight: 1.7,
            color: 'var(--text-secondary)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontFamily: 'var(--font-sans)',
          }}
        >
          <BoldSpans text={p} />
        </p>
      ))}
    </div>
  );
}

/* ── quick-ref clause badges under prose ── */

function QuickRefRow({ refs }: { refs: QuickRef[] }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px', marginTop: '8px' }}>
      {refs.map((r, i) => {
        const label = [r.source ?? r.clause ?? 'Ref', r.page != null ? `p.${r.page}` : null]
          .filter(Boolean)
          .join(' · ');
        return (
          <button
            key={i}
            onClick={() => undefined}
            title={r.clause ?? undefined}
            style={{
              background: 'var(--cite-ec3-bg)',
              color: 'var(--cite-ec3-fg)',
              border: 'none',
              borderRadius: '3px',
              padding: '2px 7px',
              fontSize: '10px',
              fontWeight: 600,
              fontFamily: 'var(--font-sans)',
              cursor: 'pointer',
              lineHeight: 1.5,
              whiteSpace: 'nowrap',
            }}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

/* ── assistant message ── */

const AssistantMessage = memo(function AssistantMessage({
  message,
  onCitationClick,
}: {
  message: ChatMessage;
  onCitationClick: (c: ActiveCitation) => void;
}) {
  const isStreaming = message.isStreaming === true;
  const showStatus = isStreaming && !!message.status;

  return (
    <div style={{ marginBottom: '18px' }}>
      {message.auditFindings ? (
        <div
          style={{
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            padding: '14px',
          }}
        >
          <AuditView
            findings={message.auditFindings}
            overview={message.auditOverview ?? null}
            onCitationClick={onCitationClick}
          />
        </div>
      ) : message.content ? (
        <div>
          <Prose text={message.content} />
          {message.quickRefs && message.quickRefs.length > 0 && (
            <QuickRefRow refs={message.quickRefs} />
          )}
        </div>
      ) : null}

      {showStatus ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '7px',
            marginTop: message.auditFindings || message.content ? '10px' : '2px',
            fontSize: '11px',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          <span className="comply-spinner" />
          <span>{message.status}</span>
        </div>
      ) : isStreaming && !message.content && !message.auditFindings ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '7px',
            fontSize: '11px',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          <span className="comply-spinner" />
          <span>Thinking…</span>
        </div>
      ) : null}
    </div>
  );
});

/* ── main component ── */

interface ChatSidebarProps {
  activeFile: UploadedFile | null;
  messages: ChatMessage[];
  onSend: (message: string, visibleMessage?: string) => void;
  streaming: boolean;
  onClearHistory: () => void;
  onCitationClick: (c: ActiveCitation) => void;
}

const NEAR_BOTTOM_PX = 60;

export default function ChatSidebar({
  activeFile,
  messages,
  onSend,
  streaming,
  onClearHistory,
  onCitationClick,
}: ChatSidebarProps) {
  const [inputValue, setInputValue] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollBoxRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pinnedToBottom = useRef(true);

  const handleScroll = useCallback(() => {
    const el = scrollBoxRef.current;
    if (!el) return;
    pinnedToBottom.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  }, []);

  /* auto-scroll only when the user is already near the bottom */
  const last = messages[messages.length - 1];
  const lastContentLength =
    (last?.content?.length ?? 0) +
    (last?.auditFindings ? 1 : 0) +
    (last?.auditOverview ? 1 : 0) +
    (last?.status?.length ?? 0);

  useEffect(() => {
    if (!pinnedToBottom.current) return;
    bottomRef.current?.scrollIntoView({ behavior: 'instant' as ScrollBehavior, block: 'end' });
  }, [messages.length, lastContentLength]);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const doSend = (msg: string, visible?: string) => {
    onSend(msg, visible);
  };

  const handleSend = () => {
    const text = inputValue.trim();
    if (!text || streaming || !activeFile) return;
    setInputValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    doSend(text);
  };

  const handleChip = (chip: (typeof QUICK_CHIPS)[number]) => {
    if (streaming || !activeFile) return;
    doSend(chip.msg, chip.label);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 110) + 'px';
    }
  };

  const chipsDisabled = streaming || !activeFile;
  const sendDisabled = streaming || !activeFile || inputValue.trim() === '';

  return (
    <>
      <style>{`
        @keyframes comply-spin { to { transform: rotate(360deg); } }
        .comply-spinner {
          width: 11px; height: 11px; flex-shrink: 0;
          border: 1.5px solid var(--border-strong);
          border-top-color: var(--text-accent);
          border-radius: 50%;
          display: inline-block;
          animation: comply-spin 0.8s linear infinite;
        }
        .comply-chip:hover:not(:disabled) {
          border-color: var(--border-strong);
          color: var(--text-primary);
          background: var(--surface-1);
        }
        .comply-clear:hover { color: var(--fail-fg); }
        .comply-textarea::placeholder { color: var(--text-muted); }
        .comply-textarea:focus {
          outline: none;
          border-color: var(--text-accent) !important;
          box-shadow: 0 0 0 2px rgba(24, 95, 165, 0.12);
        }
        .comply-send:hover:not(:disabled) { opacity: 0.88; }
      `}</style>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          width: '100%',
          background: 'var(--surface-0)',
          overflow: 'hidden',
          fontFamily: 'var(--font-sans)',
        }}
      >
        {/* ── 1. header bar ── */}
        <div
          style={{
            flexShrink: 0,
            padding: '12px 16px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '10px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
            <span
              style={{
                fontSize: '10px',
                textTransform: 'uppercase',
                letterSpacing: '0.12em',
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-mono)',
                whiteSpace: 'nowrap',
              }}
            >
              Compliance Chat
            </span>
            {activeFile && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  background: 'var(--surface-1)',
                  border: '1px solid var(--border)',
                  borderRadius: '4px',
                  padding: '2px 8px',
                  minWidth: 0,
                }}
              >
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    color: 'var(--text-accent)',
                    fontFamily: 'var(--font-mono)',
                    flexShrink: 0,
                  }}
                >
                  {activeFile.type === 'pdf' ? 'PDF' : 'XLS'}
                </span>
                <span
                  style={{
                    fontSize: '11px',
                    color: 'var(--text-secondary)',
                    maxWidth: '150px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {activeFile.filename}
                </span>
              </span>
            )}
          </div>
          {messages.length > 0 && (
            <button
              className="comply-clear"
              onClick={onClearHistory}
              style={{
                fontSize: '10px',
                color: 'var(--text-muted)',
                background: 'none',
                border: 'none',
                padding: 0,
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                transition: 'color 0.15s',
                flexShrink: 0,
              }}
            >
              Clear
            </button>
          )}
        </div>

        {/* ── 2. messages ── */}
        <div
          ref={scrollBoxRef}
          onScroll={handleScroll}
          style={{ flexGrow: 1, overflowY: 'auto', padding: '14px 16px' }}
        >
          {messages.length === 0 ? (
            <div
              style={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
              }}
            >
              <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                Ask a compliance question
              </div>
              <div
                style={{
                  fontSize: '11px',
                  color: activeFile ? 'var(--text-accent)' : 'var(--text-muted)',
                  fontFamily: 'var(--font-mono)',
                  maxWidth: '220px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {activeFile ? activeFile.filename : 'Select a file to begin'}
              </div>
            </div>
          ) : (
            <>
              {messages.map((m) =>
                m.role === 'user' ? (
                  <div
                    key={m.id}
                    style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '14px' }}
                  >
                    <div
                      style={{
                        maxWidth: '85%',
                        background: 'var(--surface-1)',
                        border: '1px solid var(--border)',
                        borderRadius: '8px 8px 3px 8px',
                        padding: '7px 12px',
                        fontSize: '12px',
                        lineHeight: 1.6,
                        color: 'var(--text-primary)',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                      }}
                    >
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <AssistantMessage key={m.id} message={m} onCitationClick={onCitationClick} />
                )
              )}
              <div ref={bottomRef} />
            </>
          )}
        </div>

        {/* ── 3 + 4. chips + input ── */}
        <div
          style={{
            flexShrink: 0,
            borderTop: '1px solid var(--border)',
            padding: '12px 16px',
            background: 'var(--surface-0)',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
            {QUICK_CHIPS.map((chip) => (
              <button
                key={chip.label}
                className="comply-chip"
                onClick={() => handleChip(chip)}
                disabled={chipsDisabled}
                style={{
                  padding: '3px 10px',
                  fontSize: '11px',
                  border: '1px solid var(--border)',
                  borderRadius: '4px',
                  background: 'var(--surface-2)',
                  color: 'var(--text-secondary)',
                  cursor: chipsDisabled ? 'not-allowed' : 'pointer',
                  opacity: chipsDisabled ? 0.5 : 1,
                  transition: 'border-color 0.15s, color 0.15s, background 0.15s',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                {chip.label}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
            <textarea
              ref={textareaRef}
              className="comply-textarea"
              value={inputValue}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              onCompositionStart={() => setIsComposing(true)}
              onCompositionEnd={() => setIsComposing(false)}
              disabled={streaming}
              placeholder={activeFile ? 'Ask about compliance…' : 'Select a file to begin'}
              rows={1}
              style={{
                flex: 1,
                resize: 'none',
                minHeight: '36px',
                maxHeight: '110px',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                padding: '8px 12px',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-sans)',
                fontSize: '13px',
                lineHeight: 1.5,
                boxSizing: 'border-box',
                opacity: streaming ? 0.6 : 1,
                overflowY: 'auto',
              }}
            />
            <button
              className="comply-send"
              onClick={handleSend}
              disabled={sendDisabled}
              style={{
                height: '36px',
                padding: '0 14px',
                background: 'var(--text-accent)',
                color: '#FFFFFF',
                fontSize: '12px',
                fontWeight: 600,
                border: 'none',
                borderRadius: '6px',
                cursor: sendDisabled ? 'not-allowed' : 'pointer',
                opacity: sendDisabled ? 0.4 : 1,
                transition: 'opacity 0.15s',
                fontFamily: 'var(--font-sans)',
                flexShrink: 0,
              }}
            >
              {streaming ? '···' : 'Send'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
