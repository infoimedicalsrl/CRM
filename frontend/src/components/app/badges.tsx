import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function ProductCodeBadge({ code, className }: { code: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border border-border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium tracking-tight text-foreground",
        className,
      )}
    >
      {code}
    </span>
  );
}

export function ZeroValueBadge() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className="border-info/40 bg-info/10 text-info-foreground">
          Valore zero
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        Riga con quantità maggiore di zero e valore economico pari a €0,00.
      </TooltipContent>
    </Tooltip>
  );
}

const IMPORT_STATUS: Record<string, { label: string; className: string }> = {
  SUCCESS: { label: "Importato", className: "border-success/40 bg-success/10 text-success" },
  PROCESSING: { label: "In elaborazione", className: "border-warning/40 bg-warning/10 text-warning" },
  ERROR: { label: "Errore", className: "border-destructive/40 bg-destructive/10 text-destructive" },
};

export function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return <span className="text-muted-foreground">—</span>;
  const known = IMPORT_STATUS[status.toUpperCase()];
  return (
    <Badge variant="outline" className={cn("font-medium", known?.className)}>
      {known?.label ?? status}
    </Badge>
  );
}
