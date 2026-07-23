/**
 * DokumenLegalitasPanel — collapsible checklist of legal documents a creator
 * must collect from the counterparty before signing.
 *
 * Displays in the ReviewPage left sidebar below the risk-flag list.
 *
 * State persisted to localStorage, keyed by document version so different
 * contracts get independent checklists.
 *
 * Two entity types:
 *   Badan Usaha (PT/CV/dll)  — NIB, Akta Pendirian, Akta Perubahan Terakhir, NPWP Perusahaan
 *   Perorangan               — KTP, NPWP Individu
 */
import { useState, useEffect } from "react";
import { ChevronDown, ChevronUp, Info, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";

// ── Data ────────────────────────────────────────────────────────────────────

type EntityType = "badan_usaha" | "perorangan";

interface DocItem {
  id: string;
  /** Short label shown in the card */
  name: string;
  /** Tooltip — placeholder until follow-up task fills in real copy */
  description: string;
}

const BADAN_USAHA_DOCS: DocItem[] = [
  {
    id: "nib",
    name: "NIB (Nomor Induk Berusaha)",
    description:
      "Tanda daftar usaha resmi yang diterbitkan sistem OSS (Online Single Submission) " +
      "Kementerian Investasi. NIB menggantikan SIUP dan TDP lama. " +
      "Pastikan: nama perusahaan di NIB sama dengan di kontrak, dan bidang usaha yang " +
      "tercantum mencakup kegiatan yang diperjanjikan (misalnya periklanan, promosi, atau konten digital).",
  },
  {
    id: "akta_pendirian",
    name: "Akta Pendirian",
    description:
      "Akta notaris yang secara resmi mendirikan badan usaha, disahkan oleh Kementerian " +
      "Hukum dan HAM (Kemenkumham). Memuat nama perusahaan, modal dasar, dan susunan " +
      "pengurus pertama beserta kewenangannya. " +
      "Pastikan: nama perusahaan sesuai kontrak, dan cek apakah penandatangan kontrak " +
      "sudah tercantum di sini — atau di Akta Perubahan Terakhir jika ada pergantian Direksi.",
  },
  {
    id: "akta_perubahan",
    name: "Akta Perubahan Terakhir (mengenai perubahan Direksi)",
    description:
      "Akta notaris terbaru yang mencatat perubahan susunan Direksi, disahkan oleh " +
      "Kemenkumham. Harus yang paling mutakhir — periksa tanggal dan nomor akta. " +
      "Pastikan: nama penandatangan kontrak tercantum sebagai Direktur yang masih aktif " +
      "pada akta ini. Jika tidak ada, minta Surat Kuasa dari Direksi yang berwenang.",
  },
  {
    id: "npwp_perusahaan",
    name: "NPWP Perusahaan",
    description:
      "Nomor Pokok Wajib Pajak badan usaha, diterbitkan oleh Direktorat Jenderal Pajak " +
      "(DJP). Digunakan untuk semua kewajiban perpajakan perusahaan, termasuk pemotongan " +
      "PPh 21/23 atas honor kreator. " +
      "Pastikan: nama dan alamat di NPWP sesuai dengan yang ada di kontrak, dan ini " +
      "adalah NPWP badan (15 digit), bukan NPWP pribadi.",
  },
];

const PERORANGAN_DOCS: DocItem[] = [
  {
    id: "ktp",
    name: "KTP / Kartu Tanda Penduduk",
    description:
      "Kartu identitas resmi warga negara Indonesia, diterbitkan oleh Dinas Kependudukan " +
      "dan Pencatatan Sipil (Disdukcapil) setempat. Berlaku seumur hidup untuk WNI usia ≥17 " +
      "tahun (tidak ada tanggal kedaluwarsa pada KTP-el baru). " +
      "Pastikan: nama pada KTP sama persis dengan nama penandatangan di kontrak, NIK " +
      "16 digit terlihat jelas, dan foto serta chip tidak rusak.",
  },
  {
    id: "npwp_individu",
    name: "NPWP Individu",
    description:
      "Nomor Pokok Wajib Pajak perseorangan, diterbitkan oleh Direktorat Jenderal Pajak " +
      "(DJP). Diperlukan untuk pelaporan PPh 21 atas penghasilan yang diterima dari kontrak ini. " +
      "Pastikan: nama pada NPWP sesuai dengan nama penandatangan kontrak dan dengan KTP, " +
      "serta ini adalah NPWP pribadi (16 digit pada format terbaru), bukan NPWP badan usaha.",
  },
];

// ── DocCard ─────────────────────────────────────────────────────────────────

/**
 * Single document card: checkbox + name + rose (i) info icon.
 *
 * Tooltip expands WITHIN the card (below the content row) so it never
 * overlaps or obscures any adjacent Dokumen Legalitas card.
 */
function DocCard({
  doc,
  checked,
  onToggle,
}: {
  doc: DocItem;
  checked: boolean;
  onToggle: () => void;
}) {
  const [tooltipOpen, setTooltipOpen] = useState(false);

  return (
    <div
      className={`rounded-md border transition-colors ${
        checked ? "border-border bg-muted/20" : "border-border bg-background"
      }`}
    >
      {/* Main row */}
      <div className="flex items-start gap-2 p-2.5">
        {/* Custom checkbox */}
        <button
          type="button"
          onClick={onToggle}
          aria-checked={checked}
          role="checkbox"
          className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
            checked
              ? "bg-green-600 border-green-600 text-white"
              : "border-muted-foreground/40 hover:border-primary"
          }`}
        >
          {checked && (
            <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 12 12">
              <path
                d="M2 6l3 3 5-5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>

        {/* Document name */}
        <span
          className={`text-xs flex-1 leading-snug ${
            checked ? "text-muted-foreground line-through" : "text-foreground"
          }`}
        >
          {doc.name}
        </span>

        {/* Info icon — opens tooltip within card */}
        <button
          type="button"
          onMouseEnter={() => setTooltipOpen(true)}
          onMouseLeave={() => setTooltipOpen(false)}
          onFocus={() => setTooltipOpen(true)}
          onBlur={() => setTooltipOpen(false)}
          aria-label={`Info tentang ${doc.name}`}
          className="shrink-0 mt-0.5 rounded focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-rose-400"
        >
          <Info
            className={`w-3.5 h-3.5 transition-colors ${
              tooltipOpen ? "text-rose-600" : "text-rose-400"
            }`}
          />
        </button>
      </div>

      {/* Tooltip: expands within the card — never overlaps adjacent cards */}
      {tooltipOpen && (
        <div className="px-2.5 pb-2.5">
          <div className="rounded border border-dashed border-rose-200 bg-rose-50/60 px-2.5 py-2">
            <p className="text-xs text-rose-700 leading-relaxed">{doc.description}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── DokumenLegalitasPanel ────────────────────────────────────────────────────

interface Props {
  /** Parent document UUID — used as part of the localStorage key */
  documentId: string;
  /** Version UUID — used as part of the localStorage key */
  versionId: string;
}

export function DokumenLegalitasPanel({ documentId, versionId }: Props) {
  const storageKey = `landy_legalitas_${documentId}_${versionId}`;
  const storageTypeKey = `${storageKey}_type`;

  const [collapsed, setCollapsed] = useState(true);
  const [entityType, setEntityType] = useState<EntityType>("badan_usaha");
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  const docs = entityType === "badan_usaha" ? BADAN_USAHA_DOCS : PERORANGAN_DOCS;
  const uncollected = docs.filter((d) => !checked[d.id]).length;

  // ── Restore persisted state ──────────────────────────────────────────────
  useEffect(() => {
    try {
      const savedChecked = localStorage.getItem(storageKey);
      if (savedChecked) setChecked(JSON.parse(savedChecked));

      const savedType = localStorage.getItem(storageTypeKey);
      if (savedType === "badan_usaha" || savedType === "perorangan") {
        setEntityType(savedType);
      }
    } catch {
      // Corrupted localStorage — start fresh
    }
  }, [storageKey, storageTypeKey]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const toggleCheck = (id: string) => {
    setChecked((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      try {
        localStorage.setItem(storageKey, JSON.stringify(next));
      } catch {}
      return next;
    });
  };

  const handleEntityChange = (type: EntityType) => {
    setEntityType(type);
    try {
      localStorage.setItem(storageTypeKey, type);
    } catch {}
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="border-t border-border bg-card shrink-0">
      {/* Collapsible header */}
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/40 transition-colors text-left gap-2"
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="truncate">Dokumen Legalitas Pihak Lain</span>
          {uncollected > 0 && (
            <Badge className="text-[10px] px-1.5 py-0 h-4 min-w-[1rem] bg-rose-500 text-white border-rose-500 shrink-0">
              {uncollected}
            </Badge>
          )}
        </div>
        {collapsed ? (
          <ChevronDown className="w-4 h-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronUp className="w-4 h-4 shrink-0 text-muted-foreground" />
        )}
      </button>

      {!collapsed && (
        <div className="px-3 pb-4 space-y-3">
          {/* Entity type toggle */}
          <div
            className="flex rounded-md border border-border text-xs font-medium overflow-hidden"
            role="group"
            aria-label="Jenis pihak lain"
          >
            <button
              type="button"
              className={`flex-1 px-2 py-1.5 transition-colors focus-visible:outline-none focus-visible:ring-inset focus-visible:ring-1 focus-visible:ring-primary ${
                entityType === "badan_usaha"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/30 text-muted-foreground hover:bg-muted/60"
              }`}
              onClick={() => handleEntityChange("badan_usaha")}
              aria-pressed={entityType === "badan_usaha"}
            >
              Badan Usaha (PT/CV/dll)
            </button>
            <button
              type="button"
              className={`flex-1 px-2 py-1.5 border-l border-border transition-colors focus-visible:outline-none focus-visible:ring-inset focus-visible:ring-1 focus-visible:ring-primary ${
                entityType === "perorangan"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/30 text-muted-foreground hover:bg-muted/60"
              }`}
              onClick={() => handleEntityChange("perorangan")}
              aria-pressed={entityType === "perorangan"}
            >
              Perorangan
            </button>
          </div>

          {/* Checklist */}
          <div className="space-y-2">
            {docs.map((doc) => (
              <DocCard
                key={doc.id}
                doc={doc}
                checked={!!checked[doc.id]}
                onToggle={() => toggleCheck(doc.id)}
              />
            ))}
          </div>

          {/* Surat Kuasa callout — Badan Usaha only */}
          {entityType === "badan_usaha" && (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-800 leading-relaxed">
                Jika nama penandatangan tidak tercantum dalam Akta Pendirian atau Akta Perubahan
                Terakhir, minta{" "}
                <strong className="font-semibold">Surat Kuasa</strong> dari pejabat yang berwenang
                sebelum penandatanganan.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
