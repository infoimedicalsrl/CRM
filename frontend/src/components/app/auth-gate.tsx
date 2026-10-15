import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { Loader2, LockKeyhole } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase, supabaseConfigured } from "@/lib/supabase";

export function useSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setLoading(false); });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, []);
  return { session, loading };
}

function LoginScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    const { error: err } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (err) setError("Credenziali non valide.");
    setBusy(false);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="rounded-md bg-primary/10 p-2 text-primary"><LockKeyhole className="size-5" aria-hidden /></div>
          <div>
            <h1 className="text-lg font-semibold">Peppol Sales Analytics</h1>
            <p className="text-sm text-muted-foreground">Accedi per continuare</p>
          </div>
        </div>
        {!supabaseConfigured && (
          <p role="alert" className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">
            Configurazione mancante: imposta VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY.
          </p>
        )}
        <div className="space-y-2">
          <Label htmlFor="login-email">Email</Label>
          <Input id="login-email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="login-password">Password</Label>
          <Input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy || !supabaseConfigured}>
          {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
          {busy ? "Accesso…" : "Accedi"}
        </Button>
      </form>
    </div>
  );
}

/** Nessun contenuto dell'app viene renderizzato (né richiesto al backend) senza una sessione valida. */
export function AuthGate({ children }: { children: ReactNode }) {
  const { session, loading } = useSession();
  if (loading) return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Caricamento…</div>;
  if (!session) return <LoginScreen />;
  return <>{children}</>;
}
