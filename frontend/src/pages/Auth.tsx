import { useState } from "react";
import { Ship } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";

type AuthMode = "signin" | "signup";

export default function Auth() {
  const [mode, setMode] = useState<AuthMode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      if (mode === "signin") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      } else {
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        setSuccess("Check your email for a confirmation link.");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-[#f5f5f7]">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-[14px] bg-apple-blue shadow-lg">
            <Ship className="h-6 w-6 text-white" strokeWidth={1.5} />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold tracking-tight text-apple-text">dockie</h1>
            <p className="mt-1 text-sm text-apple-secondary">Shipment tracking copilot</p>
          </div>
        </div>

        <div className="apple-card rounded-2xl p-6 shadow-sm">
          <div className="mb-5 flex rounded-[10px] bg-apple-hover p-1">
            <button
              onClick={() => { setMode("signin"); setError(null); setSuccess(null); }}
              className={`flex-1 rounded-[8px] py-1.5 text-sm font-medium transition-all ${
                mode === "signin" ? "bg-white text-apple-text shadow-sm" : "text-apple-secondary"
              }`}
            >
              Sign in
            </button>
            <button
              onClick={() => { setMode("signup"); setError(null); setSuccess(null); }}
              className={`flex-1 rounded-[8px] py-1.5 text-sm font-medium transition-all ${
                mode === "signup" ? "bg-white text-apple-text shadow-sm" : "text-apple-secondary"
              }`}
            >
              Sign up
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-apple-secondary">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-[10px] border border-apple-divider bg-white px-3 py-2 text-sm text-apple-text placeholder:text-apple-secondary/50 focus:border-apple-blue focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-apple-secondary">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                minLength={6}
                className="w-full rounded-[10px] border border-apple-divider bg-white px-3 py-2 text-sm text-apple-text placeholder:text-apple-secondary/50 focus:border-apple-blue focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
              />
            </div>

            {error && (
              <p className="rounded-[8px] bg-red-50 px-3 py-2 text-xs text-red-600">{error}</p>
            )}
            {success && (
              <p className="rounded-[8px] bg-green-50 px-3 py-2 text-xs text-green-700">{success}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="mt-1 w-full rounded-[10px] bg-apple-blue py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
