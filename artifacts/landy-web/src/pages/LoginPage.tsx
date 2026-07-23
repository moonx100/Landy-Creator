import { useState } from "react";
import { useLocation, Link } from "wouter";
import { login, verifyOTP } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Scale, Loader2, Mail, KeyRound } from "lucide-react";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { useToast } from "@/hooks/use-toast";

type Step = "email" | "otp";

export default function LoginPage() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [debugOtp, setDebugOtp] = useState<string | undefined>();
  const [otp, setOtp] = useState("");

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await login(email);
      setChallengeId(data.challenge_id);
      setDebugOtp(data.debug_otp);
      setStep("otp");
      toast({
        title: "Kode OTP dikirim",
        description: data.debug_otp
          ? `Mode beta: kode Anda adalah ${data.debug_otp}`
          : "Periksa email Anda untuk kode OTP 6 digit.",
      });
    } catch (err: unknown) {
      toast({
        title: "Gagal meminta OTP",
        description: err instanceof Error ? err.message : "Terjadi kesalahan.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleOtpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await verifyOTP(challengeId, otp);
      localStorage.setItem("landy_token", data.token);
      setLocation("/");
    } catch (err: unknown) {
      toast({
        title: "Verifikasi gagal",
        description: err instanceof Error ? err.message : "Kode OTP tidak valid.",
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
            <h1 className="text-3xl font-serif font-semibold tracking-tight text-primary">
              LANDY Creator
            </h1>
            <p className="text-muted-foreground mt-2">Masuk ke Akun Anda</p>
          </div>

          {step === "email" && (
            <Card className="border-border shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Mail className="w-5 h-5" /> Masuk
                </CardTitle>
                <CardDescription>
                  Masukkan email Anda. Kami akan mengirimkan kode OTP 6 digit.
                </CardDescription>
              </CardHeader>
              <form onSubmit={handleEmailSubmit}>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="nama@domain.com"
                      autoComplete="email"
                    />
                  </div>
                </CardContent>
                <CardFooter className="flex flex-col space-y-4">
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={loading}
                    data-testid="button-login-submit"
                  >
                    {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Kirim Kode OTP
                  </Button>
                  <div className="text-sm text-center text-muted-foreground">
                    Belum punya akun?{" "}
                    <Link href="/redeem" className="text-primary hover:underline font-medium">
                      Gunakan kode undangan
                    </Link>
                  </div>
                </CardFooter>
              </form>
            </Card>
          )}

          {step === "otp" && (
            <Card className="border-border shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <KeyRound className="w-5 h-5" /> Masukkan Kode OTP
                </CardTitle>
                <CardDescription>
                  Masukkan kode 6 digit yang dikirim ke{" "}
                  <span className="font-medium text-foreground">{email}</span>.
                  {debugOtp && (
                    <span className="block mt-2 text-amber-600 font-mono text-lg tracking-widest">
                      Beta: {debugOtp}
                    </span>
                  )}
                </CardDescription>
              </CardHeader>
              <form onSubmit={handleOtpSubmit}>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="otp">Kode OTP</Label>
                    <Input
                      id="otp"
                      type="text"
                      inputMode="numeric"
                      pattern="\d{6}"
                      maxLength={6}
                      required
                      value={otp}
                      onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                      placeholder="123456"
                      autoComplete="one-time-code"
                      className="text-center text-2xl tracking-widest font-mono"
                    />
                  </div>
                </CardContent>
                <CardFooter className="flex flex-col space-y-4">
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={loading || otp.length !== 6}
                    data-testid="button-otp-submit"
                  >
                    {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Verifikasi
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    className="w-full text-sm"
                    onClick={() => { setStep("email"); setOtp(""); }}
                  >
                    Kembali
                  </Button>
                </CardFooter>
              </form>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
