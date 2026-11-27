import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, FileUp, Pencil, RotateCcw, Trash2, Upload, X, ReceiptText, FileSpreadsheet } from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { ExportMenu } from "@/components/app/export-menu";
import { SearchInput } from "@/components/app/search-input";
import { DateRangeFilter } from "@/components/app/date-range-filter";
import { ComboboxFilter } from "@/components/app/combobox-filter";
import { DataTable, type DataTableColumn } from "@/components/app/data-table";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { deleteOrder, getOrders } from "@/services/orders";
import { apiPostForm, postFilesInBatches } from "@/services/api";
import { getCustomers } from "@/services/customers";
import { formatCurrency, formatDate } from "@/lib/format";
import { humanizeError } from "@/services/api";
import type { Order } from "@/types";

export const Route = createFileRoute("/orders/")({ component: OrdersPage });

function OrdersPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [customerId, setCustomerId] = useState<string | undefined>();
  const [range, setRange] = useState<{ from?: string; to?: string }>({});
  const [deleteTarget, setDeleteTarget] = useState<Order | null>(null);
  const [importOpen, setImportOpen] = useState(false); const [singleFile, setSingleFile] = useState<File | null>(null); const [bulkFiles, setBulkFiles] = useState<File[]>([]); const [importBusy, setImportBusy] = useState(false); const [importMessage, setImportMessage] = useState(""); const [importError, setImportError] = useState("");

  const customers = useQuery({ queryKey: ["customers"], queryFn: () => getCustomers(), staleTime: 60_000 });
  const query = useQuery({
    queryKey: ["orders", search, customerId, range.from, range.to],
    queryFn: () => getOrders({ search, customerId, from: range.from, to: range.to }),
    retry: false,
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteOrder(id),
    onSuccess: async () => {
      setDeleteTarget(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["products"] }),
        queryClient.invalidateQueries({ queryKey: ["customers"] }),
        queryClient.invalidateQueries({ queryKey: ["analytics"] }),
      ]);
    },
  });

  async function importSingle(){if(!singleFile)return;setImportBusy(true);setImportError("");setImportMessage("");try{const fd=new FormData();fd.append("file",singleFile);const r=await apiPostForm<{order_number:string}>("/api/imports/upload",fd);setImportMessage(`Ordine ${r.order_number} importato correttamente.`);setSingleFile(null);await Promise.all([queryClient.invalidateQueries({queryKey:["orders"]}),queryClient.invalidateQueries({queryKey:["dashboard"]}),queryClient.invalidateQueries({queryKey:["customers"]}),queryClient.invalidateQueries({queryKey:["products"]}),queryClient.invalidateQueries({queryKey:["analytics"]})])}catch(e){setImportError(humanizeError(e))}finally{setImportBusy(false)}}
  async function handleOrderFiles(files: File[]){if(!files.length)return;const input=document.getElementById("orders-card-file") as HTMLInputElement|null;setImportBusy(true);setImportError("");setImportMessage("");try{if(files.length===1&&files[0].name.toLowerCase().endsWith(".xml")){const fd=new FormData();fd.append("file",files[0]);const r=await apiPostForm<{order_number:string}>("/api/imports/upload",fd);setImportMessage(`Ordine ${r.order_number} importato correttamente.`)}else{const fd=new FormData();files.forEach(file=>fd.append("files",file));const r=await apiPostForm<{total:number;success:number;duplicates:number;errors:number;message:string}>("/api/imports/upload-multiple",fd);setImportMessage(r.message)}await Promise.all([queryClient.invalidateQueries({queryKey:["orders"]}),queryClient.invalidateQueries({queryKey:["dashboard"]}),queryClient.invalidateQueries({queryKey:["customers"]}),queryClient.invalidateQueries({queryKey:["products"]}),queryClient.invalidateQueries({queryKey:["analytics"]})])}catch(e){setImportError(humanizeError(e))}finally{setImportBusy(false);if(input)input.value=""}}

  async function importBulk(){if(!bulkFiles.length)return;setImportBusy(true);setImportError("");setImportMessage("");try{const r=await postFilesInBatches("/api/imports/upload-multiple",bulkFiles);setImportMessage(r.message);setBulkFiles([]);await Promise.all([queryClient.invalidateQueries({queryKey:["orders"]}),queryClient.invalidateQueries({queryKey:["dashboard"]}),queryClient.invalidateQueries({queryKey:["customers"]}),queryClient.invalidateQueries({queryKey:["products"]}),queryClient.invalidateQueries({queryKey:["analytics"]})])}catch(e){setImportError(humanizeError(e))}finally{setImportBusy(false)}}

  function getStatusConfig(status?: string) {
    switch (status) {
      case "EVASO":
        return { label: "Evaso", color: "bg-emerald-500", text: "text-emerald-500" };
      case "PARZIALE":
        return { label: "Parziale", color: "bg-amber-500", text: "text-amber-500" };
      case "DA_EVADERE":
      default:
        return { label: "Da evadere", color: "bg-red-500", text: "text-red-500" };
    }
  }

  const columns: DataTableColumn<Order>[] = [
    { key: "number", header: "Numero ordine", cell: (o) => <span className="font-medium">{o.order_number}</span>, sortValue: (o) => o.order_number },
    { key: "date", header: "Data", cell: (o) => formatDate(o.order_date), sortValue: (o) => o.order_date ?? "" },
    { key: "customer", header: "Cliente", cell: (o) => <span className="font-medium">{o.customer_name ?? "—"}</span>, sortValue: (o) => o.customer_name ?? "" },
    { key: "net", header: "Imponibile", align: "right", cell: (o) => formatCurrency(o.net_amount), sortValue: (o) => o.net_amount ?? 0 },
    { key: "vat", header: "IVA", align: "right", cell: (o) => formatCurrency(o.vat_amount), sortValue: (o) => o.vat_amount ?? 0 },
    { key: "total", header: "Totale", align: "right", cell: (o) => <span className="font-semibold">{formatCurrency(o.total_amount)}</span>, sortValue: (o) => o.total_amount ?? 0 },
    {
      key: "status",
      header: "Stato",
      cell: (o) => {
        const cfg = getStatusConfig(o.status);
        return (
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${cfg.color}`} aria-hidden="true" />
            <span className="text-sm font-medium">{cfg.label}</span>
          </div>
        );
      },
      sortValue: (o) => {
        // Sort: EVASO (0) > PARZIALE (1) > DA_EVADERE (2)
        const order = { EVASO: 0, PARZIALE: 1, DA_EVADERE: 2 };
        return order[o.status as keyof typeof order] ?? 2;
      },
    },
    {
      key: "actions",
      header: "Azioni",
      align: "right",
      cell: (o) => (
        <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          <Button
            size="icon"
            variant="ghost"
            title="Modifica ordine"
            onClick={() => navigate({ to: "/orders/$id", params: { id: String(o.id) } })}
          >
            <Pencil className="size-4" />
          </Button>
          <Button size="icon" variant="ghost" className="text-destructive" title="Elimina ordine" onClick={() => setDeleteTarget(o)}>
            <Trash2 className="size-4" />
          </Button>
        </div>
      ),
    },
  ];

  const hasFilters = Boolean(search || customerId || range.from || range.to);

  return (
    <div className="space-y-6">
      <PageHeader title="Ordini Clienti" subtitle="Consulta, filtra e gestisci gli ordini Peppol importati nel sistema." actions={<ExportMenu path="/api/exports/orders" params={{search,customer_id:customerId,date_from:range.from,date_to:range.to}}/>} />
      <input id="orders-card-file" type="file" accept=".xml,.zip,application/zip,application/xml,text/xml" multiple className="hidden" disabled={importBusy} onChange={e=>void handleOrderFiles(Array.from(e.target.files??[]))}/>
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <article className="rounded-xl border bg-card p-5"><div className="flex items-center gap-2 text-sm font-medium text-muted-foreground"><ReceiptText className="size-4"/>Totale ordini</div><div className="mt-3 text-3xl font-semibold tracking-tight">{formatCurrency((query.data??[]).reduce((sum,o)=>sum+(o.total_amount??0),0))}</div><p className="mt-2 text-sm text-muted-foreground">Somma degli ordini secondo i filtri attivi</p></article>
        <article className="rounded-xl border bg-card p-5"><div className="flex items-center gap-2 text-sm font-medium text-muted-foreground"><FileSpreadsheet className="size-4"/>Ordini visualizzati</div><div className="mt-3 text-3xl font-semibold tracking-tight">{(query.data??[]).length}</div><p className="mt-2 text-sm text-muted-foreground">Numero di ordini mostrati</p></article>
        <article className="rounded-xl border bg-card p-5"><div className="text-sm font-medium text-muted-foreground">Importa un Ordine</div><button type="button" disabled={importBusy} onClick={()=>document.getElementById("orders-card-file")?.click()} className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"><FileUp className="size-4"/>{importBusy?"Importazione…":"Scegli file"}</button><p className="mt-2 text-xs text-muted-foreground">Seleziona un singolo XML, più file XML oppure un archivio ZIP con più ordini.</p></article>
      </section>
      {importMessage&&<p role="status" className="rounded-md bg-muted p-3 text-sm">{importMessage}</p>}{importError&&<p role="alert" className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">{importError}</p>}

      {importOpen&&<div className="fixed inset-0 z-50 bg-black/40" onClick={()=>setImportOpen(false)}><aside role="dialog" aria-modal="true" aria-label="Importazione ordini" onClick={e=>e.stopPropagation()} className="absolute right-0 top-0 h-full w-full max-w-xl overflow-y-auto border-l bg-background p-5 shadow-xl"><div className="mb-5 flex items-center justify-between"><div><h2 className="text-lg font-semibold">Importa ordini</h2><p className="text-sm text-muted-foreground">Importazione singola XML oppure massiva XML/ZIP, con le funzioni già presenti nella sezione Importazioni.</p></div><button aria-label="Chiudi" onClick={()=>setImportOpen(false)} className="rounded-md p-2 hover:bg-muted"><X className="size-5"/></button></div>{importError&&<p role="alert" className="mb-3 rounded-md border border-destructive/40 p-3 text-sm text-destructive">{importError}</p>}{importMessage&&<p role="status" className="mb-3 rounded-md bg-muted p-3 text-sm">{importMessage}</p>}<div className="space-y-3"><section className="rounded-xl border bg-card p-4 space-y-3"><h3 className="flex items-center gap-2 font-semibold"><FileUp className="size-4"/>Singolo XML</h3><input type="file" accept=".xml,text/xml,application/xml" onChange={e=>setSingleFile(e.target.files?.[0]??null)} className="block w-full text-sm"/><Button disabled={!singleFile||importBusy} onClick={()=>void importSingle()}>{importBusy?"Importazione…":"Importa ordine"}</Button></section><section className="rounded-xl border bg-card p-4 space-y-3"><h3 className="flex items-center gap-2 font-semibold"><Archive className="size-4"/>Importazione massiva XML / ZIP</h3><p className="text-sm text-muted-foreground">Seleziona più XML oppure un archivio ZIP contenente gli ordini.</p><input type="file" multiple accept=".xml,.zip,application/zip,application/xml,text/xml" onChange={e=>setBulkFiles(Array.from(e.target.files??[]))} className="block w-full text-sm"/><p className="text-xs text-muted-foreground">{bulkFiles.length?`${bulkFiles.length} file selezionati`:"Nessun file selezionato"}</p><Button disabled={!bulkFiles.length||importBusy} onClick={()=>void importBulk()}>{importBusy?"Importazione in corso…":"Importa file selezionati"}</Button></section></div></aside></div>}
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 py-4">
          <div className="min-w-[260px] flex-1">
            <SearchInput value={search} onChange={setSearch} placeholder="Cerca numero ordine, cliente o P.IVA…" />
          </div>
          <ComboboxFilter
            label="Cliente"
            placeholder="Tutti i clienti"
            searchPlaceholder="Cerca cliente…"
            value={customerId}
            onChange={setCustomerId}
            options={(customers.data ?? []).map((customer) => ({
              value: String(customer.id),
              label: customer.name,
              hint: customer.vat_number ?? undefined,
            }))}
          />
          <DateRangeFilter from={range.from} to={range.to} onChange={setRange} idPrefix="orders" />
          {hasFilters && (
            <Button
              variant="ghost"
              onClick={() => {
                setSearch("");
                setCustomerId(undefined);
                setRange({});
              }}
            >
              <RotateCcw className="size-4" /> Reset
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <DataTable
          columns={columns}
          rows={query.data}
          isLoading={query.isLoading}
          isError={query.isError}
          onRetry={() => query.refetch()}
          onRowClick={(o) => navigate({ to: "/orders/$id", params: { id: String(o.id) } })}
          emptyTitle="Nessun ordine trovato"
          getRowId={(o) => String(o.id)}
          defaultSortKey="date"
        />
      </Card>

      <AlertDialog open={Boolean(deleteTarget)} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminare questo ordine?</AlertDialogTitle>
            <AlertDialogDescription>
              L&apos;ordine <strong>{deleteTarget?.order_number}</strong> verrà eliminato dal database e non comparirà più nelle analisi. L&apos;XML originale non viene modificato.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {remove.isError && <p className="text-sm text-destructive">{humanizeError(remove.error)}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel>Annulla</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={() => deleteTarget && remove.mutate(deleteTarget.id)}>
              {remove.isPending ? "Eliminazione…" : "Elimina ordine"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
