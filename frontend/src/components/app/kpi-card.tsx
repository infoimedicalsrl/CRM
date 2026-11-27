import type { ComponentType, ReactNode } from "react";
import type { LucideProps } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function KpiCard({
  label,
  value,
  icon: Icon,
  hint,
  tone = "default",
  onClick,
  className,
}: {
  label: string;
  value: ReactNode;
  icon?: ComponentType<LucideProps>;
  hint?: ReactNode;
  tone?: "default" | "muted" | "accent";
  onClick?: () => void;
  className?: string;
}) {
  const interactive = Boolean(onClick);
  const content = (
    <CardContent className="flex items-center justify-between gap-4 py-4">
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p
          className={cn(
            "mt-2 whitespace-nowrap font-semibold leading-none tabular-nums tracking-tight text-foreground",
            tone === "muted" ? "text-xl" : "text-[clamp(1.5rem,2.1vw,2.25rem)]",
          )}
        >
          {value}
        </p>
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </div>
      {Icon && (
        <span
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-lg",
            tone === "accent" ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
          )}
          aria-hidden
        >
          <Icon className="size-5" />
        </span>
      )}
    </CardContent>
  );

  if (interactive) {
    return (
      <Card
        className={cn(
          "cursor-pointer transition-colors hover:border-primary/40 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          className,
        )}
        tabIndex={0}
        role="button"
        onClick={onClick}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onClick?.();
          }
        }}
      >
        {content}
      </Card>
    );
  }

  return <Card className={className}>{content}</Card>;
}
