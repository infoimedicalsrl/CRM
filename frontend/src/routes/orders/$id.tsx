import { useEffect, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil, Trash2, RotateCcw, Truck } from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { DataTable, type DataTableColumn } from "@/components/app/data-table";
import { ProductCodeBadge, ZeroValueBadge } from "@/components/app/badges";
import { OrderEditDialog } from "@/components/app/order-edit-dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
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
import { deleteOrder, getOrder, getRestorePreview, restoreOrder, updateOrderDeliveryLine } from "@/services/orders";
import { humanizeError } from "@/services/api";
import { formatCurrency, formatDate, formatNumber } from "@/lib/format";
import type { OrderLine } from "@/types";

function DeliveryStatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    NON_CONSEGNATO: "Non consegnato",
    PARZIALMENTE_CONSEGNATO: "Parziale",
    COMPLETAMENTE_CONSEGNATO: "Consegnato",
    SOVRACONSEGNATO: "Sovraconsegnato",
  };
  return <Badge variant={status === "COMPLETAMENTE_CONSEGNATO" ? "default" : status === "NON_CONSEGNATO" ? "outline" : "secondary"}>{labels[status] ?? status}</Badge>;
}

function DeliveryLineControl({
  line,
  saving,
  onSave,
}: {
  line: { ordered_quantity: number; delivered_quantity: number; manual_delivered_quantity?: number | null };
  saving: boolean;
  onSave: (quantity: number | null) => void;
}) {
  const [value, setValue] = useState(String(line.delivered_quantity ?? 0));

  useEffect(() => {
    setValue(String(line.delivered_quantity ?? 0));
  }, [line.delivered_quantity]);

  const quantity = Number(value);
  const valid = Number.isFinite(quantity) && quantity >= 0;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Input
          className="h-9 w-28"
          type="number"
          min="0"
          step="0.01"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={saving}
          aria-label="Quantità consegnata"
        />
        <Button size="sm" disabled={saving || !valid} onClick={() => onSave(quantity)}>Salva</Button>
      </div>
      <div className="flex flex-wrap gap-1">
        <Button size="sm" variant="ghost" disabled={saving} onClick={() => onSave(0)}>Non consegnato</Button>
        <Button size="sm" variant="ghost" disabled={saving} onClick={() => onSave(line.ordered_quantity)}>Completo</Button>
        {line.manual_delivered_quantity != null && <Button size="sm" variant="ghost" disabled={saving} onClick={() => onSave(null)}>Usa DDT</Button>}
      </div>
      {line.manual_delivered_quantity != null && <div className="text-[10px] text-muted-foreground">Override manuale attivo</div>}
    </div>
  );
}

export const Route = createFileRoute("/orders/$id")({ component: OrderDetailPage });

function OrderDetailPage() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [restoreOpen, setRestoreOpen] = useState(false);
  const q = useQuery({ queryKey: ["orders", id], queryFn: () => getOrder(id), retry: false });
  const o = q.data;

  const preview = useQuery({queryKey:["orders",id,"restore-preview"],queryFn:()=>getRestorePreview(id),enabled:restoreOpen,retry:false});
  const restore = useMutation({mutationFn:()=>restoreOrder(id),onSuccess:async()=>{await Promise.all([q.refetch(),queryClient.invalidateQueries({queryKey:["dashboard"]}),queryClient.invalidateQueries({queryKey:["products"]}),queryClient.invalidateQueries({queryKey:["customers"]})]);setRestoreOpen(false);}});

  const deliveryUpdate = useMutation({
    mutationFn: ({ lineId, quantity }: { lineId: number; quantity: number | null }) => updateOrderDeliveryLine(id, lineId, quantity),
    onSuccess: async () => {
      await Promise.all([
        q.refetch(),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
  });

  const remove = useMutation({
    mutationFn: () => deleteOrder(id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["products"] }),
        queryClient.invalidateQueries({ queryKey: ["customers"] }),
        queryClient.invalidateQueries({ queryKey: ["analytics"] }),
      ]);
      navigate({ to: "/orders" });
    },
  });

  const cols: DataTableColumn<OrderLine>[] = [
    { key: "line", header: "Riga", cell: (l) => l.line_number ?? "—" },
    { key: "code", header: "Codice", cell: (l) => <ProductCodeBadge code={l.supplier_product_code} /> },
    { key: "desc", header: "Descrizione", className: "min-w-[320px] whitespace-normal", cell: (l) => <div className="flex items-center gap-2"><span>{l.description ?? "—"}</span>{l.is_zero_value && <ZeroValueBadge />}</div> },
    { key: "qty", header: "Quantità", align: "right", cell: (l) => `${formatNumber(l.quantity)} ${(l.unit ?? "").toUpperCase() === "C62" ? "PZ" : (l.unit ?? "")}` },
    { key: "price", header: "Prezzo unitario", align: "right", cell: (l) => formatCurrency(l.unit_price) },
    { key: "net", header: "Imponibile", align: "right", cell: (l) => formatCurrency(l.line_net) },
    { key: "vat", header: "IVA", align: "right", cell: (l) => `${formatNumber(l.vat_rate)}%` },
    { key: "vatamt", header: "IVA €", align: "right", cell: (l) => formatCurrency(l.vat_amount) },
    { key: "total", header: "Totale", align: "right", cell: (l) => <span className="font-semibold">{formatCurrency(l.line_total)}</span> },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={o ? `Ordine ${o.order_number}` : "Dettaglio ordine"}
        subtitle={o ? `${formatDate(o.order_date)} · ${o.customer_name ?? "Cliente"}` : "Caricamento…"}
        actions={
          <div className="flex flex-wrap gap-2">
            {o && (
              <>
                <Button variant="outline" onClick={() => setEditOpen(true)}><Pencil className="size-4" />Modifica</Button>
                <Button variant="outline" onClick={() => setRestoreOpen(true)}><RotateCcw className="size-4" />Ripristina da XML</Button>
                <Button variant="outline" className="text-destructive" onClick={() => setDeleteOpen(true)}><Trash2 className="size-4" />Elimina</Button>
              </>
            )}
            <Button asChild variant="outline"><Link to="/orders"><ArrowLeft className="size-4" />Ordini</Link></Button>
          </div>
        }
      />

      {o && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader><CardTitle>Cliente</CardTitle></CardHeader>
            <CardContent><div className="font-medium">{o.customer_name}</div><div className="text-sm text-muted-foreground">{o.customer_vat}</div></CardContent>
          </Card>
          <Card className="md:col-span-2">
            <CardHeader><CardTitle>Riepilogo ordine</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-3 gap-4">
              <div><div className="text-xs text-muted-foreground">Imponibile</div><div className="text-lg font-semibold">{formatCurrency(o.net_amount)}</div></div>
              <div><div className="text-xs text-muted-foreground">IVA</div><div className="text-lg font-semibold">{formatCurrency(o.vat_amount)}</div></div>
              <div><div className="text-xs text-muted-foreground">Totale</div><div className="text-lg font-semibold">{formatCurrency(o.total_amount)}</div></div>
            </CardContent>
          </Card>
        </div>
      )}

      {o?.delivery && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Truck className="size-5"/>Stato consegne</CardTitle>
            <p className="text-sm text-muted-foreground">Quantità calcolate dai DDT collegati alle righe dell'ordine.</p>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-4">
              <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Ordinato</div><div className="mt-1 text-lg font-semibold">{formatNumber(o.delivery.ordered_quantity)}</div></div>
              <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Consegnato</div><div className="mt-1 text-lg font-semibold">{formatNumber(o.delivery.delivered_quantity)}</div></div>
              <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Residuo</div><div className="mt-1 text-lg font-semibold">{formatNumber(o.delivery.residual_quantity)}</div></div>
              <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Stato</div><div className="mt-1 text-sm font-semibold">{({NON_CONSEGNATO:"Non consegnato",PARZIALMENTE_CONSEGNATO:"Parzialmente consegnato",COMPLETAMENTE_CONSEGNATO:"Completamente consegnato",SOVRACONSEGNATO:"Sovraconsegnato"} as Record<string,string>)[o.delivery.status] ?? o.delivery.status}</div></div>
            </div>
            <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-sm"><thead className="border-b"><tr><th className="px-3 py-2 text-left">Prodotto</th><th className="px-3 py-2 text-right">Ordinato</th><th className="px-3 py-2 text-right">Consegnato</th><th className="px-3 py-2 text-right">Residuo</th><th className="px-3 py-2 text-left">Stato</th><th className="px-3 py-2 text-left">Gestione</th></tr></thead><tbody>{o.delivery.lines.map(l=><tr key={l.order_line_id} className="border-b last:border-0 align-top"><td className="px-3 py-3"><div className="font-medium">{l.supplier_product_code}</div><div className="text-xs text-muted-foreground">{l.description??"—"}</div></td><td className="px-3 py-3 text-right">{formatNumber(l.ordered_quantity)} {l.unit_code??""}</td><td className="px-3 py-3 text-right font-semibold">{formatNumber(l.delivered_quantity)} {l.unit_code??""}{l.manual_delivered_quantity != null && <div className="mt-1 text-[10px] font-normal text-muted-foreground">quantità manuale</div>}</td><td className="px-3 py-3 text-right font-semibold">{formatNumber(l.residual_quantity)} {l.unit_code??""}</td><td className="px-3 py-3"><DeliveryStatusBadge status={l.status}/></td><td className="px-3 py-3"><DeliveryLineControl line={l} saving={deliveryUpdate.isPending} onSave={(quantity)=>deliveryUpdate.mutate({lineId:l.order_line_id,quantity})}/></td></tr>)}</tbody></table></div>
            {o.delivery.ddts.length>0 && <div><div className="mb-2 text-sm font-medium">Cronologia consegne</div><div className="space-y-2">{o.delivery.ddts.map(d=><Link key={d.id} to="/ddts/$id" params={{id:String(d.id)}} className="flex items-center justify-between rounded-lg border p-3 hover:bg-muted/30"><span><span className="font-medium">DDT {d.number}</span><span className="ml-2 text-sm text-muted-foreground">{formatDate(d.date)}</span></span><span className="text-sm">{formatNumber(d.quantity)} PZ</span></Link>)}</div></div>}
          </CardContent>
        </Card>
      )}

      <Card>
        <DataTable columns={cols} rows={o?.lines} isLoading={q.isLoading} isError={q.isError} onRetry={() => q.refetch()} emptyTitle="Nessuna riga ordine" getRowId={(l, i) => String(l.id ?? i)} />
      </Card>

      {o && <OrderEditDialog order={o} open={editOpen} onOpenChange={setEditOpen} onSaved={() => q.refetch()} />}


      <AlertDialog open={restoreOpen} onOpenChange={setRestoreOpen}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Ripristinare i dati originali XML?</AlertDialogTitle><AlertDialogDescription>Le modifiche manuali dell&apos;ordine verranno sostituite dai valori presenti nell&apos;XML originale archiviato localmente.</AlertDialogDescription></AlertDialogHeader>
          {preview.isLoading && <p className="text-sm text-muted-foreground">Lettura XML originale…</p>}
          {preview.isError && <p className="text-sm text-destructive">{humanizeError(preview.error)}</p>}
          {preview.data && <div className="rounded-lg border bg-muted/30 p-3 text-sm"><div><b>XML:</b> {preview.data.original.order_number} · {formatDate(preview.data.original.order_date)}</div><div><b>Cliente:</b> {preview.data.original.customer_name}</div><div><b>Totale:</b> {formatCurrency(preview.data.original.total_gross)}</div><div><b>Righe:</b> {preview.data.original.lines.length}</div></div>}
          {restore.isError && <p className="text-sm text-destructive">{humanizeError(restore.error)}</p>}
          <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel><AlertDialogAction disabled={!preview.data||restore.isPending} onClick={()=>restore.mutate()}>{restore.isPending?"Ripristino…":"Ripristina"}</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminare l&apos;ordine?</AlertDialogTitle>
            <AlertDialogDescription>
              L&apos;ordine <strong>{o?.order_number}</strong> verrà rimosso dal database e dalle analisi. Il documento originale resta invariato nell&apos;archivio.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {remove.isError && <p className="text-sm text-destructive">{humanizeError(remove.error)}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel>Annulla</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={() => remove.mutate()}>
              {remove.isPending ? "Eliminazione…" : "Elimina ordine"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
