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
