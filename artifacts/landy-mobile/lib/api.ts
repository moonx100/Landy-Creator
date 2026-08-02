/**
 * LANDY Mobile API client.
 * Mirrors artifacts/landy-web/src/lib/api.ts, adapted for React Native:
 *   - Token read from AsyncStorage (injected via getToken getter)
 *   - Base URL derived from EXPO_PUBLIC_DOMAIN env var
 */

// The token getter is set by the AuthContext so the API module doesn't
// need to import AsyncStorage directly (avoids circular imports).
let _getToken: () => Promise<string | null> = async () => null;
export function setTokenGetter(fn: () => Promise<string | null>) {
  _getToken = fn;
}

function apiBase(): string {
  const domain = process.env.EXPO_PUBLIC_DOMAIN;
  if (!domain) return '';
  return `https://${domain}`;
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await _getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Request failed (${res.status})` }));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Request failed (${res.status})` }));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export async function login(email: string): Promise<{ challenge_id: string; debug_otp?: string; message: string }> {
  return apiPost('/api/auth/login', { email });
}

export async function verifyOTP(challenge_id: string, otp: string): Promise<{
  token: string; user_id: string; email: string; display_name: string | null; expires_at: string;
}> {
  return apiPost('/api/auth/verify', { challenge_id, otp });
}

export async function getMe(): Promise<{
  user_id: string; email: string; display_name: string | null; created_at: string;
  analyses_used: number; analyses_quota: number; quota_period_start: string; is_active: boolean;
}> {
  return apiGet('/api/auth/me');
}

export async function logout(): Promise<{ detail: string }> {
  const res = await fetch(`${apiBase()}/api/auth/logout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
  });
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

// ── Documents ─────────────────────────────────────────────────────────────────

export async function listDocuments(): Promise<DocumentListItem[]> {
  return apiGet('/api/documents');
}

// ── Diff types & API ─────────────────────────────────────────────────────────

export interface VersionDiffRow {
  id: string;
  from_version: string;
  to_version: string;
  clause_ref: string | null;
  change_kind: 'added' | 'removed' | 'modified';
  /** null when classification failed — never coerce to 'immaterial'. */
  materiality: 'material' | 'immaterial' | null;
  materiality_reason: string | null;
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
  has_changes: boolean;
  diffs: VersionDiffRow[];
  job_id: string | null;
}

export async function getVersionDiff(documentId: string, versionId: string): Promise<VersionDiffResponse> {
  return apiGet(`/api/documents/${documentId}/versions/${versionId}/diff`);
}

// ── Analysis ──────────────────────────────────────────────────────────────────

export async function triggerAnalysis(versionId: string): Promise<AnalysisJobResponse> {
  return apiPost('/api/analyses', { version_id: versionId });
}

export async function getAnalysis(jobId: string): Promise<AnalysisJobResponse> {
  return apiGet(`/api/analyses/${jobId}`);
}

// ── Risk flag types ───────────────────────────────────────────────────────────

export interface RiskFlagResponse {
  id: string;
  clause_id: string | null;
  domain: string;
  severity: string;
  finding_type: string;
  summary: string;
  rationale: string;
  negotiation_ask: string | null;
  created_at: string;
}

export interface AnalysisResultsResponse {
  job_id: string;
  version_id: string;
  document_id: string;
  state: string;
  stage: string | null;
  error_message: string | null;
  risk_flags: RiskFlagResponse[];
  flag_counts: { critical: number; high: number; medium: number; info: number };
}

export async function getAnalysisResults(jobId: string): Promise<AnalysisResultsResponse> {
  return apiGet(`/api/analyses/${jobId}/results`);
}
