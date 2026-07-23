import { useState, useRef, useCallback } from "react";
import { createDocument, uploadVersion } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { FileText, Upload, X, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const ACCEPTED_TYPES = [
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
];
const ACCEPTED_EXT = [".docx", ".pdf", ".jpg", ".jpeg", ".png", ".webp"];
const MAX_MB = 20;

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess: (jobId: string) => void;
}

type UploadStep = "form" | "uploading" | "done";

export function UploadModal({ open, onClose, onSuccess }: Props) {
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState("");
  const [counterparty, setCounterparty] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [step, setStep] = useState<UploadStep>("form");
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setTitle("");
    setCounterparty("");
    setSelectedFile(null);
    setUploadProgress(0);
    setStep("form");
    setError(null);
  };

  const handleClose = () => {
    if (step === "uploading") return; // block close during upload
    reset();
    onClose();
  };

  const validateFile = (file: File): string | null => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    const isValidType = ACCEPTED_TYPES.includes(file.type) || ACCEPTED_EXT.includes(ext);
    if (!isValidType) {
      return `Format tidak didukung. Gunakan: ${ACCEPTED_EXT.join(", ")}`;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      return `Ukuran file melebihi batas ${MAX_MB} MB.`;
    }
    return null;
  };

  const handleFileSelect = (file: File) => {
    const err = validateFile(file);
    if (err) {
      setError(err);
      return;
    }
    setSelectedFile(file);
    setError(null);
    // Auto-fill title from filename if blank
    if (!title) {
      setTitle(file.name.replace(/\.[^.]+$/, ""));
    }
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  }, [title]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || !title.trim()) return;
    setError(null);
    setStep("uploading");
    setUploadProgress(0);

    try {
      // Step 1: create document record
      const doc = await createDocument(title.trim(), counterparty.trim() || undefined);

      // Step 2: upload file + enqueue job
      const result = await uploadVersion(doc.id, selectedFile, (pct) => {
        setUploadProgress(pct);
      });

      setStep("done");
      toast({
        title: "Dokumen berhasil diunggah",
        description: "Analisis sedang diproses. Anda akan melihat hasilnya sebentar lagi.",
      });

      setTimeout(() => {
        reset();
        onClose();
        onSuccess(result.job_id);
      }, 1500);
    } catch (err: unknown) {
      setStep("form");
      setError(err instanceof Error ? err.message : "Terjadi kesalahan saat mengunggah.");
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-serif">Unggah Kontrak</DialogTitle>
          <DialogDescription>
            Unggah kontrak dalam format DOCX, PDF, atau gambar (maks {MAX_MB} MB).
            Informasi pribadi yang tidak diperlukan sebaiknya dihapus sebelum diunggah.
          </DialogDescription>
        </DialogHeader>

        {step === "done" ? (
          <div className="flex flex-col items-center gap-4 py-8">
            <CheckCircle2 className="w-12 h-12 text-green-600" />
            <p className="text-center font-medium">Dokumen berhasil diunggah!</p>
            <p className="text-sm text-muted-foreground text-center">Analisis dimulai…</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Title */}
            <div className="space-y-2">
              <Label htmlFor="upload-title">Nama Kontrak <span className="text-destructive">*</span></Label>
              <Input
                id="upload-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Contoh: Perjanjian Brand Ambassador PT XYZ"
                required
                disabled={step === "uploading"}
              />
            </div>

            {/* Counterparty */}
            <div className="space-y-2">
              <Label htmlFor="upload-counterparty">Pihak Lain (opsional)</Label>
              <Input
                id="upload-counterparty"
                value={counterparty}
                onChange={(e) => setCounterparty(e.target.value)}
                placeholder="Contoh: PT Brand XYZ"
                disabled={step === "uploading"}
              />
            </div>

            {/* File drop zone */}
            <div className="space-y-2">
              <Label>File Kontrak <span className="text-destructive">*</span></Label>
              {selectedFile ? (
                <div className="flex items-center gap-3 p-3 rounded-md border border-border bg-muted/30">
                  <FileText className="w-8 h-8 text-primary shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{selectedFile.name}</p>
                    <p className="text-xs text-muted-foreground">{formatBytes(selectedFile.size)}</p>
                  </div>
                  {step !== "uploading" && (
                    <button
                      type="button"
                      onClick={() => setSelectedFile(null)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ) : (
                <div
                  className={`
                    border-2 border-dashed rounded-md p-8 text-center cursor-pointer
                    transition-colors
                    ${dragOver
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50 hover:bg-muted/20"
                    }
                  `}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={onDrop}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="w-8 h-8 mx-auto mb-3 text-muted-foreground" />
                  <p className="text-sm font-medium">Seret & lepas file di sini</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    atau klik untuk memilih file
                  </p>
                  <p className="text-xs text-muted-foreground mt-2">
                    {ACCEPTED_EXT.join(", ")} · maks {MAX_MB} MB
                  </p>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept={ACCEPTED_EXT.join(",")}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); }}
                disabled={step === "uploading"}
              />
            </div>

            {/* Upload progress */}
            {step === "uploading" && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Mengunggah…</span>
                  <span className="font-medium">{uploadProgress}%</span>
                </div>
                <Progress value={uploadProgress} className="h-2" />
              </div>
            )}

            {/* Error */}
            {error && (
              <Alert variant="destructive">
                <AlertTriangle className="w-4 h-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <DialogFooter className="gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={handleClose}
                disabled={step === "uploading"}
              >
                Batal
              </Button>
              <Button
                type="submit"
                disabled={!selectedFile || !title.trim() || step === "uploading"}
              >
                {step === "uploading" ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Mengunggah…
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4 mr-2" />
                    Unggah
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
