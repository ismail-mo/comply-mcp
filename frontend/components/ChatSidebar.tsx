'use client';

import { useRef, useEffect, useState } from 'react';
import type { UploadedFile, ChatMessage, ComplianceRow, ActiveCitation } from '../lib/types';

const COMPLIANCE_CHIPS = [
  {
    label: 'Check EC1 Compliance',
    hidden_prompt: `[COMPLIANCE_AUDIT] You are checking this project document for Eurocode 1 compliance. Run a full compliance audit following the compliance_audit skill exactly:
1. Call extract_design_values
2. Call retrieve_code_clauses for each value against EC1
3. Call compare_value_to_clause for each comparison
4. Return Summary + Table in exact required format`,
  },
  {
    label: 'Check EC3 Compliance',
    hidden_prompt: `[COMPLIANCE_AUDIT] You are checking this project document for Eurocode 3 compliance. Run a full compliance audit following the compliance_audit skill exactly:
1. Call extract_design_values
2. Call retrieve_code_clauses for each value against EC3
3. Call compare_value_to_clause for each comparison
4. Return Summary + Table in exact required format`,
  },
  {
    label: 'Check Client Reqs',
    hidden_prompt: `[COMPLIANCE_AUDIT] You are checking this project document against client requirements. Run a full compliance audit following the compliance_audit skill exactly:
1. Call extract_design_values
2. Call retrieve_code_clauses against client requirements
3. Call compare_value_to_clause for each comparison
4. Return Summary + Table in exact required format`,
  },
  {
    label: 'Summarise Risks',
    hidden_prompt: `[COMPLIANCE_AUDIT] Identify all engineering risks across uploaded project documents. Rank by severity. Return Summary + Table in exact required format with FAIL for critical risks, WARN for moderate, PASS for managed.`,
  },
  {
    label: "What's Missing?",
    hidden_prompt: `[COMPLIANCE_AUDIT] Identify what is absent from the uploaded project documents that would be required for a complete EC1, EC3, or client requirements submission. Return Summary + Table in exact required format.`,
  },
];

const getSummaryText = (content: string): string =>
  content.replace(/<table>[\s\S]*?<\/table>/g, '').trim();

function StatusBadge({ status }: { status: string }) {
  const bg =
    status === 'FAIL' ? 'var(--danger)' :
    status === 'WARN' ? 'var(--warning)' :
    'var(--success)';
  const color = status === 'FAIL' ? '#fff' : '#0d0d0f';
  return (
    <span
      style={{
        background: bg,
        color,
        fontSize: '9px',
        fontWeight: 700,
        padding: '2px 6px',
        borderRadius: '3px',
        textTransform: 'uppercase' as const,
        whiteSpace: 'nowrap' as const,
        display: 'inline-block',
      }}
    >
      {status}
    </span>
  );
}

function ProjectBadge({
  row,
  onCitationClick,
}: {
  row: ComplianceRow;
  onCitationClick: (c: ActiveCitation) => void;
}) {
  if (!row.project_file_id || !row.source_page || !row.highlight_start || !row.highlight_end) return null;
  return (
    <button
      className="project-citation-badge"
      title="View in document"
      onClick={() =>
        onCitationClick({
          type: 'project',
          file_id: row.project_file_id!,
          page: row.source_page!,
          highlight_start: row.highlight_start!,
          highlight_end: row.highlight_end!,
        })
      }
      style={{
        display: 'inline-flex',
        width: '16px',
        height: '16px',
        borderRadius: '50%',
        background: '#2563eb',
        color: '#fff',
        fontSize: '9px',
        fontWeight: 700,
        cursor: 'pointer',
        marginLeft: '4px',
        verticalAlign: 'middle',
        alignItems: 'center',
        justifyContent: 'center',
        border: 'none',
        flexShrink: 0,
        lineHeight: 1,
      }}
    >
      P
    </button>
  );
}

function StandardBadge({
  row,
  onCitationClick,
}: {
  row: ComplianceRow;
  onCitationClick: (c: ActiveCitation) => void;
}) {
  if (!row.standard_file_id || !row.standard_page || !row.standard_text) return null;
  const words = (row.standard_text ?? '').split(' ').filter((w) => w.length > 0);
  const highlight_start = words.slice(0, 5).join(' ');
  const highlight_end = words.slice(-5).join(' ');
  return (
    <button
      className="standard-citation-badge"
      title="View in standard"
      onClick={() =>
        onCitationClick({
          type: 'standard',
          file_id: row.standard_file_id!,
          page: row.standard_page!,
          highlight_start,
          highlight_end,
        })
      }
      style={{
        display: 'inline-flex',
        width: '16px',
        height: '16px',
        borderRadius: '50%',
        background: '#9333ea',
        color: '#fff',
        fontSize: '9px',
        fontWeight: 700,
        cursor: 'pointer',
        marginLeft: '4px',
        verticalAlign: 'middle',
        alignItems: 'center',
        justifyContent: 'center',
        border: 'none',
        flexShrink: 0,
        lineHeight: 1,
      }}
    >
      S
    </button>
  );
}

function SummaryText({
  text,
  table,
  onCitationClick,
}: {
  text: string;
  table: ComplianceRow[];
  onCitationClick: (c: ActiveCitation) => void;
}) {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <p
      style={{
        fontSize: '12px',
        color: 'var(--text-primary)',
        lineHeight: '1.7',
        marginBottom: '12px',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (!match) return <span key={i}>{part}</span>;
        const n = parseInt(match[1]);
        const row = table[n - 1];
        if (!row || !row.project_file_id || !row.source_page || !row.highlight_start || !row.highlight_end) {
          return (
            <span key={i} style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
              [{n}]
            </span>
          );
        }
        return (
          <button
            className="project-citation-badge"
            key={i}
            title="View in document"
            onClick={() =>
              onCitationClick({
                type: 'project',
                file_id: row.project_file_id!,
                page: row.source_page!,
                highlight_start: row.highlight_start!,
                highlight_end: row.highlight_end!,
              })
            }
            style={{
              display: 'inline-flex',
              width: '16px',
              height: '16px',
              borderRadius: '50%',
              background: '#2563eb',
              color: '#fff',
              fontSize: '9px',
              fontWeight: 700,
              cursor: 'pointer',
              marginLeft: '2px',
              marginRight: '1px',
              verticalAlign: 'middle',
              alignItems: 'center',
              justifyContent: 'center',
              border: 'none',
              flexShrink: 0,
              lineHeight: 1,
            }}
          >
            {n}
          </button>
        );
      })}
    </p>
  );
}

const COL = '60px 100px 1fr 120px 100px 80px 120px';
const TABLE_HEADERS = ['Status', 'Category', 'Issue', 'Reference', 'Clause', 'Party', 'Action'];
const STATUS_ORDER: Record<string, number> = { FAIL: 0, WARN: 1, PASS: 2 };

function ComplianceTable({
  rows,
  onCitationClick,
}: {
  rows: ComplianceRow[];
  onCitationClick: (c: ActiveCitation) => void;
}) {
  const sorted = [...rows].sort(
    (a, b) => (STATUS_ORDER[a.status] ?? 3) - (STATUS_ORDER[b.status] ?? 3)
  );

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: '4px',
        overflowX: 'auto',
        width: '100%',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: COL,
          background: 'var(--bg-panel)',
          borderBottom: '1px solid var(--border)',
          minWidth: '680px',
        }}
      >
        {TABLE_HEADERS.map((h) => (
          <div
            key={h}
            style={{
              padding: '6px 8px',
              fontSize: '9px',
              textTransform: 'uppercase' as const,
              letterSpacing: '0.08em',
              color: 'var(--text-muted)',
              fontFamily: 'IBM Plex Mono, monospace',
            }}
          >
            {h}
          </div>
        ))}
      </div>

      {/* Rows */}
      {sorted.map((row, idx) => (
        <div
          key={idx}
          style={{
            display: 'grid',
            gridTemplateColumns: COL,
            borderBottom: idx < sorted.length - 1 ? '1px solid var(--border)' : 'none',
            padding: '8px',
            minWidth: '680px',
            transition: 'background 0.1s',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-hover)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLDivElement).style.background = 'transparent';
          }}
        >
          {/* Status */}
          <div style={{ display: 'flex', alignItems: 'flex-start', paddingTop: '1px' }}>
            <StatusBadge status={row.status} />
          </div>

          {/* Category */}
          <div
            style={{
              fontSize: '10px',
              color: 'var(--text-secondary)',
              padding: '0 4px',
              wordBreak: 'break-word',
              lineHeight: '1.5',
            }}
          >
            {row.category}
          </div>

          {/* Issue */}
          <div
            style={{
              fontSize: '11px',
              color: 'var(--text-primary)',
              lineHeight: '1.5',
              padding: '0 4px',
              wordBreak: 'break-word',
            }}
          >
            {row.issue}
          </div>

          {/* Reference */}
          <div
            style={{
              padding: '0 4px',
              fontSize: '11px',
              color: 'var(--text-secondary)',
              fontStyle: 'italic',
              wordBreak: 'break-word',
              lineHeight: '1.5',
            }}
          >
            {row.reference_text ?? '—'}
            <ProjectBadge row={row} onCitationClick={onCitationClick} />
          </div>

          {/* Clause */}
          <div
            style={{
              padding: '0 4px',
              fontSize: '11px',
              color: 'var(--text-primary)',
              wordBreak: 'break-word',
              lineHeight: '1.5',
            }}
          >
            {row.standard_clause ?? '—'}
            <StandardBadge row={row} onCitationClick={onCitationClick} />
          </div>

          {/* Party */}
          <div
            style={{
              padding: '0 4px',
              fontSize: '10px',
              color: 'var(--text-secondary)',
              wordBreak: 'break-word',
              lineHeight: '1.5',
            }}
          >
            {row.party_affected ?? '—'}
          </div>

          {/* Action */}
          <div
            style={{
              padding: '0 4px',
              fontSize: '11px',
              color: row.status === 'PASS' ? 'var(--success)' : 'var(--text-primary)',
              wordBreak: 'break-word',
              lineHeight: '1.5',
            }}
          >
            {row.recommendation ?? (row.status === 'PASS' ? 'None — compliant' : '—')}
          </div>
        </div>
      ))}
    </div>
  );
}

function AssistantMessage({
  message,
  onCitationClick,
}: {
  message: ChatMessage;
  onCitationClick: (c: ActiveCitation) => void;
}) {
  const isStreaming = message.isStreaming === true;
  const hasTable = !isStreaming && !!message.table && message.table.length > 0;
  const summaryText = getSummaryText(message.content);
  const streamingText = summaryText || 'Preparing compliance check...';

  return (
    <div
      style={{
        marginBottom: '16px',
        display: 'flex',
        justifyContent: 'flex-start',
        gap: '8px',
        alignItems: 'flex-start',
      }}
    >
      {/* Avatar */}
      <div
        style={{
          width: '20px',
          height: '20px',
          flexShrink: 0,
          borderRadius: '3px',
          background: 'var(--accent)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginTop: '2px',
        }}
      >
        <span style={{ fontSize: '11px', fontWeight: 700, color: '#0d0d0f' }}>C</span>
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {isStreaming ? (
          <div
            style={{
              fontSize: '12px',
              color: 'var(--text-primary)',
              lineHeight: '1.6',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {streamingText}
            <span
              className="comply-cursor"
              style={{
                display: 'inline-block',
                width: '2px',
                height: '12px',
                background: 'var(--accent)',
                marginLeft: '2px',
                verticalAlign: 'middle',
              }}
            />
          </div>
        ) : hasTable ? (
          <>
            <SummaryText
              text={summaryText}
              table={message.table!}
              onCitationClick={onCitationClick}
            />
            <ComplianceTable rows={message.table!} onCitationClick={onCitationClick} />
          </>
        ) : (
          <div
            style={{
              fontSize: '12px',
              color: 'var(--text-primary)',
              lineHeight: '1.6',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {summaryText}
          </div>
        )}
      </div>
    </div>
  );
}

interface ChatSidebarProps {
  activeFile: UploadedFile | null;
  messages: ChatMessage[];
  onSend: (message: string, visibleMessage?: string) => Promise<void>;
  streaming: boolean;
  onClearHistory: () => void;
  onCitationClick: (citation: ActiveCitation) => void;
}

export default function ChatSidebar({
  activeFile,
  messages,
  onSend,
  streaming,
  onClearHistory,
  onCitationClick,
}: ChatSidebarProps) {
  const [inputValue, setInputValue] = useState('');
  const [sendHover, setSendHover] = useState(false);
  const [clearHover, setClearHover] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const lastMessage = messages[messages.length - 1];
  const lastContentLength = lastMessage?.content?.length ?? 0;
  const scrollRaf = useRef<number | null>(null);
  useEffect(() => {
    if (!streaming) return;
    if (scrollRaf.current) cancelAnimationFrame(scrollRaf.current);
    scrollRaf.current = requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'instant', block: 'end' });
    });
    return () => {
      if (scrollRaf.current) cancelAnimationFrame(scrollRaf.current);
    };
  }, [lastContentLength, streaming]);

  useEffect(() => {
    if (textareaRef.current) textareaRef.current.focus();
  }, []);

  const handleSend = async () => {
    const text = inputValue.trim();
    if (!text || streaming || !activeFile) return;
    setInputValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    await onSend(text);
  };

  const handleChipClick = async (chip: (typeof COMPLIANCE_CHIPS)[number]) => {
    if (streaming || !activeFile) return;
    setInputValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    await onSend(chip.hidden_prompt, chip.label);
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
      ta.style.height = Math.min(ta.scrollHeight, 96) + 'px';
    }
  };

  const charColor =
    inputValue.length > 1000
      ? 'var(--danger)'
      : inputValue.length > 500
      ? 'var(--warning)'
      : 'var(--text-muted)';

  const sendDisabled = !activeFile || streaming || inputValue.trim() === '';

  const typeLabel =
    activeFile?.type === 'pdf' ? 'PDF' :
    activeFile?.type === 'excel' ? 'XLS' :
    '';

  const classif = activeFile?.classification ?? 'PROJECT';

  return (
    <>
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        .comply-cursor { animation: blink 1s step-end infinite; }
        @keyframes pulse-opacity {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        .comply-send-pulse { animation: pulse-opacity 1s ease-in-out infinite; }
        .comply-messages::-webkit-scrollbar { width: 4px; }
        .comply-messages::-webkit-scrollbar-track { background: transparent; }
        .comply-messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
        .comply-textarea::placeholder { color: var(--text-muted); }
        .comply-textarea:focus { border-color: var(--accent) !important; outline: none; box-shadow: 0 0 0 2px rgba(232,240,74,0.1); }
        .quick-chip:hover { border-color: var(--accent) !important; color: var(--accent) !important; }
        .project-citation-badge:hover { background: #1d4ed8 !important; }
        .standard-citation-badge:hover { background: #7e22ce !important; }
      `}</style>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          width: '100%',
          background: 'var(--bg-panel)',
          overflow: 'hidden',
        }}
      >
        {/* HEADER */}
        <div
          style={{
            flexShrink: 0,
            padding: '12px 16px',
            borderBottom: '1px solid var(--border)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span
                style={{
                  fontSize: '10px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                  color: 'var(--text-secondary)',
                  fontFamily: 'IBM Plex Mono, monospace',
                }}
              >
                Compliance Chat
              </span>
              {activeFile && (
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    marginTop: '4px',
                    background: 'var(--bg-hover)',
                    border: '1px solid var(--border)',
                    borderRadius: '3px',
                    padding: '2px 8px',
                  }}
                >
                  <span
                    style={{
                      fontSize: '9px',
                      color: 'var(--accent)',
                      fontFamily: 'IBM Plex Mono, monospace',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                    }}
                  >
                    {typeLabel}
                  </span>
                  <span
                    style={{
                      fontSize: '10px',
                      color: 'var(--text-secondary)',
                      fontFamily: 'IBM Plex Mono, monospace',
                      maxWidth: '180px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {activeFile.filename}
                  </span>
                  <span
                    style={{
                      fontSize: '9px',
                      padding: '1px 4px',
                      border: `1px solid ${classif === 'STANDARD' ? 'var(--warning)' : 'var(--success)'}`,
                      color: classif === 'STANDARD' ? 'var(--warning)' : 'var(--success)',
                      borderRadius: '2px',
                      fontFamily: 'IBM Plex Mono, monospace',
                    }}
                  >
                    {classif}
                  </span>
                </div>
              )}
            </div>
            {messages.length > 0 && (
              <button
                onClick={onClearHistory}
                onMouseEnter={() => setClearHover(true)}
                onMouseLeave={() => setClearHover(false)}
                style={{
                  fontSize: '10px',
                  color: clearHover ? 'var(--danger)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  background: 'none',
                  border: 'none',
                  fontFamily: 'IBM Plex Mono, monospace',
                  padding: '0',
                  transition: 'color 0.15s',
                }}
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* MESSAGE AREA */}
        <div
          className="comply-messages"
          style={{ flexGrow: 1, overflowY: 'auto', padding: '12px' }}
        >
          {messages.length === 0 ? (
            <div
              style={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
              }}
            >
              <div
                style={{
                  fontSize: '24px',
                  color: 'var(--text-muted)',
                  marginBottom: '8px',
                }}
              >
                ◈
              </div>
              <div
                style={{
                  fontSize: '12px',
                  color: 'var(--text-muted)',
                  fontFamily: 'IBM Plex Mono, monospace',
                }}
              >
                Ask a compliance question
              </div>
              {!activeFile ? (
                <div
                  style={{
                    fontSize: '10px',
                    color: 'var(--text-muted)',
                    fontFamily: 'IBM Plex Mono, monospace',
                    marginTop: '4px',
                  }}
                >
                  Select a file to begin
                </div>
              ) : (
                <div
                  style={{
                    fontSize: '10px',
                    color: 'var(--accent)',
                    fontFamily: 'IBM Plex Mono, monospace',
                    marginTop: '4px',
                    maxWidth: '200px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {activeFile.filename}
                </div>
              )}
            </div>
          ) : (
            <>
              {messages.map((msg) =>
                msg.role === 'user' ? (
                  <div
                    key={msg.id}
                    style={{
                      marginBottom: '12px',
                      display: 'flex',
                      justifyContent: 'flex-end',
                    }}
                  >
                    <div
                      style={{
                        maxWidth: '85%',
                        background: 'var(--accent-dim)',
                        border: '1px solid rgba(232,240,74,0.25)',
                        borderRadius: '6px 6px 2px 6px',
                        padding: '8px 12px',
                        color: 'var(--text-primary)',
                        fontSize: '12px',
                        lineHeight: '1.5',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        fontFamily: 'IBM Plex Mono, monospace',
                      }}
                    >
                      {msg.content}
                    </div>
                  </div>
                ) : (
                  <AssistantMessage
                    key={msg.id}
                    message={msg}
                    onCitationClick={onCitationClick}
                  />
                )
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* INPUT AREA */}
        <div
          style={{
            flexShrink: 0,
            borderTop: '1px solid var(--border)',
            padding: '12px',
            background: 'var(--bg-panel)',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {/* Quick prompt chips */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                {COMPLIANCE_CHIPS.map((chip) => (
                  <button
                    key={chip.label}
                    className="quick-chip"
                    onClick={() => handleChipClick(chip)}
                    disabled={!activeFile || streaming}
                    style={{
                      padding: '2px 8px',
                      fontSize: '10px',
                      border: '1px solid var(--border)',
                      borderRadius: '3px',
                      color: 'var(--text-muted)',
                      background: 'transparent',
                      cursor: (!activeFile || streaming) ? 'not-allowed' : 'pointer',
                      fontFamily: 'IBM Plex Mono, monospace',
                      opacity: (!activeFile || streaming) ? 0.5 : 1,
                      transition: 'border-color 150ms, color 150ms',
                    }}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>

              {/* Textarea */}
              <textarea
                ref={textareaRef}
                className="comply-textarea"
                value={inputValue}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                onCompositionStart={() => setIsComposing(true)}
                onCompositionEnd={() => setIsComposing(false)}
                disabled={streaming}
                placeholder={activeFile ? 'Ask about compliance...' : 'Select a file to begin'}
                rows={1}
                style={{
                  width: '100%',
                  resize: 'none',
                  minHeight: '36px',
                  maxHeight: '96px',
                  background: 'var(--bg-base)',
                  border: '1px solid var(--border)',
                  borderRadius: '4px',
                  padding: '8px 12px',
                  color: 'var(--text-primary)',
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '12px',
                  lineHeight: '1.5',
                  boxSizing: 'border-box',
                  opacity: streaming ? 0.5 : 1,
                  overflowY: 'auto',
                }}
              />

              {/* Bottom row */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginTop: '8px',
                }}
              >
                <span
                  style={{
                    fontSize: '10px',
                    color: charColor,
                    fontFamily: 'IBM Plex Mono, monospace',
                  }}
                >
                  {inputValue.length} chars
                </span>
                <button
                  onClick={handleSend}
                  disabled={sendDisabled}
                  onMouseEnter={() => setSendHover(true)}
                  onMouseLeave={() => setSendHover(false)}
                  className={streaming ? 'comply-send-pulse' : ''}
                  style={{
                    fontSize: '11px',
                    height: '28px',
                    padding: '0 12px',
                    background: 'var(--accent)',
                    color: '#0d0d0f',
                    fontWeight: 700,
                    border: 'none',
                    borderRadius: '3px',
                    cursor: sendDisabled ? 'not-allowed' : 'pointer',
                    fontFamily: 'IBM Plex Mono, monospace',
                    opacity: sendDisabled ? 0.4 : sendHover ? 0.85 : 1,
                    transition: 'opacity 0.15s',
                  }}
                >
                  {streaming ? '···' : 'Send ↵'}
                </button>
              </div>
            </div>
        </div>
      </div>
    </>
  );
}
