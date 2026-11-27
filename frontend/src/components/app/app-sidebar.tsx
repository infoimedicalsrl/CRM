import { Link } from "@tanstack/react-router";
import {
  Cloud,
  BarChart3,
  FileSpreadsheet,
  Boxes,
  FileStack,
  LayoutDashboard,
  Wallet,
  ReceiptText,
  FileText,
  Truck,
  Settings,
  Users,
} from "lucide-react";
import type { LucideProps } from "lucide-react";
import type { ComponentType } from "react";
import { cn } from "@/lib/utils";
import { useBackendStatus } from "./backend-status";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<LucideProps>;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/orders", label: "Ordini Clienti", icon: ReceiptText },
  { to: "/sales-invoices", label: "Fatture vendita", icon: FileText },
  { to: "/purchase-invoices", label: "Fatture acquisti", icon: FileSpreadsheet },
  { to: "/ddts", label: "DDT", icon: Truck },
  { to: "/customers", label: "Clienti", icon: Users },
  { to: "/products", label: "Prodotti", icon: Boxes },
  { to: "/analytics", label: "Analisi", icon: BarChart3 },
  { to: "/customer-statements", label: "Estratto conto cliente", icon: FileSpreadsheet },
  { to: "/bank", label: "Banca", icon: Wallet },
  { to: "/imports", label: "Importazioni", icon: FileStack },
  { to: "/settings", label: "Impostazioni", icon: Settings },
];

export function SidebarNav({
  collapsed,
  onNavigate,
}: {
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <nav className="flex flex-1 flex-col gap-0.5 p-2" aria-label="Navigazione principale">
      {NAV_ITEMS.map((item) => {
        const link = (
          <Link
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            activeOptions={{ exact: item.to === "/" }}
            activeProps={{
              className: "bg-sidebar-accent text-sidebar-accent-foreground font-medium",
            }}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
              collapsed && "justify-center px-0",
            )}
          >
            <item.icon className="size-4.5 shrink-0" aria-hidden />
            {!collapsed && <span className="truncate">{item.label}</span>}
            {collapsed && <span className="sr-only">{item.label}</span>}
          </Link>
        );

        if (!collapsed) return link;
        return (
          <Tooltip key={item.to}>
            <TooltipTrigger asChild>{link}</TooltipTrigger>
            <TooltipContent side="right">{item.label}</TooltipContent>
          </Tooltip>
        );
      })}
    </nav>
  );
}

export function SidebarBrand({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2.5 px-3 py-4", collapsed && "justify-center px-0")}>
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-[#29496d] text-[#dcecff]">
        <Cloud className="size-5" aria-hidden />
      </span>
      {!collapsed && (
        <div className="min-w-0 leading-tight">
          <p className="truncate text-base font-semibold text-sidebar-foreground">Peppol</p>
          <p className="truncate text-xs text-sidebar-foreground/75">Sales Analytics</p>
        </div>
      )}
    </div>
  );
}

export function SidebarFooter({ collapsed }: { collapsed?: boolean }) {
  const { isSuccess } = useBackendStatus();
  return (
    <div
      className={cn(
        "border-t border-sidebar-border px-3 py-3 text-xs text-sidebar-foreground/70",
        collapsed && "flex justify-center px-0",
      )}
    >
      {collapsed ? (
        <span
          className={cn("size-2 rounded-full", isSuccess ? "bg-success" : "bg-destructive")}
          aria-label={isSuccess ? "Sistema attivo" : "Backend non raggiungibile"}
        />
      ) : (
        <div className="flex items-start gap-2">
          <span
            aria-hidden
            className={cn(
              "mt-1 size-2 shrink-0 rounded-full",
              isSuccess ? "bg-success" : "bg-destructive",
            )}
          />
          <div className="min-w-0">
            <p className="truncate font-medium text-sidebar-foreground">Peppol Sales Analytics</p>
            <p className="truncate">Cloud</p>
          </div>
        </div>
      )}
    </div>
  );
}

export function AppSidebar({ collapsed }: { collapsed: boolean }) {
  return (
    <aside
      className={cn(
        "hidden shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 lg:flex",
        collapsed ? "w-[4.25rem]" : "w-64",
      )}
    >
      <SidebarBrand collapsed={collapsed} />
      <SidebarNav collapsed={collapsed} />
      <SidebarFooter collapsed={collapsed} />
    </aside>
  );
}
