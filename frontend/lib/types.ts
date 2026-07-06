export interface UploadedFile {
  file_id: string;
  filename: string;
  type: 'pdf' | 'excel';
  classification: 'STANDARD' | 'PROJECT' | 'UNKNOWN';
  rag_status?: 'not_applicable' | 'pending' | 'embedded' | 'failed';
  rag_collection?: string | null;
  rag_error?: string | null;
}

export interface ComplianceRow {
  // verdict
  status: 'FAIL' | 'WARN' | 'PASS';
  category: string;
  issue: string;
  party_affected: string;
  recommendation: string;

  // PROJECT citation — where problem was found
  project_file_id: string | null;
  reference_text: string | null;
  source_page: number | null;
  highlight_start: string | null;
  highlight_end: string | null;

  // STANDARD citation — what was violated
  standard_file_id: string | null;
  standard_clause: string | null;
  standard_page: number | null;
  standard_text: string | null;
}

export interface ActiveCitation {
  type: 'project' | 'standard';
  file_id: string;
  page: number;
  highlight_start: string;
  highlight_end: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
  table?: ComplianceRow[];
  citations?: ActiveCitation[];
}

export interface ChatRequest {
  message: string;
  file_id: string | null;
  history: Array<{ role: 'user' | 'assistant'; content: string }>;
}

export interface ChatStreamChunk {
  type: 'token' | 'done' | 'error' | 'table';
  content?: string;
  message?: string;
  data?: ComplianceRow[];
}

export interface HealthResponse {
  status: string;
  mcp_connected: boolean;
  mcp_pid: number | null;
  tools: string[];
  cache_size: {
    coords: number;
    in_flight_chats: number;
  };
}

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
