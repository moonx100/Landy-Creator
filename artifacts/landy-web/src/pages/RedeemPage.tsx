import { useState } from "react";
import { useLocation, Link } from "wouter";
import { redeem } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Scale, Loader2 } from "lucide-react";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { useToast } from "@/hooks/use-toast";

export default function RedeemPage() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    invite_code: "",
    email: "",
    display_name: ""
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await redeem(formData.invite_code, formData.email, formData.display_name || undefined);
      localStorage.setItem("landy_token", data.token);
      setLocation("/");
    } catch (err: any) {
      toast({
        title: "Gagal memverifikasi",
        description: err.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      <DisclaimerBanner />
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-md space-y-8">
          <div className="flex flex-col items-center text-center">
            <div className="bg-primary/10 p-3 rounded-full mb-4">
              <Scale className="w-8 h-8 text-primary" />
            </div>
            <h1 className="text-3xl font-serif font-semibold tracking-tight text-primary">LANDY Creator</h1>
            <p className="text-muted-foreground mt-2">Ulasan Kontrak & Negosiasi Profesional</p>
          </div>

          <Card className="border-border shadow-sm">
            <CardHeader>
              <CardTitle>Gunakan Kode Undangan</CardTitle>
              <CardDescription>
                Masukkan kode undangan Anda untuk membuat akun.
              </CardDescription>
            </CardHeader>
            <form onSubmit={handleSubmit}>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="invite_code">Kode Undangan</Label>
                  <Input 
                    id="invite_code" 
                    required 
                    value={formData.invite_code}
                    onChange={(e) => setFormData(p => ({ ...p, invite_code: e.target.value }))}
                    placeholder="Contoh: LNDY-BETA-123" 
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input 
                    id="email" 
                    type="email" 
                    required 
                    value={formData.email}
                    onChange={(e) => setFormData(p => ({ ...p, email: e.target.value }))}
                    placeholder="nama@domain.com" 
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="display_name">Nama Tampilan <span className="text-muted-foreground font-normal">(Opsional)</span></Label>
                  <Input 
                    id="display_name" 
                    value={formData.display_name}
                    onChange={(e) => setFormData(p => ({ ...p, display_name: e.target.value }))}
                    placeholder="Nama Anda" 
                  />
                </div>
              </CardContent>
              <CardFooter className="flex flex-col space-y-4">
                <Button type="submit" className="w-full" disabled={loading} data-testid="button-redeem-submit">
                  {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Daftar
                </Button>
                <div className="text-sm text-center text-muted-foreground">
                  Sudah punya akun?{" "}
                  <Link href="/login" className="text-primary hover:underline font-medium">
                    Masuk di sini
                  </Link>
                </div>
              </CardFooter>
            </form>
          </Card>
        </div>
      </div>
    </div>
  );
}
