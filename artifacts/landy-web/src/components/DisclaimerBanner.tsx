import { AlertTriangle } from "lucide-react";

export function DisclaimerBanner() {
  return (
    <div className="bg-primary/5 border-b border-primary/10 text-primary px-4 py-2.5 text-xs sm:text-sm text-center flex items-center justify-center gap-2">
      <AlertTriangle className="h-4 w-4 shrink-0 text-primary" />
      <span className="font-medium max-w-3xl leading-relaxed">
        Konten ini merupakan informasi hukum, bukan nasihat hukum, dan bukan pengganti konsultasi dengan advokat.
      </span>
    </div>
  );
}
