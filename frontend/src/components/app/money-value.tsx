import { formatCurrency } from "@/lib/format";
import { cn } from "@/lib/utils";

export function MoneyValue({
  value,
  className,
  muted,
}: {
  value?: number | null;
  className?: string;
  muted?: boolean;
}) {
  return (
    <span
      className={cn("tabular-nums", muted && "text-muted-foreground", className)}
      title={formatCurrency(value)}
    >
      {formatCurrency(value)}
    </span>
  );
}
