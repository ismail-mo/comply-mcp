export interface UploadedFile {
  file_id: string;
  filename: string;
  type: 'pdf' | 'excel';
  classification: 'STANDARD' | 'PROJECT' | 'UNKNOWN';
  rag_status?: 'not_applicable' | 'pending' | 'embedded' | 'failed';
  rag_collection?: string | null;
  rag_error?: string | null;
  /** Stage 0 result — present only on the upload response for a PROJECT pdf */
  indexed_elements?: { type: string; designation?: string | null }[] | null;
}

/* ── Audit output (deterministic engine contract) ── */

export type AuditStatus =
  | 'FAIL' | 'ERROR' | 'CONFLICT' | 'MISSING' | 'ASSUMED' | 'WARNING' | 'PASS';

export type CiteBadge = 'ec3' | 'en1990' | 'en10025' | 'report' | 'sbb';

export interface AuditReference {
  quote: string | null;
  clause: string;
  page: number | null;
  source: string | null;
}

export interface AuditCalc {
  label: string;
  lines: string[];
}

export interface AuditFinding {
  check_id: string;
  status: AuditStatus;
  name: string;
  category_sub: string;
  clause: string;
  badge: CiteBadge;
  issue: string;
  action: string;
  reference: AuditReference;
  calc: AuditCalc | null;
  metrics: Record<string, number | string | null>;
  assumed_inputs: string[];
  element?: string;
  designation?: string | null;
}

export interface AuditFindingsPayload {
  title: string;
  subtitle: string;
  document: string;
  file_id: string;
  pills: Partial<Record<AuditStatus, number>>;
  findings: AuditFinding[];
}

export interface AuditOverviewPayload {
  overview: string;
  recommended_actions: string[];
}

export interface QuickRef {
  clause: string | null;
  source: string | null;
  page: number | null;
}

/* ── Citation navigation (PDF viewer) ── */

export interface ActiveCitation {
  type: 'project' | 'standard';
  file_id: string;
  page: number;
  highlight_start: string;
  highlight_end: string;
}

/* ── Chat ── */

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
  status?: string | null;
  auditFindings?: AuditFindingsPayload | null;
  auditOverview?: AuditOverviewPayload | null;
  quickRefs?: QuickRef[] | null;
  timing?: Record<string, number> | null;
}

export interface ChatRequest {
  message: string;
  file_id: string | null;
  history: Array<{ role: 'user' | 'assistant'; content: string }>;
}

export interface ChatStreamChunk {
  type:
    | 'token' | 'done' | 'error' | 'status'
    | 'findings' | 'overview' | 'quick_refs'
    | 'table' | 'reset_text'; // legacy, tolerated
  content?: string;
  message?: string;
  data?: unknown;
  timing?: Record<string, number>;
}

export interface HealthResponse {
  status: string;
  mcp_connected: boolean;
  mcp_pid: number | null;
  tools: string[];
  cache_size: { coords: number };
}

/* ── PDF coordinates ── */

export interface PdfWord {
  text: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface PdfPage {
  width: number;
  height: number;
  words: PdfWord[];
}

export interface PdfCoordinates {
  page_count: number;
  pages: Record<string, PdfPage>;
}
