'use client';

import { memo, useMemo } from 'react';
import type {
  ActiveCitation,
  AuditFinding,
  AuditFindingsPayload,
  AuditOverviewPayload,
  AuditStatus,
} from '../lib/types';

/* ── status helpers ── */

const STATUS_ORDER: AuditStatus[] = [
  'FAIL', 'ERROR', 'CONFLICT', 'MISSING', 'ASSUMED', 'WARNING', 'PASS',
];

const STATUS_LABEL: Record<AuditStatus, { one: string; many: string }> = {
  FAIL: { one: 'Fail', many: 'Fails' },
  ERROR: { one: 'Error', many: 'Errors' },
  CONFLICT: { one: 'Conflict', many: 'Conflicts' },
  MISSING: { one: 'Missing', many: 'Missing' },
  ASSUMED: { one: 'Assumed', many: 'Assumed' },
  WARNING: { one: 'Warning', many: 'Warnings' },
  PASS: { one: 'Pass', many: 'Passes' },
};

const statusBg = (s: AuditStatus) => `var(--${s.toLowerCase()}-bg)`;
const statusFg = (s: AuditStatus) => `var(--${s.toLowerCase()}-fg)`;

const OVERVIEW_STATUS_WORD: Record<string, string> = {
  failure: 'fail',
  error: 'error',
  conflict: 'conflict',
  missing: 'missing',
  assumed: 'assumed',
  warning: 'warning',
  pass: 'pass',
};

/* ── markdown-lite: **bold**; overview mode colors status words ── */

function BoldText({
  text,
  statusColors = false,
}: {
  text: string;
  statusColors?: boolean;
}) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        const m = part.match(/^\*\*([^*]+)\*\*$/);
        if (!m) return <span key={i}>{part}</span>;
        let color = 'var(--text-primary)';
        if (statusColors) {
          const s = m[1].match(/(failure|error|conflict|missing|assumed|warning|pass)/i);
          if (s) color = `var(--${OVERVIEW_STATUS_WORD[s[1].toLowerCase()]}-fg)`;
        }
        return (
          <strong key={i} style={{ color, fontWeight: statusColors ? 500 : 600 }}>
            {m[1]}
          </strong>
        );
      })}
    </>
  );
}

/* ── small shared bits ── */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: '10px',
        textTransform: 'uppercase',
        letterSpacing: '0.12em',
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-sans)',
        fontWeight: 500,
        marginBottom: '6px',
      }}
    >
      {children}
    </div>
  );
}

function StatusPill({ status, count }: { status: AuditStatus; count: number }) {
  const label = count > 1 ? STATUS_LABEL[status].many : STATUS_LABEL[status].one;
  return (
    <span
      style={{
        background: statusBg(status),
        color: statusFg(status),
        borderRadius: '20px',
        padding: '4px 10px',
        fontSize: '11px',
        fontWeight: 500,
        fontFamily: 'var(--font-sans)',
        whiteSpace: 'nowrap',
        display: 'inline-block',
      }}
    >
      {count} {label}
    </span>
  );
}

function StatusBadge({ status }: { status: AuditStatus }) {
  return (
    <span
      style={{
        background: statusBg(status),
        color: statusFg(status),
        padding: '3px 8px',
        borderRadius: '4px',
        fontSize: '11px',
        fontWeight: 500,
        fontFamily: 'var(--font-sans)',
        whiteSpace: 'nowrap',
        display: 'inline-block',
      }}
    >
      {status}
    </span>
  );
}

/* ── table column spec ── */

const COLUMNS: Array<{ label: string; width: number }> = [
  { label: 'STATUS', width: 90 },
  { label: 'CATEGORY', width: 155 },
  { label: 'ISSUE', width: 265 },
  { label: 'REFERENCE', width: 240 },
  { label: 'ACTION', width: 200 },
];

interface AuditViewProps {
  findings: AuditFindingsPayload;
  overview: AuditOverviewPayload | null;
  onCitationClick: (c: ActiveCitation) => void;
}

const AuditView = memo(function AuditView({
  findings,
  overview,
  onCitationClick,
}: AuditViewProps) {
  const rows = findings.findings;

  /* 1-based badge numbers by unique clause, in row order */
  const clauseNumbers = useMemo(() => {
    const map = new Map<string, number>();
    for (const f of rows) {
      if (!map.has(f.clause)) map.set(f.clause, map.size + 1);
    }
    return map;
  }, [rows]);

  const pillEntries = STATUS_ORDER.filter(
    (s) => (findings.pills[s] ?? 0) > 0
  ).map((s) => [s, findings.pills[s] as number] as const);

  const referenceClick = (f: AuditFinding) => {
    const quote = f.reference.quote;
    const page = f.reference.page;
    if (!quote || page == null) return;
    const words = quote.split(/\s+/).filter(Boolean);
    onCitationClick({
      type: 'project',
      file_id: findings.file_id,
      page,
      highlight_start: words.slice(0, 5).join(' '),
      highlight_end: words.slice(-5).join(' '),
    });
  };

  const calcs = rows.filter((f) => f.calc != null);

  return (
    <div style={{ fontFamily: 'var(--font-sans)' }}>
      <style>{`
        .audit-calc summary { list-style: none; cursor: pointer; }
        .audit-calc summary::-webkit-details-marker { display: none; }
        .audit-calc .audit-calc-arrow { display: inline-block; transition: transform 0.15s ease; }
        .audit-calc[open] .audit-calc-arrow { transform: rotate(90deg); }
        .audit-cite-link:hover { text-decoration: underline; }
        @keyframes audit-shimmer { 0%, 100% { opacity: 0.45; } 50% { opacity: 1; } }
        .audit-shimmer { animation: audit-shimmer 1.4s ease-in-out infinite; }
      `}</style>

      {/* a. section label */}
      <SectionLabel>Compliance Audit</SectionLabel>

      {/* b. title + subtitle */}
      <div
        style={{
          fontSize: '16px',
          fontWeight: 500,
          color: 'var(--text-primary)',
          lineHeight: 1.4,
        }}
      >
        {findings.title}
      </div>
      <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
        {findings.subtitle}
      </div>

      {/* c. summary pills */}
      {pillEntries.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '12px' }}>
          {pillEntries.map(([s, n]) => (
            <StatusPill key={s} status={s} count={n} />
          ))}
        </div>
      )}

      {/* d. divider + overview */}
      <div
        style={{
          borderTop: '0.5px solid var(--border)',
          margin: '14px 0',
        }}
      />
      <SectionLabel>Overview</SectionLabel>
      {overview ? (
        <p
          style={{
            fontSize: '13px',
            lineHeight: 1.8,
            color: 'var(--text-secondary)',
            margin: 0,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          <BoldText text={overview.overview} statusColors />
        </p>
      ) : (
        <div
          className="audit-shimmer"
          style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic' }}
        >
          Writing overview…
        </div>
      )}

      {/* e. recommended actions */}
      {overview && overview.recommended_actions.length > 0 && (
        <div style={{ marginTop: '14px' }}>
          <SectionLabel>Recommended Actions</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {overview.recommended_actions.map((action, i) => (
              <div key={i} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                <span
                  style={{
                    color: 'var(--text-muted)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '12px',
                    lineHeight: 1.6,
                    flexShrink: 0,
                  }}
                >
                  -&gt;
                </span>
                <span
                  style={{
                    fontSize: '12px',
                    lineHeight: 1.6,
                    color: 'var(--text-secondary)',
                    wordBreak: 'break-word',
                  }}
                >
                  <BoldText text={action} />
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* f. findings table */}
      <div style={{ marginTop: '16px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            gap: '12px',
            marginBottom: '6px',
          }}
        >
          <SectionLabel>Findings — {rows.length}</SectionLabel>
          <span
            style={{
              fontSize: '11px',
              color: 'var(--text-muted)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            FAIL -&gt; ERROR -&gt; MISSING -&gt; ASSUMED -&gt; WARNING -&gt; PASS
          </span>
        </div>

        <div
          style={{
            overflowX: 'auto',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            background: 'var(--surface-2)',
          }}
        >
          <table
            style={{
              borderCollapse: 'collapse',
              minWidth: '860px',
              width: '100%',
            }}
          >
            <thead>
              <tr>
                {COLUMNS.map((col) => (
                  <th
                    key={col.label}
                    style={{
                      width: `${col.width}px`,
                      minWidth: `${col.width}px`,
                      textAlign: 'left',
                      padding: '8px 10px',
                      fontSize: '10px',
                      textTransform: 'uppercase',
                      fontWeight: 500,
                      color: 'var(--text-muted)',
                      letterSpacing: '0.08em',
                      borderBottom: '0.5px solid var(--border-strong)',
                      fontFamily: 'var(--font-sans)',
                    }}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((f, idx) => {
                const n = clauseNumbers.get(f.clause) ?? idx + 1;
                const quote = f.reference.quote;
                const page = f.reference.page;
                const sourceClickable = page != null;
                return (
                  <tr key={f.check_id} style={{ verticalAlign: 'top' }}>
                    {/* STATUS */}
                    <td
                      style={{
                        padding: '10px',
                        borderBottom: '0.5px solid var(--border)',
                      }}
                    >
                      <StatusBadge status={f.status} />
                    </td>

                    {/* CATEGORY */}
                    <td
                      style={{
                        padding: '10px',
                        borderBottom: '0.5px solid var(--border)',
                      }}
                    >
                      <div
                        style={{
                          fontSize: '12px',
                          fontWeight: 500,
                          color: 'var(--text-primary)',
                          fontFamily: 'var(--font-sans)',
                          lineHeight: 1.5,
                        }}
                      >
                        {f.name}
                      </div>
                      <div
                        style={{
                          fontSize: '11px',
                          color: 'var(--text-muted)',
                          fontFamily: 'var(--font-sans)',
                          lineHeight: 1.5,
                        }}
                      >
                        {f.category_sub}
                      </div>
                      {f.element && (
                        <span
                          style={{
                            display: 'inline-block',
                            marginTop: '4px',
                            fontSize: '10px',
                            fontFamily: 'var(--font-mono)',
                            color: 'var(--text-secondary)',
                            background: 'var(--surface-1)',
                            border: '1px solid var(--border)',
                            borderRadius: '3px',
                            padding: '1px 6px',
                          }}
                        >
                          {f.element}
                        </span>
                      )}
                    </td>

                    {/* ISSUE */}
                    <td
                      style={{
                        padding: '10px',
                        borderBottom: '0.5px solid var(--border)',
                      }}
                    >
                      <div
                        style={{
                          fontSize: '12px',
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-primary)',
                          lineHeight: 1.6,
                          wordBreak: 'break-word',
                        }}
                      >
                        {f.issue}
                      </div>
                      <div
                        style={{
                          marginTop: '4px',
                          fontSize: '11px',
                          fontFamily: 'var(--font-sans)',
                          color: 'var(--text-muted)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '5px',
                          flexWrap: 'wrap',
                        }}
                      >
                        <span>Per {f.clause}</span>
                        <button
                          onClick={() => referenceClick(f)}
                          title={quote && page != null ? 'View cited text' : undefined}
                          style={{
                            background: `var(--cite-${f.badge}-bg)`,
                            color: `var(--cite-${f.badge}-fg)`,
                            padding: '1px 6px',
                            borderRadius: '3px',
                            fontSize: '10px',
                            fontWeight: 600,
                            border: 'none',
                            cursor: quote && page != null ? 'pointer' : 'default',
                            fontFamily: 'var(--font-sans)',
                            lineHeight: 1.5,
                          }}
                        >
                          {n}
                        </button>
                      </div>
                    </td>

                    {/* REFERENCE */}
                    <td
                      style={{
                        padding: '10px',
                        borderBottom: '0.5px solid var(--border)',
                      }}
                    >
                      {quote ? (
                        <div
                          style={{
                            fontSize: '11px',
                            fontStyle: 'italic',
                            color: 'var(--text-secondary)',
                            lineHeight: 1.7,
                            fontFamily: 'var(--font-mono)',
                            wordBreak: 'break-word',
                          }}
                        >
                          &ldquo;{quote}&rdquo;
                        </div>
                      ) : (
                        <div
                          style={{
                            fontSize: '11px',
                            color: 'var(--text-muted)',
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          —
                        </div>
                      )}
                      <div
                        style={{
                          fontSize: '11px',
                          color: 'var(--text-secondary)',
                          marginTop: '3px',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        ({f.clause}).
                      </div>
                      {f.reference.source && (
                        <button
                          className={sourceClickable ? 'audit-cite-link' : undefined}
                          onClick={() => referenceClick(f)}
                          disabled={!sourceClickable}
                          style={{
                            display: 'block',
                            marginTop: '3px',
                            fontSize: '11px',
                            color: 'var(--text-accent)',
                            background: 'none',
                            border: 'none',
                            padding: 0,
                            textAlign: 'left',
                            cursor: sourceClickable ? 'pointer' : 'default',
                            fontFamily: 'var(--font-mono)',
                            lineHeight: 1.6,
                          }}
                        >
                          &gt; {f.reference.source}
                          {page != null ? ` · p.${page}` : ''}
                        </button>
                      )}
                    </td>

                    {/* ACTION */}
                    <td
                      style={{
                        padding: '10px',
                        borderBottom: '0.5px solid var(--border)',
                        fontSize: '12px',
                        fontFamily: 'var(--font-sans)',
                        color: 'var(--text-secondary)',
                        lineHeight: 1.6,
                        wordBreak: 'break-word',
                      }}
                    >
                      {f.action}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* g. calculation summaries */}
      {calcs.length > 0 && (
        <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {calcs.map((f) => (
            <details key={f.check_id} className="audit-calc">
              <summary
                style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  fontFamily: 'var(--font-sans)',
                  color: 'var(--text-primary)',
                  padding: '4px 0',
                }}
              >
                <span
                  className="audit-calc-arrow"
                  style={{ marginRight: '6px', color: 'var(--text-muted)' }}
                >
                  ▸
                </span>
                {f.calc!.label}
              </summary>
              <pre
                style={{
                  margin: '6px 0 0 0',
                  border: '1px solid var(--border-strong)',
                  background: 'var(--surface-2)',
                  borderRadius: '6px',
                  padding: '14px 16px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11.5px',
                  lineHeight: 1.7,
                  color: 'var(--text-primary)',
                  whiteSpace: 'pre-wrap',
                  overflowX: 'auto',
                }}
              >
                {f.calc!.lines.join('\n')}
              </pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
});

export default AuditView;
