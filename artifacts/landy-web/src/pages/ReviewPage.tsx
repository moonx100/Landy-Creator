/**
 * ReviewPage — per-job contract analysis review screen.
 * Route: /review/:jobId
 *
 * Layout:
 *   Left panel  — risk flags grouped by severity (critical → high → medium → info)
 *   Right panel — selected flag detail: rationale, negotiation ask, suggested edits
 *
 * Spec §8, §9.6: disclaimer shown prominently. Absence findings shown in a
 * dedicated "Klausul Tidak Ditemukan" section.
 */
import { useEffect, useState, useCallback } from "react";
import { useLocation, useParams } from "wouter";
import {
  getAnalysisResults, patchSuggestedEdit, exportDocx, exportEmailDraft,
  AnalysisResultsResponse, RiskFlagResponse, SuggestedEditResponse,
} from "@/lib/api";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Scale, ChevronLeft, AlertTriangle, Info, Check, X, Minus,
  FileDown, Mail, Copy, Loader2, ChevronDown, ChevronUp, RefreshCw,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";

// ── Domain label map ──────────────────────────────────────────────────────────

const DOMAIN_LABELS: Record<string, string> = {
  scope_deliverables: "Lingkup & Deliverabel",
  exclusivity: "Eksklusivitas",
  ip_ownership: "Kepemilikan IP",
  moral_rights: "Hak Moral",
  usage_rights: "Hak Penggunaan & Media",
  payment_terms: "Pembayaran & Pajak",
  term_termination: "Jangka Waktu & Pemutusan",
  morality_clause: "Klausul Moralitas",
  content_approval: "Persetujuan & Takedown",
  confidentiality: "Kerahasiaan",
  personal_data_likeness: "Data Pribadi & Rupa",
  liability_indemnity: "Kewajiban & Ganti Rugi",
  non_compete: "Larangan Bersaing",
  dispute_forum: "Forum Penyelesaian Sengketa",
  governing_language: "Bahasa Hukum",
  agency_commission: "Komisi Agensi",
  disclosure_compliance: "Pengungkapan Iklan",
  execution_validity: "Keabsahan Eksekusi",
};

// ── Severity helpers ──────────────────────────────────────────────────────────

const SEVERITY_ORDER = ["critical", "high", "medium", "info"] as const;

const SEVERITY_CONFIG = {
  critical: {
    label: "Kritis",
    badgeClass: "bg-red-600 text-white border-red-600",
    headerClass: "text-red-700 border-red-200 bg-red-50",
    dotClass: "bg-red-500",
  },
  high: {
    label: "Tinggi",
    badgeClass: "bg-orange-500 text-white border-orange-500",
    headerClass: "text-orange-700 border-orange-200 bg-orange-50",
    dotClass: "bg-orange-500",
  },
  medium: {
    label: "Sedang",
    badgeClass: "bg-yellow-500 text-white border-yellow-500",
    headerClass: "text-yellow-700 border-yellow-200 bg-yellow-50",
    dotClass: "bg-yellow-500",
  },
  info: {
    label: "Info",
    badgeClass: "bg-blue-500 text-white border-blue-500",
    headerClass: "text-blue-700 border-blue-200 bg-blue-50",
    dotClass: "bg-blue-500",
  },
} as const;

type Severity = keyof typeof SEVERITY_CONFIG;

// ── Sub-components ─────────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const cfg = SEVERITY_CONFIG[severity as Severity] ?? SEVERITY_CONFIG.info;
  return (
    <Badge className={`text-xs font-semibold px-2 py-0.5 border ${cfg.badgeClass}`}>
      {cfg.label}
    </Badge>
  );
}

function FindingTypeBadge({ findingType }: { findingType: string }) {
  if (findingType === "absent") {
    return <Badge variant="outline" className="text-xs text-muted-foreground">Tidak ditemukan</Badge>;
  }
  if (findingType === "ambiguous") {
    return <Badge variant="outline" className="text-xs text-amber-600 border-amber-400">Ambigu</Badge>;
  }
  return null; // present_risky shows no extra badge
}

// ── Suggested edit card ────────────────────────────────────────────────────────

function SuggestedEditCard({
  edit,
  onAccept,
  onReject,
  onReset,
}: {
  edit: SuggestedEditResponse & { accepted: boolean | null };
  onAccept: () => void;
  onReject: () => void;
  onReset: () => void;
}) {
  return (
    <div className="rounded-md border border-border bg-muted/20 p-3 space-y-3">
      {/* Diff view */}
      <div className="space-y-2 text-sm font-mono">
        <div className="bg-red-50 border border-red-200 rounded p-2">
          <span className="text-xs text-red-600 font-sans font-medium block mb-1">Teks Asli</span>
          <span className="text-red-800 line-through whitespace-pre-wrap break-words">
            {edit.original_text}
          </span>
        </div>
        <div className="bg-green-50 border border-green-200 rounded p-2">
          <span className="text-xs text-green-600 font-sans font-medium block mb-1">Usulan</span>
          <span className="text-green-800 whitespace-pre-wrap break-words">
            {edit.revised_text}
          </span>
        </div>
      </div>
      {edit.comment && (
        <p className="text-xs text-muted-foreground italic">{edit.comment}</p>
      )}

      {/* Accept / Reject / Undecided buttons */}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant={edit.accepted === true ? "default" : "outline"}
          className={`gap-1 text-xs h-7 ${edit.accepted === true ? "bg-green-600 hover:bg-green-700 text-white" : "border-green-400 text-green-700 hover:bg-green-50"}`}
          onClick={onAccept}
        >
          <Check className="w-3 h-3" />Terima
        </Button>
        <Button
          size="sm"
          variant={edit.accepted === false ? "default" : "outline"}
          className={`gap-1 text-xs h-7 ${edit.accepted === false ? "bg-red-600 hover:bg-red-700 text-white" : "border-red-400 text-red-700 hover:bg-red-50"}`}
          onClick={onReject}
        >
          <X className="w-3 h-3" />Tolak
        </Button>
        {edit.accepted !== null && (
          <Button
            size="sm"
            variant="ghost"
            className="gap-1 text-xs h-7 text-muted-foreground"
            onClick={onReset}
          >
            <Minus className="w-3 h-3" />Reset
          </Button>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          {edit.accepted === null && "Belum diputuskan"}
          {edit.accepted === true && <span className="text-green-600 font-medium">Diterima → masuk ke DOCX</span>}
          {edit.accepted === false && <span className="text-red-600 font-medium">Ditolak → tidak masuk DOCX</span>}
        </span>
      </div>
    </div>
  );
}

// ── Flag detail panel ─────────────────────────────────────────────────────────

function FlagDetail({
  flag,
  onEditChange,
}: {
  flag: RiskFlagResponse & { suggested_edits: (SuggestedEditResponse & { accepted: boolean | null })[] };
  onEditChange: (editId: string, accepted: boolean | null) => void;
}) {
  const [rationaleOpen, setRationaleOpen] = useState(true);
  const { toast } = useToast();

  const handleEditAction = async (editId: string, accepted: boolean | null) => {
    try {
      await patchSuggestedEdit(editId, accepted);
      onEditChange(editId, accepted);
    } catch (err: unknown) {
      toast({
        title: "Gagal menyimpan",
        description: err instanceof Error ? err.message : "Coba lagi.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <SeverityBadge severity={flag.severity} />
            <FindingTypeBadge findingType={flag.finding_type} />
            <span className="text-xs text-muted-foreground">
              {DOMAIN_LABELS[flag.domain] ?? flag.domain}
            </span>
          </div>
          <h2 className="text-base font-semibold leading-snug">{flag.summary}</h2>
        </div>
      </div>

      {/* Rationale (expandable) */}
      <div className="rounded-md border border-border overflow-hidden">
        <button
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium bg-muted/30 hover:bg-muted/60 transition-colors text-left"
          onClick={() => setRationaleOpen((v) => !v)}
        >
          <span>Mengapa ini penting?</span>
          {rationaleOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {rationaleOpen && (
          <div className="px-4 py-3 text-sm text-foreground leading-relaxed whitespace-pre-wrap">
            {flag.rationale}
          </div>
        )}
      </div>

      {/* Negotiation ask */}
      {flag.negotiation_ask && (
        <div className="rounded-md border border-border bg-primary/5 p-4">
          <p className="text-xs font-semibold text-primary uppercase tracking-wide mb-2">
            Permintaan Negosiasi
          </p>
          <p className="text-sm leading-relaxed">{flag.negotiation_ask}</p>
        </div>
      )}

      {/* Suggested edits */}
      {flag.suggested_edits.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Usulan Perubahan Teks ({flag.suggested_edits.length})
          </p>
          {flag.suggested_edits.map((edit) => (
            <SuggestedEditCard
              key={edit.id}
              edit={edit}
              onAccept={() => handleEditAction(edit.id, true)}
              onReject={() => handleEditAction(edit.id, false)}
              onReset={() => handleEditAction(edit.id, null)}
            />
          ))}
        </div>
      )}

      {/* Absence finding note */}
      {flag.finding_type === "absent" && (
        <div className="flex items-start gap-2 rounded-md border border-blue-200 bg-blue-50 p-3">
          <Info className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
          <p className="text-xs text-blue-800 leading-relaxed">
            Klausul ini tidak ditemukan dalam kontrak. Ketidakhadiran klausul ini sendiri
            merupakan temuan penting — pertimbangkan untuk meminta penambahan klausul tersebut.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Email draft modal ─────────────────────────────────────────────────────────

function EmailDraftPanel({
  draft,
  onClose,
}: {
  draft: string;
  onClose: () => void;
}) {
  const { toast } = useToast();

  const handleCopy = () => {
    navigator.clipboard.writeText(draft).then(() => {
      toast({ title: "Email draft disalin ke clipboard" });
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-background rounded-lg shadow-xl max-w-2xl w-full max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-primary" />
            <h2 className="font-semibold text-sm">Email Draft Negosiasi</h2>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" className="gap-1.5 text-xs" onClick={handleCopy}>
              <Copy className="w-3.5 h-3.5" />Salin ke Clipboard
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose} className="text-muted-foreground">
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2.5 mb-4 leading-relaxed">
            <strong>Perhatian:</strong> Email ini adalah panduan negosiasi, bukan nasihat hukum.
            Sesuaikan dengan situasi dan konteks Anda sebelum mengirim. Tidak ada fitur kirim
            otomatis — gunakan email client Anda sendiri.
          </div>
          <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed text-foreground">
            {draft}
          </pre>
        </div>
      </div>
    </div>
  );
}

// ── Main ReviewPage ───────────────────────────────────────────────────────────

export default function ReviewPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;
  const [, setLocation] = useLocation();
  const { toast } = useToast();

  const [results, setResults] = useState<AnalysisResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedFlagId, setSelectedFlagId] = useState<string | null>(null);

  // Local mutable copy of all flags (so edit acceptance updates happen locally)
  const [flags, setFlags] = useState<(RiskFlagResponse & {
    suggested_edits: (SuggestedEditResponse & { accepted: boolean | null })[]
  })[]>([]);

  // Export state
  const [docxLoading, setDocxLoading] = useState(false);
  const [emailLoading, setEmailLoading] = useState(false);
  const [emailDraft, setEmailDraft] = useState<string | null>(null);

  // ── Load results ─────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAnalysisResults(jobId);
      setResults(data);
      setFlags(data.risk_flags as typeof flags);
      // Default-select the first critical/high flag
      const firstFlag = data.risk_flags[0];
      if (firstFlag) setSelectedFlagId(firstFlag.id);
    } catch (err: unknown) {
      toast({
        title: "Gagal memuat hasil",
        description: err instanceof Error ? err.message : "Coba lagi.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [jobId, toast]);

  useEffect(() => {
    const token = localStorage.getItem("landy_token");
    if (!token) { setLocation("/login"); return; }
    load();
  }, [load, setLocation]);

  // ── Edit change handler ──────────────────────────────────────────────────
  const handleEditChange = (editId: string, accepted: boolean | null) => {
    setFlags((prev) =>
      prev.map((flag) => ({
        ...flag,
        suggested_edits: flag.suggested_edits.map((e) =>
          e.id === editId ? { ...e, accepted } : e
        ),
      }))
    );
  };

  // ── DOCX export ──────────────────────────────────────────────────────────
  const handleDocxExport = async () => {
    if (!results) return;
    setDocxLoading(true);
    try {
      // document_id and version_id come directly from the API response — no
      // sessionStorage needed; deep-linking to /review/:jobId works correctly.
      const docxRes = await exportDocx(results.document_id, results.version_id);
      if (docxRes.warning) {
        toast({ title: "Peringatan", description: docxRes.warning, variant: "destructive" });
      }
      const a = document.createElement("a");
      a.href = docxRes.url;
      a.download = "kontrak-redlined.docx";
      a.click();
      toast({
        title: "DOCX berhasil dibuat",
        description: `${docxRes.edit_count} perubahan dilacak, ${docxRes.comment_only_count} komentar saja.`,
      });
    } catch (err: unknown) {
      toast({
        title: "Gagal membuat DOCX",
        description: err instanceof Error ? err.message : "Coba lagi.",
        variant: "destructive",
      });
    } finally {
      setDocxLoading(false);
    }
  };

  // ── Email draft export ───────────────────────────────────────────────────
  const handleEmailDraft = async () => {
    if (!results) return;
    setEmailLoading(true);
    try {
      const res = await exportEmailDraft(results.document_id, results.version_id);
      setEmailDraft(res.draft);
    } catch (err: unknown) {
      toast({
        title: "Gagal membuat email draft",
        description: err instanceof Error ? err.message : "Coba lagi.",
        variant: "destructive",
      });
    } finally {
      setEmailLoading(false);
    }
  };

  // ── Group flags by severity ──────────────────────────────────────────────
  const flagsByGroup: Record<string, typeof flags> = {};
  for (const sev of SEVERITY_ORDER) {
    const group = flags.filter(
      (f) => f.severity === sev && f.finding_type !== "absent"
    );
    if (group.length > 0) flagsByGroup[sev] = group;
  }
  const absenceFlags = flags.filter((f) => f.finding_type === "absent");

  const selectedFlag = flags.find((f) => f.id === selectedFlagId) ?? null;

  // ── Tally ─────────────────────────────────────────────────────────────────
  const totalEdits = flags.flatMap((f) => f.suggested_edits).length;
  const acceptedEdits = flags.flatMap((f) => f.suggested_edits).filter((e) => e.accepted === true).length;
  const rejectedEdits = flags.flatMap((f) => f.suggested_edits).filter((e) => e.accepted === false).length;
  const undecidedEdits = totalEdits - acceptedEdits - rejectedEdits;

  // ── Render ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!results) return null;

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <DisclaimerBanner />

      {/* Navbar */}
      <header className="border-b border-border bg-card sticky top-0 z-10">
        <div className="max-w-screen-xl mx-auto px-4 h-14 flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => setLocation("/")} className="gap-1.5 text-muted-foreground">
            <ChevronLeft className="w-4 h-4" />Beranda
          </Button>
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <Scale className="w-5 h-5 text-primary shrink-0" />
            <span className="font-serif font-semibold text-primary">LANDY</span>
            <span className="text-muted-foreground/40 mx-1">·</span>
            <span className="text-sm text-muted-foreground truncate">Tinjauan Kontrak</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {/* Edit tally */}
            {totalEdits > 0 && (
              <div className="hidden sm:flex items-center gap-2 text-xs text-muted-foreground border rounded-md px-2 py-1 bg-muted/30">
                <Check className="w-3 h-3 text-green-600" />{acceptedEdits}
                <X className="w-3 h-3 text-red-500 ml-1" />{rejectedEdits}
                <Minus className="w-3 h-3 text-muted-foreground ml-1" />{undecidedEdits}
              </div>
            )}
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs"
              onClick={handleEmailDraft}
              disabled={emailLoading || flags.length === 0}
            >
              {emailLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Mail className="w-3.5 h-3.5" />}
              Email Draft
            </Button>
            <Button
              size="sm"
              className="gap-1.5 text-xs"
              onClick={handleDocxExport}
              disabled={docxLoading}
            >
              {docxLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileDown className="w-3.5 h-3.5" />}
              Unduh DOCX
            </Button>
          </div>
        </div>
      </header>

      {/* Warning if analysis had partial errors */}
      {results.error_message && (
        <div className="bg-amber-50 border-b border-amber-200 px-4 py-2">
          <p className="text-xs text-amber-800 max-w-screen-xl mx-auto">
            <AlertTriangle className="w-3.5 h-3.5 inline mr-1" />
            Analisis selesai dengan peringatan: {results.error_message}
          </p>
        </div>
      )}

      <div className="flex flex-1 max-w-screen-xl mx-auto w-full overflow-hidden" style={{ height: "calc(100vh - 8rem)" }}>

        {/* ── Left panel: flag list ─────────────────────────────────────────── */}
        <aside className="w-72 xl:w-80 border-r border-border flex flex-col overflow-hidden shrink-0">
          <div className="px-4 py-3 border-b border-border bg-card">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-sm">Temuan Risiko</h2>
              <Button variant="ghost" size="icon" className="w-7 h-7" onClick={load} title="Muat ulang">
                <RefreshCw className="w-3.5 h-3.5" />
              </Button>
            </div>
            {results.flag_counts && (
              <div className="flex gap-2 mt-2 flex-wrap">
                {(["critical", "high", "medium", "info"] as const).map((s) => {
                  const count = results.flag_counts[s];
                  if (!count) return null;
                  const cfg = SEVERITY_CONFIG[s];
                  return (
                    <Badge key={s} className={`text-xs ${cfg.badgeClass}`}>
                      {count} {cfg.label}
                    </Badge>
                  );
                })}
              </div>
            )}
          </div>
          <div className="flex-1 overflow-y-auto">
            {/* Present/ambiguous flags by severity */}
            {SEVERITY_ORDER.map((sev) => {
              const group = flagsByGroup[sev];
              if (!group) return null;
              const cfg = SEVERITY_CONFIG[sev];
              return (
                <div key={sev}>
                  <div className={`px-4 py-2 text-xs font-semibold uppercase tracking-wide border-b ${cfg.headerClass}`}>
                    {cfg.label}
                  </div>
                  {group.map((flag) => (
                    <button
                      key={flag.id}
                      className={`w-full text-left px-4 py-3 border-b border-border transition-colors hover:bg-muted/40 ${
                        selectedFlagId === flag.id ? "bg-primary/5 border-l-2 border-l-primary" : ""
                      }`}
                      onClick={() => setSelectedFlagId(flag.id)}
                    >
                      <div className="flex items-start gap-2">
                        <span className={`w-2 h-2 rounded-full mt-1 shrink-0 ${cfg.dotClass}`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-muted-foreground truncate">
                            {DOMAIN_LABELS[flag.domain] ?? flag.domain}
                          </p>
                          <p className="text-sm leading-snug mt-0.5 line-clamp-2">
                            {flag.summary}
                          </p>
                          {flag.suggested_edits.length > 0 && (
                            <p className="text-xs text-muted-foreground mt-1">
                              {flag.suggested_edits.filter(e => e.accepted === true).length}/{flag.suggested_edits.length} diterima
                            </p>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              );
            })}

            {/* Absence findings section */}
            {absenceFlags.length > 0 && (
              <div>
                <div className="px-4 py-2 text-xs font-semibold uppercase tracking-wide border-b bg-slate-50 border-slate-200 text-slate-600">
                  Klausul Tidak Ditemukan
                </div>
                {absenceFlags.map((flag) => (
                  <button
                    key={flag.id}
                    className={`w-full text-left px-4 py-3 border-b border-border transition-colors hover:bg-muted/40 ${
                      selectedFlagId === flag.id ? "bg-primary/5 border-l-2 border-l-primary" : ""
                    }`}
                    onClick={() => setSelectedFlagId(flag.id)}
                  >
                    <div className="flex items-start gap-2">
                      <Info className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-muted-foreground truncate">
                          {DOMAIN_LABELS[flag.domain] ?? flag.domain}
                        </p>
                        <p className="text-sm leading-snug mt-0.5 line-clamp-2 text-muted-foreground">
                          {flag.summary}
                        </p>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {flags.length === 0 && (
              <div className="flex flex-col items-center justify-center h-32 text-center px-4">
                <p className="text-sm text-muted-foreground">Tidak ada temuan risiko.</p>
              </div>
            )}
          </div>
        </aside>

        {/* ── Right panel: flag detail ─────────────────────────────────────── */}
        <main className="flex-1 overflow-y-auto p-6">
          {selectedFlag ? (
            <FlagDetail
              flag={selectedFlag as Parameters<typeof FlagDetail>[0]["flag"]}
              onEditChange={handleEditChange}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground gap-2">
              <Scale className="w-10 h-10 text-primary/30" />
              <p className="text-sm">Pilih temuan risiko di panel kiri untuk melihat detailnya.</p>
            </div>
          )}
        </main>
      </div>

      {/* Email draft modal */}
      {emailDraft && (
        <EmailDraftPanel
          draft={emailDraft}
          onClose={() => setEmailDraft(null)}
        />
      )}
    </div>
  );
}
