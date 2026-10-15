import { useState, type ReactNode } from "react";
import { useRouter } from "@tanstack/react-router";
import { LogOut, Menu, PanelLeftClose, PanelLeftOpen, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { AppSidebar, SidebarBrand, SidebarFooter, SidebarNav } from "./app-sidebar";
import { BackendStatus } from "./backend-status";
import { GlobalSearch } from "./global-search";
import { supabase } from "@/lib/supabase";

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const router = useRouter();

  return (
    <div className="flex min-h-screen bg-background">
      <AppSidebar collapsed={collapsed} />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-card/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-card/80">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Apri menu">
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 bg-sidebar p-0">
              <SheetTitle className="sr-only">Navigazione</SheetTitle>
              <div className="flex h-full flex-col">
                <SidebarBrand />
                <SidebarNav onNavigate={() => setMobileOpen(false)} />
                <SidebarFooter />
              </div>
            </SheetContent>
          </Sheet>

          <Button
            variant="ghost"
            size="icon"
            className="hidden lg:inline-flex"
            aria-label={collapsed ? "Espandi menu" : "Comprimi menu"}
            onClick={() => setCollapsed((v) => !v)}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-5" />
            ) : (
              <PanelLeftClose className="size-5" />
            )}
          </Button>

          <div className="ml-auto flex items-center gap-2">
            <GlobalSearch />
            <BackendStatus />
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.invalidate()}
              aria-label="Aggiorna dati"
            >
              <RefreshCw className="size-4" aria-hidden />
              Aggiorna
            </Button>
            <Button variant="outline" size="sm" onClick={() => void supabase.auth.signOut()} aria-label="Esci">
              <LogOut className="size-4" aria-hidden />
              Esci
            </Button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1600px] flex-1 space-y-6 p-4 lg:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
