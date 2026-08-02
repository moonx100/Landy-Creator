export const API_BASE = '/api/auth';
export const DOCS_BASE = '/api/documents';
export const ANALYSES_BASE = '/api/analyses';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('landy_token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

// ── Auth ─────────────────────────────────────────────────────────────────────

/** Step 1: request OTP challenge. Returns { challenge_id, debug_otp? } */
export async function login(email: string): Promise<{ challenge_id: string; debug_otp?: string; message: string }> {
  const res = await fetch(`${API_BASE}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Terjadi kesalahan saat login.' }));
    throw new Error(error.detail || 'Terjadi kesalahan saat login.');
  }
  return res.json();
}

/** Step 2: submit OTP to get a session token. */
export async function verifyOTP(challenge_id: string, otp: string): Promise<{
  token: string; user_id: string; email: string; display_name: string | null; expires_at: string;
}> {
  const res = await fetch(`${API_BASE}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ challenge_id, otp }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Kode OTP tidak valid atau sudah kadaluarsa.' }));
    throw new Error(error.detail || 'Kode OTP tidak valid atau sudah kadaluarsa.');
  }
  return res.json();
}

export async function redeem(invite_code: string, email: string, display_name?: string): Promise<{
  token: string; user_id: string; email: string; display_name: string | null; expires_at: string;
}> {
  const res = await fetch(`${API_BASE}/redeem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ invite_code, email, display_name }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Terjadi kesalahan saat verifikasi kode.' }));
    throw new Error(error.detail || 'Terjadi kesalahan saat verifikasi kode.');
  }
  return res.json();
}

export async function getMe(): Promise<{
  user_id: string; email: string; display_name: string | null; created_at: string;
  analyses_used: number; analyses_quota: number; quota_period_start: string; is_active: boolean;
}> {
  const res = await fetch(`${API_BASE}/me`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(res.status === 401 ? 'Unauthorized' : 'Gagal mengambil data pengguna.');
  return res.json();
}

export async function logout(): Promise<{ detail: string }> {
  const res = await fetch(`${API_BASE}/logout`, { method: 'POST', headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Gagal logout.');
  return res.json();
}

// ── Document types ────────────────────────────────────────────────────────────

export interface VersionResponse {
  id: string;
  document_id: string;
  version_no: number;
  source_filename: string;
  source_format: string;
  sha256: string;
  extraction_ok: boolean;
  extraction_note: string | null;
  accuracy_warning: string | null;
  detected_language: string | null;
  uploaded_at: string;
  /** Parse status of the DOCX revision/comments layer. null = not applicable
   *  (PDF/image); 'failed' = the layer could not be read — distinct from
   *  "no revisions" / "no comments". */
  tc_parse_status: 'ok' | 'failed' | null;
  tc_parse_note: string | null;
  comments_parse_status: 'ok' | 'failed' | null;
  comments_parse_note: string | null;
}

export interface AnalysisJobResponse {
  job_id: string;
  version_id: string;
  user_id: string;
  state: string;
  stage: string | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface DocumentListItem {
  id: string;
  title: string;
  counterparty: string | null;
  created_at: string;
  version_count: number;
  latest_version: VersionResponse | null;
  latest_job: AnalysisJobResponse | null;
}

export interface VersionUploadResponse {
  version: VersionResponse;
  job_id: string;
  job_state: string;
}

// ── Document API ──────────────────────────────────────────────────────────────

export async function createDocument(title: string, counterparty?: string): Promise<{ id: string; title: string }> {
  const res = await fetch(DOCS_BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ title, counterparty }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Gagal membuat dokumen.' }));
    throw new Error(err.detail || 'Gagal membuat dokumen.');
  }
  return res.json();
}

export async function listDocuments(): Promise<DocumentListItem[]> {
  const res = await fetch(DOCS_BASE, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Gagal memuat daftar dokumen.');
  return res.json();
}

export async function deleteDocument(documentId: string): Promise<void> {
  const res = await fetch(`${DOCS_BASE}/${documentId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('Gagal menghapus dokumen.');
}

export async function uploadVersion(
  documentId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<VersionUploadResponse> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${DOCS_BASE}/${documentId}/versions`);
    const token = localStorage.getItem('landy_token');
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)); }
        catch { reject(new Error('Respons tidak valid dari server.')); }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `Upload gagal (${xhr.status}).`));
        } catch {
          reject(new Error(`Upload gagal (${xhr.status}).`));
        }
      }
    };
    xhr.onerror = () => reject(new Error('Koneksi terputus saat unggah.'));
    xhr.send(formData);
  });
}

export async function getDownloadUrl(documentId: string, versionId: string): Promise<string> {
  const res = await fetch(`${DOCS_BASE}/${documentId}/versions/${versionId}/download`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('Gagal membuat tautan unduhan.');
  const data = await res.json();
  return data.url as string;
}

// ── Analysis result types ─────────────────────────────────────────────────────

/** One comment bubble extracted from a DOCX file. */
export interface DocCommentResponse {
  id: string;
  author: string | null;
  comment_date: string | null;   // ISO-8601 string from w:date attribute
  anchor_text: string | null;    // text the comment is anchored to in the doc
  body: string;
  ordinal: number;
}

export interface CitationResponse {
  id: string;
  provision_id: string | null;  // always null in v1 — corpus not yet populated
  citation_text: string | null; // always null in v1
  basis: string | null;         // 'statutory' | 'doctrinal'
}

export interface SuggestedEditResponse {
  id: string;
  clause_id: string | null;
  original_text: string;
  revised_text: string;
  comment: string | null;
  accepted: boolean | null;  // null = undecided; true/false = user's choice before export
}

export interface RiskFlagResponse {
  id: string;
  clause_id: string | null;
  domain: string;        // taxonomy key, e.g. 'ip_ownership'
  severity: string;      // 'critical' | 'high' | 'medium' | 'info'
  finding_type: string;  // 'present_risky' | 'absent' | 'ambiguous'
  summary: string;       // one-line Bahasa Indonesia summary
  rationale: string;     // why this matters to the creator
  negotiation_ask: string | null;
  created_at: string;
  suggested_edits: SuggestedEditResponse[];
  citations: CitationResponse[];
}

export interface AnalysisResultsResponse {
  job_id: string;
  version_id: string;
  document_id: string;   // parent document — used by ReviewPage to call export endpoints
  state: string;
  stage: string | null;
  error_message: string | null;
  risk_flags: RiskFlagResponse[];
  flag_counts: { critical: number; high: number; medium: number; info: number };
  /** Comment bubbles extracted from the DOCX file. An empty list only means
   *  "no comments" when comments_parse_status is not 'failed'. */
  document_comments: DocCommentResponse[];
  /** Whether the DOCX contained unaccepted tracked changes. Only meaningful
   *  when tc_parse_status is not 'failed'. */
  has_tracked_changes: boolean;
  tc_parse_status: 'ok' | 'failed' | null;
  tc_parse_note: string | null;
  comments_parse_status: 'ok' | 'failed' | null;
  comments_parse_note: string | null;
  /** Outcome of document-summary generation (null for legacy jobs). */
  summary_status: 'ok' | 'failed' | null;
  /** Per-domain run accounting — the source of truth for completeness. */
  domains_total: number;
  domains_failed: number;
  /** Taxonomy keys of failed domains — unchecked risk categories, by name. */
  failed_domains: string[];
  /** True when the job crossed the majority-failure threshold and its quota unit was returned. */
  quota_refunded: boolean;
  /** True only when every contributing check succeeded. Absence claims may only render when true. */
  review_complete: boolean;
}

// ── Analysis API ──────────────────────────────────────────────────────────────

export async function getAnalysis(jobId: string): Promise<AnalysisJobResponse> {
  const res = await fetch(`${ANALYSES_BASE}/${jobId}`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Gagal memuat status analisis.');
  return res.json();
}

export async function triggerAnalysis(versionId: string): Promise<AnalysisJobResponse> {
  const res = await fetch(ANALYSES_BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ version_id: versionId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Gagal memulai analisis.' }));
    throw new Error(err.detail || 'Gagal memulai analisis.');
  }
  return res.json();
}

/** Fetch full risk analysis results (risk_flags + suggested_edits + citations)
 *  for a completed job. Available as soon as job.state === 'done'. */
export async function getAnalysisResults(jobId: string): Promise<AnalysisResultsResponse> {
  const res = await fetch(`${ANALYSES_BASE}/${jobId}/results`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Gagal memuat hasil analisis.');
  return res.json();
}

// ── Export + suggested-edit acceptance (Task 4) ───────────────────────────────

/** Accept (true), reject (false), or reset (null) a suggested edit. */
export async function patchSuggestedEdit(
  editId: string,
  accepted: boolean | null,
): Promise<SuggestedEditResponse & { accepted: boolean | null }> {
  const res = await fetch(`/api/suggested-edits/${editId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ accepted }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Gagal menyimpan pilihan.' }));
    throw new Error(err.detail || 'Gagal menyimpan pilihan.');
  }
  return res.json();
}

export interface DocxExportResponse {
  url: string;
  expires_in_seconds: number;
  edit_count: number;
  comment_only_count: number;
  warning: string | null;
}

export interface EmailDraftResponse {
  draft: string;
  flag_count: number;
}

/** Generate DOCX with real tracked changes. Returns a presigned download URL. */
export async function exportDocx(
  documentId: string,
  versionId: string,
): Promise<DocxExportResponse> {
  const res = await fetch(
    `${DOCS_BASE}/${documentId}/versions/${versionId}/export/docx`,
    { method: 'POST', headers: getAuthHeaders() },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Gagal menghasilkan DOCX.' }));
    throw new Error(err.detail || 'Gagal menghasilkan DOCX.');
  }
  return res.json();
}

/** Generate Bahasa Indonesia negotiation email draft via LLM. */
export async function exportEmailDraft(
  documentId: string,
  versionId: string,
): Promise<EmailDraftResponse> {
  const res = await fetch(
    `${DOCS_BASE}/${documentId}/versions/${versionId}/export/email-draft`,
    { method: 'POST', headers: getAuthHeaders() },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Gagal menghasilkan email draft.' }));
    throw new Error(err.detail || 'Gagal menghasilkan email draft.');
  }
  return res.json();
}

// ── Version diff (Task 5) ─────────────────────────────────────────────────────

export interface VersionDiffRow {
  id: string;
  from_version: string;
  to_version: string;
  clause_ref: string | null;
  change_kind: 'added' | 'removed' | 'modified';
  /** null when classification failed — the change is real but its legal
   *  significance is unknown. Never coerce to 'immaterial'. */
  materiality: 'material' | 'immaterial' | null;
  materiality_reason: string | null;
  /** Operational outcome of the classification, separate from the answer. */
  classification_status: 'ok' | 'low_confidence' | 'failed';
  classification_error: string | null;
  before_text: string | null;
  after_text: string | null;
}

export interface VersionDiffResponse {
  from_version_id: string;
  to_version_id: string;
  from_version_no: number;
  to_version_no: number;
  total_changes: number;
  material_count: number;
  immaterial_count: number;
  /** Changes whose classification failed. Counted, never derived by
   *  subtraction — total may exceed material + immaterial. */
  unclassified_count: number;
  has_changes: boolean;
  /** True only when every change was classified and the revision layer was
   *  readable. "Tidak ada perubahan material" may only render when true. */
  review_complete: boolean;
  diffs: VersionDiffRow[];
  /** Completed analysis job for the "to" version, if one exists. */
  job_id: string | null;
  /**
   * How the diff was produced:
   *   'tracked_changes' — from <w:ins>/<w:del> marks in the DOCX.
   *   'text_diff'       — from clause-level textual comparison between versions.
   */
  diff_source: 'tracked_changes' | 'text_diff';
  /** 'failed' means revisions could not be read and diff_source degraded to
   *  text_diff — the UI must say so. */
  tc_parse_status: 'ok' | 'failed' | null;
  tc_parse_note: string | null;
}

/**
 * Fetch the version diff between ver_id and its immediately prior version.
 * Returns 404 (throws) when version is v1 or diff not yet computed.
 */
export async function getVersionDiff(
  documentId: string,
  versionId: string,
): Promise<VersionDiffResponse> {
  const res = await fetch(
    `${DOCS_BASE}/${documentId}/versions/${versionId}/diff`,
    { headers: getAuthHeaders() },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Gagal memuat diff versi.' }));
    throw new Error(err.detail || 'Gagal memuat diff versi.');
  }
  return res.json();
}
