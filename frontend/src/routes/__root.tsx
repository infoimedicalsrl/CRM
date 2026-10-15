import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Outlet, Link, createRootRouteWithContext } from "@tanstack/react-router";
import { AppShell } from "@/components/app/app-shell";
import { AuthGate } from "@/components/app/auth-gate";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";

function NotFoundComponent() {
  return <div className="flex min-h-screen items-center justify-center bg-background px-4"><div className="max-w-md text-center"><h1 className="text-7xl font-bold">404</h1><h2 className="mt-4 text-xl font-semibold">Pagina non trovata</h2><p className="mt-2 text-sm text-muted-foreground">La pagina richiesta non esiste o è stata spostata.</p><Link to="/" className="mt-6 inline-flex rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">Torna alla Dashboard</Link></div></div>;
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
});

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  return <QueryClientProvider client={queryClient}><TooltipProvider delayDuration={200}><AuthGate><AppShell><Outlet /></AppShell></AuthGate><Toaster position="top-right" /></TooltipProvider></QueryClientProvider>;
}
