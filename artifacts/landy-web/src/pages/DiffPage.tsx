/**
 * DiffPage — side-by-side version diff with materiality classification.
 * Route: /documents/:docId/versions/:versionId/diff
 *
 * Shows clause-level changes between the selected version and its predecessor.
 * Material changes are shown first (spec §1 item 5): each change is labelled
 * with materiality badge, change kind, and the Bahasa Indonesia reason.
 */
import { useEffect, useState, useCallback, useRef } from "react";
import { useLocation, useParams } from "wouter";
import {
  getVersionDiff,
  triggerAnalysis,
  VersionDiffResponse,
  VersionDiffRow,
} from "@/lib/api";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ChevronLeft, Scale, Loader2, AlertTriangle, Info,
  PlusCircle, MinusCircle, RefreshCw, ArrowRight, Sparkles,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";

// ── Helpers ───────────────────────────────────────────────────────────────────

const CHANGE_KIND_CONFIG = {
  added: {
    label: "Ditambahkan",
    badgeClass: "bg-green-600 text-white border-green-600",
    icon: PlusCircle,
    textSide: "after" as const,
  },
  removed: {
    label: "Dihapus",
    badgeClass: "bg-red-600 text-white border-red-600",
    icon: MinusCircle,
    textSide: "before" as const,
  },
  modified: {
    label: "Diubah",
    badgeClass: "bg-amber-500 text-white border-amber-500",
    icon: RefreshCw,
    textSide: "both" as const,
  },
} as const;

const MATERIALITY_CONFIG = {
  material: {
    label: "Material",
    badgeClass: "bg-rose-100 text-rose-800 border-rose-300",
    sectionClass: "border-l-4 border-l-rose-400 bg-rose-50/40",
  },
  immaterial: {
    label: "Tidak Material",
    badgeClass: "bg-slate-100 text-slate-600 border-slate-300",
    sectionClass: "border-l-4 border-l-slate-200 bg-muted/20",
  },
} as const;

// ── Diff change card ──────────────────────────────────────────────────────────

function DiffCard({ row, jobId, onNavigateReview, onStartAnalysis, triggeringAnalysis }: {
  row: VersionDiffRow;
  jobId: string | null;
  onNavigateReview: (clauseRef: string | null) => void;
  onStartAnalysis: () => void;
  triggeringAnalysis: boolean;
}) {
  const mat = MATERIALITY_CONFIG[row.materiality] ?? MATERIALITY_CONFIG.immaterial;
  const kind = CHANGE_KIND_CONFIG[row.change_kind] ?? CHANGE_KIND_CONFIG.modified;
  const KindIcon = kind.icon;
  const isMaterial = row.materiality === "material";

  return (
    <div className={`rounded-md border border-border ${mat.sectionClass} overflow-hidden`}>
      {/* Card header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/50 bg-card/60">
        <KindIcon className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
        <span className="text-sm font-medium flex-1 truncate">
          {row.clause_ref ?? "Klausul tanpa referensi"}
        </span>
        <div className="flex items-center gap-1.5 shrink-0">
          <Badge className={`text-xs border ${kind.badgeClass}`}>{kind.label}</Badge>
          <Badge className={`text-xs border ${mat.badgeClass}`}>{mat.label}</Badge>
          {isMaterial && jobId && (
            <button
              onClick={() => onNavigateReview(row.clause_ref)}
              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary/80 hover:underline transition-colors ml-1"
              title="Lihat saran negosiasi untuk klausul ini"
            >
              Lihat Saran Negosiasi
              <ArrowRight className="w-3 h-3" />
            </button>
          )}
          {isMaterial && !jobId && (
            <button
              onClick={onStartAnalysis}
              disabled={triggeringAnalysis}
              className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-primary hover:underline transition-colors ml-1 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Analisis untuk versi ini belum selesai — klik untuk memulai analisis"
            >
              {triggeringAnalysis ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Sparkles className="w-3 h-3" />
              )}
              Mulai Analisis
            </button>
          )}
        </div>
      </div>

      {/* Materiality reason */}
      {row.materiality_reason && (
        <div className="px-4 py-2 border-b border-border/30 bg-muted/10">
          <p className="text-xs text-muted-foreground italic leading-relaxed">
            {row.materiality_reason}
          </p>
        </div>
      )}

      {/* Text content */}
      <div className="p-4 space-y-3">
        {/* Before text (removed or modified) */}
        {row.before_text && (
          <div className="space-y-1">
            <p className="text-xs font-semibold text-red-600 uppercase tracking-wide">
              {row.change_kind === "removed" ? "Klausul dihapus" : "Teks sebelumnya"}
            </p>
            <div className="bg-red-50 border border-red-200 rounded p-3">
              <p className="text-sm whitespace-pre-wrap break-words leading-relaxed text-red-900">
                {row.before_text}
              </p>
            </div>
          </div>
        )}

        {/* Arrow separator for modified */}
        {row.change_kind === "modified" && row.before_text && row.after_text && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <div className="flex-1 border-t border-dashed border-border" />
            <span>diubah menjadi</span>
            <div className="flex-1 border-t border-dashed border-border" />
          </div>
        )}

        {/* After text (added or modified) */}
        {row.after_text && (
          <div className="space-y-1">
            <p className="text-xs font-semibold text-green-600 uppercase tracking-wide">
              {row.change_kind === "added" ? "Klausul baru" : "Teks baru"}
            </p>
            <div className="bg-green-50 border border-green-200 rounded p-3">
              <p className="text-sm whitespace-pre-wrap break-words leading-relaxed text-green-900">
                {row.after_text}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main DiffPage ─────────────────────────────────────────────────────────────

export default function DiffPage() {
  const params = useParams<{ docId: string; versionId: string }>();
  const { docId, versionId } = params;
  const [, setLocation] = useLocation();
  const { toast } = useToast();

  const [diff, setDiff] = useState<VersionDiffResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Initialise from sessionStorage so the button stays suppressed across reloads.
  // The stored value is a numeric timestamp (ms) representing when the flag expires.
  // A 10-minute TTL prevents the spinner from persisting forever if the backend
  // silently fails to return a job_id or throw an error.
  const sessionKey = `landy_analysis_pending_${versionId}`;
  const ANALYSIS_TTL_MS = 10 * 60 * 1000; // 10 minutes

  // Compute both initial values in a single sessionStorage read so we can
  // detect an expired entry without a second pass (the first read removes it).
  const [{ initialTriggering, initialExpiredOnMount }] = useState(() => {
    const raw = sessionStorage.getItem(sessionKey);
    if (!raw) return { initialTriggering: false, initialExpiredOnMount: false };
    const expiry = Number(raw);
    if (isNaN(expiry) || Date.now() > expiry) {
      // Expired or malformed entry — clear it so the button re-enables and
      // remember that it expired so we can warn the creator on mount.
      sessionStorage.removeItem(sessionKey);
      return { initialTriggering: false, initialExpiredOnMount: true };
    }
    return { initialTriggering: true, initialExpiredOnMount: false };
  });

  const [triggeringAnalysis, setTriggeringAnalysis] = useState(initialTriggering);
  // True only on the first render when we found an expired analysis entry.
  const [analysisExpiredOnMount] = useState(initialExpiredOnMount);

  // Ref-based in-flight guard: prevents a second call from firing before the
  // first async call resolves, even if React hasn't re-rendered yet.
  const analysisInFlight = useRef(false);

  // Filter for material/immaterial sections
  const [showMaterialOnly, setShowMaterialOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getVersionDiff(docId, versionId);
      setDiff(data);
      // If the job completed while we were away, clear the pending flag.
      if (data.job_id) {
        sessionStorage.removeItem(sessionKey);
        setTriggeringAnalysis(false);
        analysisInFlight.current = false;
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Gagal memuat diff.";
      setError(msg);
      toast({ title: "Gagal memuat perbandingan versi", description: msg, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }, [docId, versionId, sessionKey, toast]);

  useEffect(() => {
    const token = localStorage.getItem("landy_token");
    if (!token) { setLocation("/login"); return; }
    load();
  }, [load, setLocation]);

  // Warn the creator if a previous analysis attempt timed out while they were away.
  useEffect(() => {
    if (!analysisExpiredOnMount) return;
    toast({
      title: "Analisis sebelumnya tidak selesai",
      description:
        "Sesi analisis sebelumnya habis waktu sebelum selesai. Silakan mulai analisis kembali.",
      variant: "destructive",
    });
  // We only want this to run once on mount; toast is stable.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Navigate to ReviewPage, optionally passing a clause ref for deep-linking
  const handleNavigateReview = useCallback((clauseRef: string | null) => {
    if (!diff?.job_id) return;
    const base = `/review/${diff.job_id}`;
    const target = clauseRef
      ? `${base}?clauseRef=${encodeURIComponent(clauseRef)}`
      : base;
    setLocation(target);
  }, [diff, setLocation]);

  // Trigger analysis for the "to" version and navigate to ReviewPage on success.
  // The ref guard prevents a second in-flight call even before React re-renders.
  // sessionStorage persists the in-flight state across page reloads.
  const handleTriggerAnalysis = useCallback(async () => {
    if (!diff || analysisInFlight.current || triggeringAnalysis) return;
    analysisInFlight.current = true;
    sessionStorage.setItem(sessionKey, String(Date.now() + ANALYSIS_TTL_MS));
    setTriggeringAnalysis(true);
    try {
      const job = await triggerAnalysis(diff.to_version_id);
      sessionStorage.removeItem(sessionKey);
      setLocation(`/review/${job.job_id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Gagal memulai analisis.";
      toast({ title: "Gagal memulai analisis", description: msg, variant: "destructive" });
      analysisInFlight.current = false;
      sessionStorage.removeItem(sessionKey);
      setTriggeringAnalysis(false);
    }
  }, [diff, sessionKey, triggeringAnalysis, setLocation, toast]);

  // ── Render ────────────────────────────────────────────────────────────────

  const filteredDiffs = diff
    ? showMaterialOnly
      ? diff.diffs.filter((d) => d.materiality === "material")
      : diff.diffs
    : [];

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <DisclaimerBanner />

      {/* Navbar */}
      <header className="border-b border-border bg-card sticky top-0 z-10">
        <div className="max-w-screen-lg mx-auto px-4 h-14 flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setLocation("/")}
            className="gap-1.5 text-muted-foreground"
          >
            <ChevronLeft className="w-4 h-4" />Beranda
          </Button>
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <Scale className="w-5 h-5 text-primary shrink-0" />
            <span className="font-serif font-semibold text-primary">LANDY</span>
            <span className="text-muted-foreground/40 mx-1">·</span>
            <span className="text-sm text-muted-foreground truncate">
              {diff
                ? `Perubahan: v${diff.from_version_no} → v${diff.to_version_no}`
                : "Perbandingan Versi"}
            </span>
          </div>
          {/* CTA: jump to review if analysis exists, or start one if material changes present */}
          {diff?.job_id ? (
            <Button
              size="sm"
              className="gap-1.5 text-xs shrink-0"
              onClick={() => handleNavigateReview(null)}
            >
              Tinjau Analisis
              <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          ) : diff && diff.material_count > 0 && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs shrink-0"
              onClick={handleTriggerAnalysis}
              disabled={triggeringAnalysis}
              title="Analisis untuk versi ini belum selesai — klik untuk memulai"
            >
              {triggeringAnalysis ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Sparkles className="w-3.5 h-3.5" />
              )}
              Mulai Analisis
            </Button>
          )}
        </div>
      </header>

      <main className="flex-1 max-w-screen-lg mx-auto w-full px-4 py-6 space-y-6">

        {/* Error state */}
        {error && (
          <div className="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 p-4">
            <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">Perbandingan tidak tersedia</p>
              <p className="text-xs text-amber-700 mt-0.5">{error}</p>
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 mt-1 text-xs text-amber-700"
                onClick={load}
              >
                Coba lagi
              </Button>
            </div>
          </div>
        )}

        {diff && (
          <>
            {/* Summary header */}
            <div className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                  <h1 className="font-semibold text-base">
                    Perbandingan v{diff.from_version_no} → v{diff.to_version_no}
                  </h1>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {diff.total_changes} klausul berubah
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {diff.material_count > 0 && (
                    <span className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full bg-rose-100 text-rose-800 border border-rose-200">
                      <AlertTriangle className="w-3 h-3" />
                      {diff.material_count} material
                    </span>
                  )}
                  {diff.immaterial_count > 0 && (
                    <span className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                      <Info className="w-3 h-3" />
                      {diff.immaterial_count} tidak material
                    </span>
                  )}
                  {diff.material_count > 0 && diff.immaterial_count > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs h-7"
                      onClick={() => setShowMaterialOnly((v) => !v)}
                    >
                      {showMaterialOnly ? "Tampilkan semua" : "Material saja"}
                    </Button>
                  )}
                </div>
              </div>

              {/* Materiality info note */}
              <div className="flex items-start gap-2 mt-3 pt-3 border-t border-border">
                <Info className="w-3.5 h-3.5 text-muted-foreground shrink-0 mt-0.5" />
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Perubahan <strong>material</strong> menggeser posisi hukum Anda secara nyata.
                  Perubahan <strong>tidak material</strong> bersifat redaksional.
                  Klasifikasi dilakukan oleh AI — selalu verifikasi dengan advokat sebelum menandatangani.
                </p>
              </div>
            </div>

            {/* No-analysis prompt — shown when there are material changes but no completed job */}
            {!diff.job_id && diff.material_count > 0 && (
              <div className="flex items-start gap-3 rounded-lg border border-violet-200 bg-violet-50 p-4">
                <Sparkles className="w-5 h-5 text-violet-500 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-violet-900">
                    Analisis belum tersedia untuk versi ini
                  </p>
                  <p className="text-xs text-violet-700 mt-0.5 leading-relaxed">
                    Terdapat {diff.material_count} perubahan material yang perlu ditinjau. Mulai analisis untuk mendapatkan saran negosiasi dan identifikasi risiko.
                  </p>
                </div>
                <Button
                  size="sm"
                  className="gap-1.5 text-xs shrink-0 bg-violet-600 hover:bg-violet-700 text-white"
                  onClick={handleTriggerAnalysis}
                  disabled={triggeringAnalysis}
                >
                  {triggeringAnalysis ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="w-3.5 h-3.5" />
                  )}
                  {triggeringAnalysis ? "Memulai…" : "Mulai Analisis"}
                </Button>
              </div>
            )}

            {/* Change list */}
            {filteredDiffs.length > 0 ? (
              <div className="space-y-3">
                {/* Material section header */}
                {!showMaterialOnly && diff.material_count > 0 && diff.immaterial_count > 0 && (
                  <p className="text-xs font-semibold text-rose-700 uppercase tracking-wide px-1">
                    Perubahan Material ({diff.material_count})
                  </p>
                )}
                {filteredDiffs
                  .filter((d) => showMaterialOnly || d.materiality === "material")
                  .map((row) => (
                    <DiffCard
                      key={row.id}
                      row={row}
                      jobId={diff.job_id}
                      onNavigateReview={handleNavigateReview}
                      onStartAnalysis={handleTriggerAnalysis}
                      triggeringAnalysis={triggeringAnalysis}
                    />
                  ))}

                {/* Immaterial section header */}
                {!showMaterialOnly && diff.immaterial_count > 0 && (
                  <>
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide px-1 pt-2">
                      Perubahan Tidak Material ({diff.immaterial_count})
                    </p>
                    {filteredDiffs
                      .filter((d) => d.materiality === "immaterial")
                      .map((row) => (
                        <DiffCard
                          key={row.id}
                          row={row}
                          jobId={diff.job_id}
                          onNavigateReview={handleNavigateReview}
                          onStartAnalysis={handleTriggerAnalysis}
                          triggeringAnalysis={triggeringAnalysis}
                        />
                      ))}
                  </>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
                <Scale className="w-10 h-10 text-primary/30" />
                <p className="text-sm text-muted-foreground">
                  {showMaterialOnly
                    ? "Tidak ada perubahan material yang terdeteksi."
                    : "Tidak ada perubahan yang terdeteksi antara kedua versi."}
                </p>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
