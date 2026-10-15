import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { SearchInput } from "@/components/app/search-input";
import { DataTable, type DataTableColumn } from "@/components/app/data-table";
import { ProductCodeBadge } from "@/components/app/badges";
import { ExportMenu } from "@/components/app/export-menu";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { getProductCodeVariants, getProducts } from "@/services/products";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { Product } from "@/types";

export const Route = createFileRoute("/products/")({ component: ProductsPage });
function ProductsPage(){
  const navigate=useNavigate(); const [search,setSearch]=useState(""); const [auditOpen,setAuditOpen]=useState(false);
  const q=useQuery({queryKey:["products",search],queryFn:()=>getProducts({search}),retry:false});
  const variants=useQuery({queryKey:["products","code-variants"],queryFn:getProductCodeVariants,retry:false});
  const cols:DataTableColumn<Product>[]=[
    {key:"code",header:"Codice fornitore",cell:p=><ProductCodeBadge code={p.supplier_product_code}/>,sortValue:p=>p.supplier_product_code},
    {key:"desc",header:"Descrizione",className:"min-w-[360px] whitespace-normal",cell:p=>p.description ?? "—",sortValue:p=>p.description ?? ""},
    {key:"qty",header:"Quantità ordinata",align:"right",cell:p=>formatNumber(p.quantity_ordered),sortValue:p=>p.quantity_ordered ?? 0},
    {key:"orders",header:"Ordini",align:"right",cell:p=>formatNumber(p.orders_count),sortValue:p=>p.orders_count ?? 0},
    {key:"customers",header:"Clienti",align:"right",cell:p=>formatNumber(p.customers_count),sortValue:p=>p.customers_count ?? 0},
    {key:"revenue",header:"Fatturato netto",align:"right",cell:p=><span className="font-semibold">{formatCurrency(p.net_revenue)}</span>,sortValue:p=>p.net_revenue ?? 0},
  ];
  const suspectCount=variants.data?.length ?? 0;
  return <div className="space-y-6">
    <PageHeader title="Prodotti" subtitle="Ricerca e analizza i prodotti tramite il codice fornitore univoco." actions={<div className="flex gap-2"><Button variant="outline" onClick={()=>setAuditOpen(true)}>{suspectCount ? <AlertTriangle className="size-4"/> : <CheckCircle2 className="size-4"/>}Controllo codici{suspectCount ? ` (${suspectCount})` : ""}</Button><ExportMenu path="/api/exports/products" params={{search}}/></div>}/>
    <Card><CardContent className="pt-6"><SearchInput value={search} onChange={setSearch} placeholder="Cerca per codice fornitore o descrizione…" className="max-w-xl"/></CardContent></Card>
    <Card><DataTable columns={cols} rows={q.data} isLoading={q.isLoading} isError={q.isError} onRetry={()=>q.refetch()} onRowClick={p=>navigate({to:"/products/$id",params:{id:String(p.id)}})} emptyTitle="Nessun prodotto trovato" getRowId={p=>String(p.id)} defaultSortKey="revenue"/></Card>
    <Dialog open={auditOpen} onOpenChange={setAuditOpen}><DialogContent className="max-w-3xl"><DialogHeader><DialogTitle>Controllo codici prodotto</DialogTitle><DialogDescription>Il sistema ignora spazi e maiuscole/minuscole nell'identità prodotto, ma conserva le forme ricevute dagli XML.</DialogDescription></DialogHeader>
      {variants.isLoading ? <p className="text-sm text-muted-foreground">Controllo in corso…</p> : suspectCount===0 ? <div className="rounded-xl border bg-muted/30 p-5 text-sm"><div className="flex items-center gap-2 font-medium"><CheckCircle2 className="size-4"/>Nessuna variante sospetta rilevata</div><p className="mt-1 text-muted-foreground">Non sono state ricevute forme diverse dello stesso codice.</p></div> : <div className="max-h-[55vh] space-y-3 overflow-auto">{variants.data?.map(g=><div key={g.product_id} className="rounded-xl border p-4"><div className="flex flex-wrap items-center gap-2"><ProductCodeBadge code={g.canonical_code}/><span className="font-medium">{g.description ?? "—"}</span></div><div className="mt-3 flex flex-wrap gap-2">{g.variants.map(v=><span key={v.code} className="rounded-md bg-muted px-2 py-1 font-mono text-xs">{v.code} · {v.occurrences}×</span>)}</div></div>)}</div>}
    </DialogContent></Dialog>
  </div>;
}
