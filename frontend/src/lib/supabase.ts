import { createClient } from "@supabase/supabase-js";

const url = import.meta.env["VITE_SUPABASE_URL"] as string | undefined;
const anonKey = import.meta.env["VITE_SUPABASE_ANON_KEY"] as string | undefined;

export const supabaseConfigured = Boolean(url && anonKey);

// Solo la chiave pubblica (anon/publishable) è presente nel browser. Le tabelle non sono
// leggibili con questa chiave (RLS attiva): i dati passano solo dalle API protette.
export const supabase = createClient(url ?? "https://missing.invalid", anonKey ?? "missing", {
  auth: { persistSession: true, autoRefreshToken: true },
});
