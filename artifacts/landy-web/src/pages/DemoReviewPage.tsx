/**
 * DemoReviewPage — a fully interactive preview of the review screen,
 * using hardcoded mock data for a "SAMPLE Sale Purchase" contract.
 * Route: /demo
 * No authentication required.
 */
import { useState } from "react";
import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Scale, ChevronLeft, Info, Check, X, Minus,
  FileDown, Mail, Copy, ChevronDown, ChevronUp,
  MessageSquare, GitBranch, AlertTriangle,
} from "lucide-react";

// ── Domain labels ─────────────────────────────────────────────────────────────

const DOMAIN_LABELS: Record<string, string> = {
  payment_terms: "Pembayaran & Pajak",
  ip_ownership: "Kepemilikan IP",
  dispute_forum: "Forum Penyelesaian Sengketa",
  exclusivity: "Eksklusivitas",
  governing_language: "Bahasa Hukum",
  term_termination: "Jangka Waktu & Pemutusan",
  liability_indemnity: "Kewajiban & Ganti Rugi",
};

// ── Severity config ───────────────────────────────────────────────────────────

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

// ── Mock data ─────────────────────────────────────────────────────────────────

interface MockEdit {
  id: string;
  original_text: string;
  revised_text: string;
  comment: string;
  accepted: boolean | null;
}

interface MockFlag {
  id: string;
  severity: Severity;
  domain: string;
  finding_type: "present_risky" | "absent" | "ambiguous";
  summary: string;
  rationale: string;
  negotiation_ask: string | null;
  suggested_edits: MockEdit[];
}

const MOCK_FLAGS: MockFlag[] = [
  {
    id: "f1",
    severity: "critical",
    domain: "payment_terms",
    finding_type: "present_risky",
    summary: "Jadwal pembayaran tidak memiliki tanggal jatuh tempo yang pasti",
    rationale:
      "Pasal 4.2 menyatakan pembayaran dilakukan \"dalam waktu yang wajar setelah penyerahan barang\". Frasa ini tidak mengikat secara hukum karena tidak mendefinisikan batas waktu konkret. Dalam praktik, pembeli dapat menunda pembayaran tanpa risiko wanprestasi selama mereka dapat berargumen bahwa waktu yang berlalu masih \"wajar\". Ini menempatkan penjual pada posisi yang sangat lemah — terutama jika barang sudah diserahkan dan pembayaran tertunda berbulan-bulan.",
    negotiation_ask:
      "Minta klausul pembayaran diubah agar menetapkan tanggal pasti, misalnya: \"Pembayaran lunas wajib dilakukan dalam 14 (empat belas) hari kalender setelah tanggal penyerahan barang, dibuktikan dengan berita acara serah terima yang ditandatangani kedua pihak.\" Sertakan denda keterlambatan 2% per bulan atas saldo yang belum dibayar.",
    suggested_edits: [
      {
        id: "e1",
        original_text:
          "Pembayaran akan dilakukan dalam waktu yang wajar setelah penyerahan barang kepada Pembeli.",
        revised_text:
          "Pembayaran lunas wajib dilakukan dalam 14 (empat belas) hari kalender setelah tanggal penyerahan barang, dibuktikan dengan berita acara serah terima yang ditandatangani kedua pihak. Keterlambatan pembayaran dikenakan denda sebesar 2% (dua persen) per bulan dari saldo yang belum dibayarkan.",
        comment:
          "Menambahkan batas waktu 14 hari dan denda keterlambatan untuk melindungi penjual.",
        accepted: null,
      },
    ],
  },
  {
    id: "f2",
    severity: "high",
    domain: "ip_ownership",
    finding_type: "present_risky",
    summary: "Hak kepemilikan IP dialihkan secara permanen tanpa batasan penggunaan",
    rationale:
      "Pasal 7.1 mengalihkan \"seluruh hak kekayaan intelektual yang melekat pada objek perjanjian, termasuk namun tidak terbatas pada merek, desain, dan konten digital, kepada Pembeli secara permanen dan tanpa batas\". Jika objek yang dijual mencakup materi kreatif (foto produk, deskripsi, konten promosi), klausul ini berarti Anda tidak dapat lagi menggunakan karya tersebut untuk portofolio, referensi, atau keperluan lain — bahkan untuk menunjukkan bahwa Anda pernah membuat karya itu. Pengalihan \"tanpa batas\" juga mencakup modifikasi dan distribusi ulang tanpa persetujuan Anda.",
    negotiation_ask:
      "Batasi pengalihan IP hanya pada penggunaan yang terkait langsung dengan objek transaksi. Pertahankan hak moral dan hak untuk mencantumkan karya dalam portofolio. Alternatif: ubah menjadi lisensi eksklusif dengan jangka waktu tertentu, bukan pengalihan permanen.",
    suggested_edits: [
      {
        id: "e2",
        original_text:
          "Penjual dengan ini mengalihkan seluruh hak kekayaan intelektual yang melekat pada objek perjanjian kepada Pembeli secara permanen dan tanpa batas.",
        revised_text:
          "Penjual memberikan kepada Pembeli lisensi eksklusif, tidak dapat dipindahtangankan, dan berlaku selama 5 (lima) tahun untuk menggunakan kekayaan intelektual yang melekat pada objek perjanjian semata-mata dalam kaitannya dengan pengoperasian bisnis Pembeli. Penjual tetap berhak mencantumkan karya terkait dalam portofolio profesional mereka.",
        comment:
          "Mengubah dari pengalihan permanen menjadi lisensi 5 tahun dan mempertahankan hak portofolio.",
        accepted: null,
      },
    ],
  },
  {
    id: "f3",
    severity: "high",
    domain: "dispute_forum",
    finding_type: "absent",
    summary: "Tidak ada klausul penyelesaian sengketa — forum hukum tidak ditentukan",
    rationale:
      "Kontrak ini tidak memuat ketentuan mengenai bagaimana sengketa akan diselesaikan jika terjadi perselisihan antara pihak. Tanpa klausul ini, salah satu pihak dapat mengajukan gugatan ke pengadilan mana saja yang dianggap menguntungkan mereka — termasuk pengadilan di kota atau provinsi yang jauh, yang dapat sangat merugikan secara biaya dan waktu. Di Indonesia, ketidakhadiran klausul ADR (Alternative Dispute Resolution) sering berarti proses litigasi penuh yang bisa berlangsung bertahun-tahun.",
    negotiation_ask:
      "Tambahkan klausul yang menetapkan: (1) mediasi wajib 30 hari sebelum litigasi; (2) jika mediasi gagal, forum sengketa di Pengadilan Negeri Jakarta Selatan atau BANI (Badan Arbitrase Nasional Indonesia); (3) hukum yang berlaku adalah hukum Republik Indonesia.",
    suggested_edits: [],
  },
  {
    id: "f4",
    severity: "medium",
    domain: "exclusivity",
    finding_type: "ambiguous",
    summary: "Klausul non-compete bagi penjual tidak jelas batas lingkup dan durasinya",
    rationale:
      "Pasal 9 melarang penjual untuk \"terlibat dalam kegiatan serupa\" selama \"periode yang wajar\" pasca-transaksi. Frasa \"kegiatan serupa\" tidak didefinisikan — apakah ini berarti penjualan produk dalam kategori yang sama, penjualan kepada pelanggan yang sama, atau bahkan bekerja di industri yang sama? \"Periode yang wajar\" sama ambigunya dengan klausul pembayaran. Pembatasan non-compete yang terlalu luas dapat melanggar prinsip kebebasan bekerja yang dilindungi hukum Indonesia.",
    negotiation_ask:
      "Minta definisi yang spesifik: lingkup geografis, kategori produk yang dibatasi, dan durasi yang pasti (maksimum 1-2 tahun untuk non-compete yang dapat ditegakkan di Indonesia). Pastikan klausul ini hanya melarang bersaing secara langsung, bukan mencari nafkah secara umum.",
    suggested_edits: [],
  },
  {
    id: "f5",
    severity: "info",
    domain: "governing_language",
    finding_type: "present_risky",
    summary: "Kontrak dibuat dalam Bahasa Inggris — berisiko tidak dapat ditegakkan penuh",
    rationale:
      "Undang-Undang No. 24 Tahun 2009 tentang Bendera, Bahasa, dan Lambang Negara mewajibkan perjanjian yang melibatkan pihak Indonesia untuk dibuat dalam Bahasa Indonesia. Mahkamah Agung Indonesia telah membatalkan kontrak yang hanya tersedia dalam Bahasa Inggris (putusan MA No. 601 K/Pdt/2015). Jika terjadi sengketa, pihak lawan dapat berargumen bahwa kontrak ini batal demi hukum karena tidak ada versi Bahasa Indonesia.",
    negotiation_ask:
      "Minta agar kontrak dibuat dalam versi bilingual (Bahasa Indonesia dan Bahasa Inggris). Jika terdapat perbedaan penafsiran, versi Bahasa Indonesia yang berlaku. Ini melindungi Anda sekaligus memenuhi kewajiban hukum.",
    suggested_edits: [],
  },
  {
    id: "f6",
    severity: "medium",
    domain: "liability_indemnity",
    finding_type: "absent",
    summary: "Tidak ada klausul pembatasan tanggung jawab (limitation of liability)",
    rationale:
      "Kontrak tidak membatasi besarnya ganti rugi yang dapat dituntut oleh salah satu pihak. Tanpa pembatasan ini, jika ada kerugian turunan (consequential damages) yang diklaim — misalnya, pembeli mengklaim kerugian bisnis yang jauh lebih besar dari nilai transaksi — Anda dapat dituntut hingga jumlah yang tidak proporsional. Klausul pembatasan tanggung jawab yang umum membatasi ganti rugi maksimum sebesar nilai transaksi.",
    negotiation_ask:
      "Tambahkan klausul yang membatasi tanggung jawab masing-masing pihak sebesar nilai total transaksi, dan mengecualikan tanggung jawab atas kerugian tidak langsung, kerugian keuntungan, atau kerugian konsekuensial.",
    suggested_edits: [],
  },
];

// Counterparty comment bubbles (simulating comments extracted from DOCX)
const MOCK_COMMENTS = [
  {
    id: "c1",
    author: "Legal Team — Pembeli",
    comment_date: "2026-07-20",
    anchor_text:
      "Pembayaran akan dilakukan dalam waktu yang wajar setelah penyerahan barang kepada Pembeli.",
    body: "Klausul ini perlu tetap fleksibel karena proses verifikasi kualitas barang kami memerlukan waktu internal. Kami tidak dapat berkomitmen pada tanggal tetap sebelum audit selesai.",
    ordinal: 1,
  },
  {
    id: "c2",
    author: "Legal Team — Pembeli",
    comment_date: "2026-07-20",
    anchor_text:
      "Penjual dengan ini mengalihkan seluruh hak kekayaan intelektual yang melekat pada objek perjanjian kepada Pembeli secara permanen dan tanpa batas.",
    body: "Ini adalah syarat mutlak dari pihak kami. Penggunaan IP oleh penjual untuk tujuan apapun pasca-transaksi tidak dapat kami setujui.",
    ordinal: 2,
  },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: Severity }) {
  const cfg = SEVERITY_CONFIG[severity];
  return (
    <Badge className={`text-xs font-semibold px-2 py-0.5 border ${cfg.badgeClass}`}>
      {cfg.label}
    </Badge>
  );
}

function FindingTypeBadge({ findingType }: { findingType: string }) {
  if (findingType === "absent")
    return <Badge variant="outline" className="text-xs text-muted-foreground">Tidak ditemukan</Badge>;
  if (findingType === "ambiguous")
    return <Badge variant="outline" className="text-xs text-amber-600 border-amber-400">Ambigu</Badge>;
  return null;
}

function SuggestedEditCard({
  edit,
  onAccept,
  onReject,
  onReset,
}: {
  edit: MockEdit;
  onAccept: () => void;
  onReject: () => void;
  onReset: () => void;
}) {
  return (
    <div className="rounded-md border border-border bg-muted/20 p-3 space-y-3">
      <div className="space-y-2 text-sm font-mono">
        <div className="bg-red-50 border border-red-200 rounded p-2">
          <span className="text-xs text-red-600 font-sans font-medium block mb-1">Teks Asli</span>
          <span className="text-red-800 line-through whitespace-pre-wrap break-words">{edit.original_text}</span>
        </div>
        <div className="bg-green-50 border border-green-200 rounded p-2">
          <span className="text-xs text-green-600 font-sans font-medium block mb-1">Usulan</span>
          <span className="text-green-800 whitespace-pre-wrap break-words">{edit.revised_text}</span>
        </div>
      </div>
      {edit.comment && <p className="text-xs text-muted-foreground italic">{edit.comment}</p>}
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
          <Button size="sm" variant="ghost" className="gap-1 text-xs h-7 text-muted-foreground" onClick={onReset}>
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

function FlagDetail({
  flag,
  edits,
  onEditChange,
}: {
  flag: MockFlag;
  edits: MockEdit[];
  onEditChange: (editId: string, accepted: boolean | null) => void;
}) {
  const [rationaleOpen, setRationaleOpen] = useState(true);
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <SeverityBadge severity={flag.severity} />
            <FindingTypeBadge findingType={flag.finding_type} />
            <span className="text-xs text-muted-foreground">{DOMAIN_LABELS[flag.domain] ?? flag.domain}</span> // silent-failure-ok: cosmetic label, falls back to raw key
          </div>
          <h2 className="text-base font-semibold leading-snug">{flag.summary}</h2>
        </div>
      </div>

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

      {flag.negotiation_ask && (
        <div className="rounded-md border border-border bg-primary/5 p-4">
          <p className="text-xs font-semibold text-primary uppercase tracking-wide mb-2">Permintaan Negosiasi</p>
          <p className="text-sm leading-relaxed">{flag.negotiation_ask}</p>
        </div>
      )}

      {edits.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Usulan Perubahan Teks ({edits.length})
          </p>
          {edits.map((edit) => (
            <SuggestedEditCard
              key={edit.id}
              edit={edit}
              onAccept={() => onEditChange(edit.id, true)}
              onReject={() => onEditChange(edit.id, false)}
              onReset={() => onEditChange(edit.id, null)}
            />
          ))}
        </div>
      )}

      {flag.finding_type === "absent" && (
        <div className="flex items-start gap-2 rounded-md border border-blue-200 bg-blue-50 p-3">
          <Info className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
          <p className="text-xs text-blue-800 leading-relaxed">
            Klausul ini tidak ditemukan dalam kontrak. Ketidakhadiran klausul ini sendiri merupakan
            temuan penting — pertimbangkan untuk meminta penambahan klausul tersebut.
          </p>
        </div>
      )}
    </div>
  );
}

// ── DemoReviewPage ────────────────────────────────────────────────────────────

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "info"];

export default function DemoReviewPage() {
  const [, setLocation] = useLocation();
  const [selectedFlagId, setSelectedFlagId] = useState<string>("f1");

  // Local mutable edits state
  const [editState, setEditState] = useState<Record<string, boolean | null>>({
    e1: null,
    e2: null,
  });

  const handleEditChange = (editId: string, accepted: boolean | null) => {
    setEditState((prev) => ({ ...prev, [editId]: accepted }));
  };

  // Merge edit state into flags
  const flags = MOCK_FLAGS.map((f) => ({
    ...f,
    suggested_edits: f.suggested_edits.map((e) => ({
      ...e,
      accepted: editId => editId === e.id ? (editState[e.id] ?? null) : null, // silent-failure-ok: undecided edit state, not a classification
    })),
  }));

  const enrichedFlags = MOCK_FLAGS.map((f) => ({
    ...f,
    suggested_edits: f.suggested_edits.map((e) => ({
      ...e,
      accepted: editState[e.id] ?? null, // silent-failure-ok: undecided edit state, not a classification
    })),
  }));

  const presentFlags = enrichedFlags.filter((f) => f.finding_type !== "absent");
  const absentFlags = enrichedFlags.filter((f) => f.finding_type === "absent");
  const selectedFlag = enrichedFlags.find((f) => f.id === selectedFlagId) ?? null;

  const flagsByGroup: Partial<Record<Severity, typeof enrichedFlags>> = {};
  for (const f of presentFlags) {
    if (!flagsByGroup[f.severity]) flagsByGroup[f.severity] = [];
    flagsByGroup[f.severity]!.push(f);
  }

  const acceptedEdits = Object.values(editState).filter((v) => v === true).length;
  const rejectedEdits = Object.values(editState).filter((v) => v === false).length;
  const undecidedEdits = Object.values(editState).filter((v) => v === null).length;

  return (
    <div className="flex flex-col h-screen bg-background overflow-hidden">

      {/* Disclaimer banner */}
      <div className="bg-muted/60 border-b border-border px-4 py-2 flex items-center gap-2">
        <AlertTriangle className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        <p className="text-xs text-muted-foreground">
          Konten ini merupakan informasi hukum, bukan nasihat hukum, dan bukan pengganti konsultasi dengan advokat.
        </p>
        <Badge variant="outline" className="ml-auto text-xs shrink-0 bg-amber-50 border-amber-300 text-amber-700">
          DEMO — Data Contoh
        </Badge>
      </div>

      {/* Header */}
      <header className="border-b border-border bg-card px-4 py-3 flex items-center gap-3 shrink-0">
        <button
          onClick={() => setLocation("/")}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          Kembali
        </button>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Scale className="w-5 h-5 text-primary shrink-0" />
          <span className="font-serif font-semibold text-primary">LANDY</span>
          <span className="text-muted-foreground/40 mx-1">·</span>
          <span className="text-sm text-muted-foreground truncate">SAMPLE Sale Purchase</span>
          <span className="text-muted-foreground/40 mx-1">·</span>
          <span className="text-xs text-muted-foreground">DUMMY2</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Edit tally */}
          <div className="hidden sm:flex items-center gap-2 text-xs text-muted-foreground border rounded-md px-2 py-1 bg-muted/30">
            <Check className="w-3 h-3 text-green-600" />{acceptedEdits}
            <X className="w-3 h-3 text-red-500 ml-1" />{rejectedEdits}
            <Minus className="w-3 h-3 text-muted-foreground ml-1" />{undecidedEdits}
          </div>
          <Button size="sm" variant="outline" className="gap-1.5 text-xs" disabled>
            <Mail className="w-3.5 h-3.5" />Email Draft
          </Button>
          <Button size="sm" className="gap-1.5 text-xs" disabled>
            <FileDown className="w-3.5 h-3.5" />Unduh DOCX
          </Button>
        </div>
      </header>

      {/* Tracked-changes notice (demo: shown as example) */}
      <div className="bg-violet-50 border-b border-violet-200 px-4 py-2">
        <p className="text-xs text-violet-800 max-w-screen-xl mx-auto flex items-center gap-1.5">
          <GitBranch className="w-3.5 h-3.5 shrink-0" />
          <span>
            <strong>Dokumen mengandung Track Changes.</strong>{" "}
            Perubahan yang dilacak digunakan sebagai sumber perbandingan versi — LANDY membaca
            revisi asli dari dokumen, bukan teks yang sudah diterima.
          </span>
        </p>
      </div>

      <div className="flex flex-1 max-w-screen-xl mx-auto w-full overflow-hidden" style={{ height: "calc(100vh - 9rem)" }}>

        {/* ── Left panel: flag list ────────────────────────────────────────── */}
        <aside className="w-72 xl:w-80 border-r border-border flex flex-col overflow-hidden shrink-0">
          <div className="px-4 py-3 border-b border-border bg-card">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-sm">Temuan Risiko</h2>
            </div>
            <div className="flex gap-2 mt-2 flex-wrap">
              <Badge className="text-xs bg-red-600 text-white border-red-600">1 Kritis</Badge>
              <Badge className="text-xs bg-orange-500 text-white border-orange-500">2 Tinggi</Badge>
              <Badge className="text-xs bg-yellow-500 text-white border-yellow-500">2 Sedang</Badge>
              <Badge className="text-xs bg-blue-500 text-white border-blue-500">1 Info</Badge>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
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
                            {DOMAIN_LABELS[flag.domain] ?? flag.domain /* silent-failure-ok: cosmetic label, falls back to raw key */}
                          </p>
                          <p className="text-sm leading-snug mt-0.5 line-clamp-2">{flag.summary}</p>
                          {flag.suggested_edits.length > 0 && (
                            <p className="text-xs text-muted-foreground mt-1">
                              {flag.suggested_edits.filter((e) => e.accepted === true).length}/{flag.suggested_edits.length} diterima
                            </p>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              );
            })}

            {absentFlags.length > 0 && (
              <div>
                <div className="px-4 py-2 text-xs font-semibold uppercase tracking-wide border-b bg-slate-50 border-slate-200 text-slate-600">
                  Klausul Tidak Ditemukan
                </div>
                {absentFlags.map((flag) => (
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
                          {DOMAIN_LABELS[flag.domain] ?? flag.domain /* silent-failure-ok: cosmetic label, falls back to raw key */}
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
          </div>

          {/* Counterparty docs placeholder */}
          <div className="border-t border-border px-4 py-3 bg-muted/20 shrink-0">
            <p className="text-xs text-muted-foreground font-medium">Dokumen Legalitas Pihak Lain</p>
            <p className="text-xs text-muted-foreground mt-0.5">— Tidak ada dokumen diunggah</p>
          </div>
        </aside>

        {/* ── Right panel: flag detail + comments ─────────────────────────── */}
        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {selectedFlag ? (
            <FlagDetail
              flag={selectedFlag}
              edits={selectedFlag.suggested_edits}
              onEditChange={handleEditChange}
            />
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground gap-2">
              <Scale className="w-10 h-10 text-primary/30" />
              <p className="text-sm">Pilih temuan risiko di panel kiri untuk melihat detailnya.</p>
            </div>
          )}

          {/* Catatan dari Pihak Lain */}
          <section aria-labelledby="comments-heading">
            <div className="flex items-center gap-2 mb-3">
              <MessageSquare className="w-4 h-4 text-muted-foreground" />
              <h2 id="comments-heading" className="text-sm font-semibold">
                Catatan dari Pihak Lain
              </h2>
              <span className="ml-auto text-xs text-muted-foreground">
                {MOCK_COMMENTS.length} komentar
              </span>
            </div>
            <div className="space-y-3">
              {MOCK_COMMENTS.map((c) => (
                <div key={c.id} className="rounded-md border border-border bg-card p-4 space-y-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-violet-100 text-violet-800 border border-violet-200">
                      <MessageSquare className="w-2.5 h-2.5" />
                      {c.author}
                    </span>
                    <span className="text-xs text-muted-foreground">{c.comment_date}</span>
                  </div>
                  <blockquote className="border-l-2 border-violet-300 pl-3 text-xs text-muted-foreground italic leading-relaxed">
                    {c.anchor_text}
                  </blockquote>
                  <p className="text-sm leading-relaxed">{c.body}</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
              <Info className="w-3 h-3 inline mr-1" />
              Komentar-komentar ini diekstrak dari bubble komentar dalam file DOCX yang diunggah.
              Komentar sudah dipertimbangkan dalam analisis risiko di atas.
            </p>
          </section>
        </main>
      </div>
    </div>
  );
}
