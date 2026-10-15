import { createFileRoute } from "@tanstack/react-router";
import { Database, HardDrive, LockKeyhole, LogOut, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { useSession } from "@/components/app/auth-gate";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { supabase } from "@/lib/supabase";

export const Route = createFileRoute("/settings")({ component: SettingsPage });

function Info({ icon: Icon, title, value }: { icon: typeof Database; title: string; value: string }) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3 pt-6">
        <div className="rounded-md bg-muted p-2"><Icon className="size-5" aria-hidden /></div>
        <div>
          <div className="text-sm font-medium">{title}</div>
          <div className="mt-1 text-sm text-muted-foreground">{value}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function SettingsPage() {
  const { session } = useSession();
  return (
    <div className="space-y-6">
      <PageHeader title="Impostazioni" subtitle="Account, archiviazione e sicurezza." />
      <div className="grid gap-4 md:grid-cols-3">
        <Info icon={Database} title="Database" value="Supabase PostgreSQL. Gestito e con backup a cura di Supabase." />
        <Info icon={HardDrive} title="Documenti originali" value="Supabase Storage, bucket privato: XML, PDF, CSV ed Excel importati." />
        <Info icon={ShieldCheck} title="Accesso" value="Login obbligatorio. Le tabelle non sono leggibili dal browser (RLS attiva)." />
      </div>
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2 text-base"><LockKeyhole className="size-4" aria-hidden />Account</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs text-muted-foreground">Connesso come</div>
            <div className="text-sm font-medium">{session?.user.email ?? "—"}</div>
          </div>
          <Button variant="outline" onClick={() => void supabase.auth.signOut()}><LogOut className="size-4" aria-hidden />Esci</Button>
        </CardContent>
      </Card>
    </div>
  );
}
