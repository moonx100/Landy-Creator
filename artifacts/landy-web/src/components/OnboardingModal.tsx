import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ShieldAlert, FileText } from "lucide-react";

interface OnboardingModalProps {
  userDisplayName: string | null;
  onDismiss: () => void;
}

export function OnboardingModal({ userDisplayName, onDismiss }: OnboardingModalProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const hasSeen = localStorage.getItem("landy_onboarding_shown");
    const shouldShow = !hasSeen || userDisplayName === null;
    
    if (shouldShow) {
      setOpen(true);
    }
  }, [userDisplayName]);

  const handleDismiss = () => {
    localStorage.setItem("landy_onboarding_shown", "true");
    setOpen(false);
    onDismiss();
  };

  return (
    <Dialog open={open} onOpenChange={(val) => { if(!val) handleDismiss(); }}>
      <DialogContent className="max-w-md" onPointerDownOutside={(e) => e.preventDefault()} onEscapeKeyDown={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="text-xl">Selamat datang di LANDY Creator</DialogTitle>
          <DialogDescription>
            Sebelum Anda mulai menganalisis kontrak, mohon perhatikan hal-hal berikut.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4 my-4">
          <div className="flex gap-3 p-3 rounded-md bg-muted/50 border">
            <ShieldAlert className="h-5 w-5 text-primary shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-semibold text-foreground mb-1">Privasi & Keamanan Data</p>
              <p className="text-muted-foreground leading-relaxed">
                Teks kontrak yang Anda unggah akan diproses oleh layanan AI kami. Hal ini melibatkan transfer data secara aman ke server penyedia LLM.
              </p>
            </div>
          </div>
          
          <div className="flex gap-3 p-3 rounded-md bg-muted/50 border">
            <FileText className="h-5 w-5 text-primary shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-semibold text-foreground mb-1">Hapus Data Pribadi</p>
              <p className="text-muted-foreground leading-relaxed">
                Mohon hapus informasi sensitif seperti Nomor Induk Kependudukan (NIK), nomor rekening bank, dan alamat rumah sebelum mengunggah kontrak Anda.
              </p>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button onClick={handleDismiss} className="w-full sm:w-auto" data-testid="button-onboarding-dismiss">
            Saya Mengerti
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
