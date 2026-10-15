import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { ExportMenu } from "@/components/app/export-menu";
import { GlobalFilters } from "@/components/app/global-filters";
import { DataTable, type DataTableColumn } from "@/components/app/data-table";
import { ProductCodeBadge } from "@/components/app/badges";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { getProductCustomerRows, getZeroValueLines } from "@/services/analytics";
import { formatCurrency, formatDate, formatNumber } from "@/lib/format";
import type { GlobalFilterState, ProductCustomerRow, ZeroValueLine } from "@/types";

export const Route = createFileRoute("/analytics")({ component: AnalyticsPage });

function AnalyticsPage() {
  const [filters, setFilters] = useState<GlobalFilterState>({});
  const [metric, setMetric] = useState<"quantity" | "revenue">("quantity");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const rows = useQuery({
    queryKey: ["analytics", "product-customer", filters],
    queryFn: () => getProductCustomerRows(filters),
    retry: false,
  });
  const zero = useQuery({
    queryKey: ["analytics", "zero-value", filters],
    queryFn: () => getZeroValueLines(filters),
    retry: false,
  });

  const cols: DataTableColumn<ProductCustomerRow>[] = [
    { key: "customer", header: "Cliente", cell: (r) => r.customer, sortValue: (r) => r.customer },
    { key: "code", header: "Codice", cell: (r) => <ProductCodeBadge code={r.supplier_product_code} />, sortValue: (r) => r.supplier_product_code },
    { key: "desc", header: "Descrizione", className: "min-w-[320px] whitespace-normal", cell: (r) => r.description ?? "—" },
    { key: "unit", header: "UM", cell: (r) => r.unit_code ?? "—" },
    { key: "value", header: metric === "quantity" ? "Quantità" : "Fatturato", align: "right", cell: (r) => metric === "quantity" ? formatNumber(r.quantity) : formatCurrency(r.net), sortValue: (r) => metric === "quantity" ? r.quantity : r.net },
  ];

  const zcols: DataTableColumn<ZeroValueLine>[] = [
    { key: "code", header: "Codice", cell: (r) => <ProductCodeBadge code={r.supplier_product_code} /> },
    { key: "desc", header: "Descrizione", className: "min-w-[320px] whitespace-normal", cell: (r) => r.description ?? "—" },
    { key: "customer", header: "Cliente", cell: (r) => r.customer_name ?? "—" },
    { key: "order", header: "Ordine", cell: (r) => r.order_number },
    { key: "date", header: "Data", cell: (r) => formatDate(r.order_date) },
    { key: "qty", header: "Quantità", align: "right", cell: (r) => `${formatNumber(r.quantity)} ${r.unit ?? ""}` },
  ];

  const activeCount = Object.values(filters).filter(Boolean).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analisi"
        subtitle="Analizza vendite, clienti e prodotti nel tempo."
        actions={<div className="flex gap-2"><ExportMenu path="/api/exports/analytics" params={{date_from:filters.from,date_to:filters.to,customer_id:filters.customerId,supplier_product_code:filters.productCode}}/><Button variant="outline" onClick={() => setFiltersOpen(true)}>
            <SlidersHorizontal className="size-4" aria-hidden />
            Filtri
            {activeCount > 0 && <span className="ml-1 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">{activeCount}</span>}
          </Button></div>}
      />

      <Dialog open={filtersOpen} onOpenChange={setFiltersOpen}>
        <DialogContent className="w-[calc(100%_-_2rem)] max-w-3xl p-0 sm:rounded-2xl">
          <div className="border-b px-6 py-5 sm:px-7">
            <DialogHeader className="space-y-1.5">
              <DialogTitle className="text-xl">Filtra analisi</DialogTitle>
              <DialogDescription>Restringi i risultati per periodo, cliente o prodotto.</DialogDescription>
            </DialogHeader>
          </div>
          <div className="px-6 py-6 sm:px-7">
            <GlobalFilters value={filters} onApply={setFilters} bare onApplied={() => setFiltersOpen(false)} />
          </div>
        </DialogContent>
      </Dialog>

      <Card>
        <CardHeader className="gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Prodotti × Clienti</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">Confronta quantità e fatturato per combinazione cliente/prodotto.</p>
          </div>
          <div className="inline-flex rounded-lg bg-muted p-1">
            <button type="button" onClick={() => setMetric("quantity")} className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${metric === "quantity" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>Quantità</button>
            <button type="button" onClick={() => setMetric("revenue")} className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${metric === "revenue" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>Fatturato</button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <DataTable columns={cols} rows={rows.data} isLoading={rows.isLoading} isError={rows.isError} onRetry={() => rows.refetch()} getRowId={(r, i) => `${r.customer_id}-${r.product_id}-${r.unit_code ?? ""}-${i}`} emptyTitle="Nessun dato per i filtri selezionati" />
        </CardContent>
      </Card>

      <Card id="valore-zero">
        <CardHeader><CardTitle>Forniture a valore zero</CardTitle></CardHeader>
        <CardContent className="p-0">
          <DataTable columns={zcols} rows={zero.data} isLoading={zero.isLoading} isError={zero.isError} onRetry={() => zero.refetch()} getRowId={(r) => String(r.id)} emptyTitle="Nessuna fornitura a valore zero" />
        </CardContent>
      </Card>
    </div>
  );
}
