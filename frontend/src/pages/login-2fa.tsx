import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Shield, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { login2FA } from "@/lib/api/auth";
import { toast } from "sonner";

export default function Login2FAPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const username = searchParams.get("username") || "";
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim() || code.length < 6) return;

    setLoading(true);
    try {
      await login2FA(username, code.trim());
      navigate("/dashboard");
    } catch {
      toast.error("Invalid verification code");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/20 to-blue-500/20 mb-4">
            <Shield className="h-7 w-7 text-violet-600 dark:text-violet-400" />
          </div>
          <h1 className="text-xl font-bold">Two-Factor Authentication</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Enter the 6-digit code from your authenticator app
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="000000"
              maxLength={6}
              autoFocus
              autoComplete="one-time-code"
              inputMode="numeric"
              pattern="[0-9]*"
              className="w-full text-center text-2xl font-mono tracking-[0.5em] rounded-xl border border-input bg-transparent px-4 py-3 ring-offset-background placeholder:text-muted-foreground/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <Button type="submit" className="w-full" disabled={loading || code.length < 6}>
            {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            Verify
          </Button>
        </form>

        <p className="text-xs text-center text-muted-foreground">Or use one of your backup codes</p>
      </div>
    </div>
  );
}
