import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export function DateRangeFilter({
  from,
  to,
  onChange,
  idPrefix = "range",
  className,
}: {
  from?: string;
  to?: string;
  onChange: (next: { from?: string; to?: string }) => void;
  idPrefix?: string;
  className?: string;
}) {
  return (
    <div className={cn("grid grid-cols-1 gap-4 sm:grid-cols-2", className)}>
      <div className="min-w-0 space-y-2">
        <Label htmlFor={`${idPrefix}-from`} className="text-sm font-medium text-foreground">
          Dal
        </Label>
        <Input
          id={`${idPrefix}-from`}
          type="date"
          value={from ?? ""}
          className="h-11 w-full bg-background"
          onChange={(event) => onChange({ from: event.target.value || undefined, to })}
        />
      </div>
      <div className="min-w-0 space-y-2">
        <Label htmlFor={`${idPrefix}-to`} className="text-sm font-medium text-foreground">
          Al
        </Label>
        <Input
          id={`${idPrefix}-to`}
          type="date"
          value={to ?? ""}
          className="h-11 w-full bg-background"
          onChange={(event) => onChange({ from, to: event.target.value || undefined })}
        />
      </div>
    </div>
  );
}
