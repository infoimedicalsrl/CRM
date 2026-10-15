import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/services/dashboard";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function useBackendStatus() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 15_000,
    retry: false,
    staleTime: 5_000,
  });
}

export function BackendStatus({ compact = false }: { compact?: boolean }) {
  const { isSuccess, isLoading } = useBackendStatus();
  const online = isSuccess;

  const label = isLoading
    ? "Verifica sistema…"
    : online
      ? "Sistema attivo"
      : "Backend non raggiungibile";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs font-medium",
            online ? "text-foreground" : "text-destructive",
          )}
          role="status"
          aria-live="polite"
        >
          <span
            aria-hidden
            className={cn(
              "size-2 rounded-full",
              isLoading
                ? "bg-muted-foreground"
                : online
                  ? "bg-success animate-pulse"
                  : "bg-destructive",
            )}
          />
          {!compact && <span className="whitespace-nowrap">{label}</span>}
        </div>
      </TooltipTrigger>
      <TooltipContent>
        {online
          ? "Server raggiungibile"
          : "Verifica che Peppol Sales Analytics Backend sia avviato sul Mac."}
      </TooltipContent>
    </Tooltip>
  );
}
