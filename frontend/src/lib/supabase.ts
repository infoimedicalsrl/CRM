import { createClient } from "@supabase/supabase-js";

/** Tiene solo https://xxxx.supabase.co: toglie spazi, "/" finali e percorsi come /rest/v1. */
function cleanOrigin(value: string | undefined): string | undefined {
  const raw = (value ?? "").trim().replace(/^["']|["']$/g, "");
  if (!raw) return undefined;
  try {
    return new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`).origin;
  } catch {
    return undefined;
  }
}

const url = cleanOrigin(import.meta.env["VITE_SUPABASE_URL"] as string | undefined);
const anonKey = ((import.meta.env["VITE_SUPABASE_ANON_KEY"] as string | undefined) ?? "").trim().replace(/^["']|["']$/g, "") || undefined;

export const supabaseConfigured = Boolean(url && anonKey);

// Solo la chiave pubblica (anon/publishable) è presente nel browser. Le tabelle non sono
// leggibili con questa chiave (RLS attiva): i dati passano solo dalle API protette.
export const supabase = createClient(url ?? "https://missing.invalid", anonKey ?? "missing", {
  auth: { persistSession: true, autoRefreshToken: true },
});
