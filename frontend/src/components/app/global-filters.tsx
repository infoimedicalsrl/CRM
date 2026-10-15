import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RotateCcw, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { DateRangeFilter } from "./date-range-filter";
import { ComboboxFilter } from "./combobox-filter";
import { getCustomers } from "@/services/customers";
import { getProducts } from "@/services/products";
import type { GlobalFilterState } from "@/types";

export function GlobalFilters({
  value,
  onApply,
  className,
  bare = false,
  onApplied,
}: {
  value: GlobalFilterState;
  onApply: (filters: GlobalFilterState) => void;
  className?: string;
  bare?: boolean;
  onApplied?: () => void;
}) {
  const [draft, setDraft] = useState<GlobalFilterState>(value);

  useEffect(() => setDraft(value), [value]);

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => getCustomers(),
    retry: false,
    staleTime: 60_000,
  });
  const products = useQuery({
    queryKey: ["products"],
    queryFn: () => getProducts(),
    retry: false,
    staleTime: 60_000,
  });

  const body = (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <DateRangeFilter
          from={draft.from}
          to={draft.to}
          onChange={(range) => setDraft((prev) => ({ ...prev, ...range }))}
          className="lg:col-span-2"
        />

        <ComboboxFilter
          label="Cliente"
          placeholder="Tutti i clienti"
          searchPlaceholder="Cerca cliente…"
          value={draft.customerId}
          onChange={(customerId) => setDraft((prev) => ({ ...prev, customerId }))}
          options={(customers.data ?? []).map((customer) => ({
            value: String(customer.id),
            label: customer.name,
            hint: customer.vat_number ?? undefined,
          }))}
        />

        <ComboboxFilter
          label="Prodotto"
          placeholder="Tutti i prodotti"
          searchPlaceholder="Codice o descrizione…"
          value={draft.productCode}
          onChange={(productCode) => setDraft((prev) => ({ ...prev, productCode }))}
          options={(products.data ?? []).map((product) => ({
            value: product.supplier_product_code,
            label: product.description ?? product.supplier_product_code,
            hint: product.supplier_product_code,
          }))}
        />
      </div>

      <div className="flex flex-col-reverse gap-3 border-t pt-5 sm:flex-row sm:items-center sm:justify-between">
        <Button
          variant="ghost"
          className="justify-center sm:justify-start"
          onClick={() => {
            setDraft({});
            onApply({});
            onApplied?.();
          }}
        >
          <RotateCcw className="size-4" aria-hidden />
          Reset
        </Button>
        <Button
          className="min-w-28"
          onClick={() => {
            onApply(draft);
            onApplied?.();
          }}
        >
          Applica filtri
        </Button>
      </div>
    </div>
  );

  if (bare) return <div className={className}>{body}</div>;

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardContent className="p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-muted-foreground">
          <SlidersHorizontal className="size-4" aria-hidden />
          Filtri
        </div>
        {body}
      </CardContent>
    </Card>
  );
}
