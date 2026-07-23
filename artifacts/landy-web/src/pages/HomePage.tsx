import { useEffect, useState, useCallback, useRef } from "react";
import { useLocation } from "wouter";
import {
  getMe, logout, listDocuments, deleteDocument, getDownloadUrl,
  DocumentListItem, AnalysisJobResponse, getAnalysis,
} from "@/lib/api";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { OnboardingModal } from "@/components/OnboardingModal";
import { UploadModal } from "@/components/UploadModal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Scale, LogOut, FileText, Upload, Plus, Trash2, Download,
  Loader2, CheckCircle2, AlertTriangle, Clock, RefreshCw, Search, GitCompare,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface User {
  user_id: string;
  email: string;
  display_name: string | null;
  analyses_used: number;
  analyses_quota: number;
}

// ── Job status helpers ────────────────────────────────────────────────────────

function JobBadge({ job }: { job: AnalysisJobResponse | null }) {
  if (!job) return <Badge variant="secondary">Belum dianalisis</Badge>;
  switch (job.state) {
    case "queued":
      return <Badge variant="secondary" className="gap-1"><Clock className="w-3 h-3" />Antrian</Badge>;
    case "running":
      return <Badge variant="outline" className="gap-1 text-blue-600 border-blue-300"><Loader2 className="w-3 h-3 animate-spin" />{job.stage || "Memproses"}</Badge>;
    case "done":
      if (job.stage === "Selesai") {
        return <Badge variant="default" className="gap-1 bg-green-600"><CheckCircle2 className="w-3 h-3" />Selesai</Badge>;
      }
      return <Badge variant="default" className="gap-1 bg-amber-600"><AlertTriangle className="w-3 h-3" />Selesai (ada peringatan)</Badge>;
    case "failed":
      return <Badge variant="destructive" className="gap-1"><AlertTriangle className="w-3 h-3" />Gagal</Badge>;
    default:
      return <Badge variant="secondary">{job.state}</Badge>;
  }
}

function ExtractionBadge({ doc }: { doc: DocumentListItem }) {
  const v = doc.latest_version;
  if (!v) return null;
  if (!v.extraction_ok) {
    return <Badge variant="destructive" className="text-xs gap-1"><AlertTriangle className="w-3 h-3" />Ekstraksi gagal</Badge>;
  }
  if (v.accuracy_warning) {
    return <Badge variant="outline" className="text-xs gap-1 text-amber-600 border-amber-300"><AlertTriangle className="w-3 h-3" />Akurasi OCR bervariasi</Badge>;
  }
  return null;
}

// ── Main component ────────────────────────────────────────────────────────────

export default function HomePage() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const [user, setUser] = useState<User | null>(null);
  const [pageLoading, setPageLoading] = useState(true);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [activeJobIds, setActiveJobIds] = useState<Set<string>>(new Set());
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Auth ──────────────────────────────────────────────────────────────────
  const fetchUser = useCallback(async () => {
    try {
      const data = await getMe();
      setUser(data);
    } catch (err: unknown) {
      if (err instanceof Error && err.message === 'Unauthorized') {
        localStorage.removeItem("landy_token");
        setLocation("/login");
      } else {
        toast({ title: "Gagal memuat profil", variant: "destructive" });
      }
    } finally {
      setPageLoading(false);
    }
  }, [setLocation, toast]);

  // ── Documents ─────────────────────────────────────────────────────────────
  const fetchDocuments = useCallback(async () => {
    setDocsLoading(true);
    try {
      const docs = await listDocuments();
      setDocuments(docs);
      // Collect IDs of in-flight jobs to poll
      const inFlight = new Set<string>();
      for (const doc of docs) {
        if (doc.latest_job && (doc.latest_job.state === "queued" || doc.latest_job.state === "running")) {
          inFlight.add(doc.latest_job.job_id);
        }
      }
      setActiveJobIds(inFlight);
    } catch {
      // silently ignore list errors — user stays on page
    } finally {
      setDocsLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("landy_token");
    if (!token) { setLocation("/login"); return; }
    fetchUser();
    fetchDocuments();
  }, [fetchUser, fetchDocuments, setLocation]);

  // ── Job polling (every 3 s while any job is in flight) ────────────────────
  useEffect(() => {
    if (activeJobIds.size === 0) {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const updates = await Promise.all(
          [...activeJobIds].map((id) => getAnalysis(id))
        );
        let anyDone = false;
        for (const job of updates) {
          if (job.state === "done" || job.state === "failed") anyDone = true;
        }
        if (anyDone) {
          // Refresh full document list when any job lands
          await fetchDocuments();
          await fetchUser(); // refresh quota
        } else {
          // Just update job state in documents list in-place
          setDocuments((prev) =>
            prev.map((doc) => {
              const updated = updates.find((j) => j.job_id === doc.latest_job?.job_id);
              if (updated) return { ...doc, latest_job: updated };
              return doc;
            })
          );
        }
      } catch {
        // ignore polling errors
      }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeJobIds, fetchDocuments, fetchUser]);

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleLogout = async () => {
    try { await logout(); } catch { /* ignore */ }
    localStorage.removeItem("landy_token");
    setLocation("/login");
  };

  const handleDelete = async (docId: string, title: string) => {
    if (!confirm(`Hapus "${title}"? Data akan dihapus permanen setelah 30 hari.`)) return;
    try {
      await deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      toast({ title: "Dokumen dihapus" });
    } catch {
      toast({ title: "Gagal menghapus dokumen", variant: "destructive" });
    }
  };

  const handleDownload = async (docId: string, versionId: string) => {
    try {
      const url = await getDownloadUrl(docId, versionId);
      window.open(url, "_blank");
    } catch {
      toast({ title: "Gagal membuat tautan unduhan", variant: "destructive" });
    }
  };

  const handleUploadSuccess = (_jobId: string) => {
    fetchDocuments();
    fetchUser();
  };

  const handleReview = (doc: DocumentListItem) => {
    const job = doc.latest_job;
    if (!job || job.state !== "done") return;
    // ReviewPage fetches document_id and version_id from the API results directly —
    // no sessionStorage needed; deep-linking to /review/:jobId always works.
    setLocation(`/review/${job.job_id}`);
  };

  const handleViewDiff = (doc: DocumentListItem) => {
    const ver = doc.latest_version;
    if (!ver || ver.version_no <= 1) return;
    setLocation(`/documents/${doc.id}/versions/${ver.id}/diff`);
  };

  if (pageLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Scale className="w-8 h-8 text-primary animate-pulse" />
      </div>
    );
  }
  if (!user) return null;

  const quotaPercentage = user.analyses_quota > 0
    ? Math.min(100, (user.analyses_used / user.analyses_quota) * 100)
    : 0;

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <DisclaimerBanner />

      {/* Navbar */}
      <header className="border-b border-border bg-card">
        <div className="max-w-5xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Scale className="w-6 h-6 text-primary" />
            <span className="font-serif font-semibold text-lg tracking-tight text-primary">LANDY</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium hidden sm:inline-block">
              {user.display_name || user.email}
            </span>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-muted-foreground hover:text-foreground">
              <LogOut className="w-4 h-4 mr-2" />Keluar
            </Button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 w-full max-w-5xl mx-auto px-4 py-8 space-y-8">
        {/* Hero row */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-3xl font-serif font-bold text-foreground">
              Halo, {user.display_name || "Kreator"}
            </h1>
            <p className="text-muted-foreground mt-1">
              Kelola dan analisis kontrak kerja sama Anda dengan aman.
            </p>
          </div>
          <Button
            className="shrink-0 gap-2"
            onClick={() => setUploadOpen(true)}
            disabled={user.analyses_used >= user.analyses_quota}
          >
            <Plus className="w-4 h-4" />
            Unggah Kontrak
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Quota card */}
          <Card className="col-span-1 border-border shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Kuota Analisis</CardTitle>
              <CardDescription>Penggunaan periode ini</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex justify-between text-sm">
                <span className="font-medium">{user.analyses_used} Kontrak</span>
                <span className="text-muted-foreground">dari {user.analyses_quota}</span>
              </div>
              <Progress value={quotaPercentage} className="h-2" />
              {user.analyses_used >= user.analyses_quota && (
                <p className="text-xs text-destructive mt-2">
                  Kuota habis. Akan dipulihkan awal bulan depan.
                </p>
              )}
              <p className="text-xs text-muted-foreground leading-relaxed">
                Setiap unggahan kontrak menggunakan 1 kuota analisis.
              </p>
            </CardContent>
          </Card>

          {/* Document list */}
          <Card className="col-span-1 md:col-span-2 border-border shadow-sm flex flex-col">
            <CardHeader className="flex-row justify-between items-center pb-3">
              <div>
                <CardTitle className="text-lg">Daftar Kontrak</CardTitle>
                <CardDescription>Dokumen yang telah Anda unggah</CardDescription>
              </div>
              {documents.length > 0 && (
                <Button variant="ghost" size="sm" onClick={fetchDocuments} disabled={docsLoading}>
                  <RefreshCw className={`w-4 h-4 ${docsLoading ? "animate-spin" : ""}`} />
                </Button>
              )}
            </CardHeader>
            <CardContent className="flex-1">
              {docsLoading && documents.length === 0 ? (
                <div className="flex items-center justify-center h-32">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : documents.length === 0 ? (
                <div className="flex flex-col items-center text-center min-h-[200px] justify-center border border-dashed rounded-md p-6 bg-muted/20">
                  <div className="w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center mb-4">
                    <FileText className="w-6 h-6 text-primary" />
                  </div>
                  <h3 className="font-semibold mb-2">Belum ada dokumen</h3>
                  <p className="text-sm text-muted-foreground mb-6">
                    Unggah kontrak pertama Anda untuk melihat potensi risiko dan saran negosiasi.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => setUploadOpen(true)}
                    disabled={user.analyses_used >= user.analyses_quota}
                  >
                    <Upload className="w-4 h-4 mr-2" />Unggah Kontrak Pertama Anda
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="flex items-start gap-3 p-3 rounded-md border border-border hover:bg-muted/20 transition-colors"
                    >
                      <FileText className="w-8 h-8 text-primary shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2 flex-wrap">
                          <div>
                            <p className="font-medium text-sm truncate">{doc.title}</p>
                            {doc.counterparty && (
                              <p className="text-xs text-muted-foreground">{doc.counterparty}</p>
                            )}
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            <JobBadge job={doc.latest_job} />
                          </div>
                        </div>
                        <div className="flex items-center gap-2 mt-2 flex-wrap">
                          <span className="text-xs text-muted-foreground">
                            {doc.version_count} versi ·{" "}
                            {new Date(doc.created_at).toLocaleDateString("id-ID", {
                              day: "numeric", month: "short", year: "numeric",
                            })}
                          </span>
                          <ExtractionBadge doc={doc} />
                          {doc.latest_job?.state === "running" && doc.latest_job.stage && (
                            <span className="text-xs text-blue-600">{doc.latest_job.stage}</span>
                          )}
                          {doc.latest_job?.state === "failed" && doc.latest_job.error_message && (
                            <span className="text-xs text-destructive truncate max-w-xs">
                              {doc.latest_job.error_message}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {/* Diff button — when version_no > 1 and analysis done */}
                        {doc.latest_job?.state === "done" &&
                          doc.latest_version &&
                          doc.latest_version.version_no > 1 && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="gap-1.5 text-xs h-8 text-muted-foreground hover:text-foreground"
                            title="Lihat perubahan dari versi sebelumnya"
                            onClick={() => handleViewDiff(doc)}
                          >
                            <GitCompare className="w-3.5 h-3.5" />Perubahan
                          </Button>
                        )}
                        {/* Review button — available when analysis is done */}
                        {doc.latest_job?.state === "done" && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1.5 text-xs h-8 text-primary border-primary/40 hover:bg-primary/5"
                            title="Tinjau hasil analisis"
                            onClick={() => handleReview(doc)}
                          >
                            <Search className="w-3.5 h-3.5" />Tinjau
                          </Button>
                        )}
                        {doc.latest_version && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="w-8 h-8 text-muted-foreground hover:text-foreground"
                            title="Unduh kontrak"
                            onClick={() => handleDownload(doc.id, doc.latest_version!.id)}
                          >
                            <Download className="w-4 h-4" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="w-8 h-8 text-muted-foreground hover:text-destructive"
                          title="Hapus dokumen"
                          onClick={() => handleDelete(doc.id, doc.title)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </main>

      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSuccess={handleUploadSuccess}
      />
      <OnboardingModal userDisplayName={user.display_name} onDismiss={() => {}} />
    </div>
  );
}
