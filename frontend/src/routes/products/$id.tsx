import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { LineChart, Line, ResponsiveContainer, CartesianGrid, XAxis, YAxis, Tooltip as RTooltip } from "recharts";
import { PageHeader } from "@/components/app/page-header";
import { KpiCard } from "@/components/app/kpi-card";
import { ProductCodeBadge } from "@/components/app/badges";
import { DataTable, type DataTableColumn } from "@/components/app/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { getProduct, type ProductDetail } from "@/services/products";
import { formatCurrency, formatDate, formatNumber } from "@/lib/format";

export const Route = createFileRoute("/products/$id")({ component: ProductDetailPage });
function ProductDetailPage(){
 const {id}=Route.useParams(); const q=useQuery({queryKey:["products",id],queryFn:()=>getProduct(id),retry:false}); const p=q.data;
 const cols:DataTableColumn<ProductDetail["by_customer"][number]>[]=[
  {key:"customer",header:"Cliente",cell:r=>r.customer,sortValue:r=>r.customer},{key:"qty",header:"Quantità",align:"right",cell:r=>`${formatNumber(r.quantity)} ${r.unit_code ?? ""}`,sortValue:r=>r.quantity},{key:"orders",header:"Ordini",align:"right",cell:r=>formatNumber(r.orders),sortValue:r=>r.orders},{key:"net",header:"Fatturato",align:"right",cell:r=>formatCurrency(r.net),sortValue:r=>r.net}
 ];
 const recentCols:DataTableColumn<ProductDetail["recent_orders"][number]>[]=[{key:"date",header:"Data",cell:r=>formatDate(r.order_date)},{key:"order",header:"Ordine",cell:r=><Link to="/orders/$id" params={{id:String(r.order_id)}} className="font-medium hover:underline">{r.order_number}</Link>},{key:"customer",header:"Cliente",className:"min-w-[220px]",cell:r=>r.customer},{key:"qty",header:"Quantità",align:"right",cell:r=>`${formatNumber(r.quantity)} ${r.unit_code??""}`},{key:"price",header:"Prezzo",align:"right",cell:r=>formatCurrency(r.unit_price)},{key:"net",header:"Fatturato",align:"right",cell:r=>formatCurrency(r.line_net)}];
 return <div className="space-y-6"><PageHeader eyebrow={p&&<ProductCodeBadge code={p.supplier_product_code}/>} title={p?.description ?? "Dettaglio prodotto"} subtitle="Identità prodotto basata esclusivamente sul codice fornitore." actions={<Button asChild variant="outline"><Link to="/products"><ArrowLeft className="size-4"/>Prodotti</Link></Button>}/>{p&&<><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><KpiCard label="Quantità ordinata" value={formatNumber(p.quantity_ordered)}/><KpiCard label="Fatturato netto" value={formatCurrency(p.net_revenue)} tone="accent"/><KpiCard label="Prezzo medio" value={formatCurrency(p.average_price)}/><KpiCard label="Quantità a valore zero" value={formatNumber(p.zero_value_quantity)}/></div><div className="grid gap-4 xl:grid-cols-2"><Card><CardHeader><CardTitle>Vendite per cliente</CardTitle></CardHeader><CardContent className="p-0"><DataTable columns={cols} rows={p.by_customer} getRowId={r=>`${r.customer_id}-${r.unit_code ?? ""}`}/></CardContent></Card><Card><CardHeader><CardTitle>Andamento nel tempo</CardTitle></CardHeader><CardContent><ResponsiveContainer width="100%" height={300}><LineChart data={p.trend}><CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)"/><XAxis dataKey="order_date" tickFormatter={v=>formatDate(v)}/><YAxis/><RTooltip formatter={(v:number)=>formatCurrency(v)}/><Line type="monotone" dataKey="net" name="Fatturato" stroke="var(--color-chart-1)" strokeWidth={2}/><Line type="monotone" dataKey="average_price" name="Prezzo medio" stroke="var(--color-chart-2)" strokeWidth={2}/></LineChart></ResponsiveContainer></CardContent></Card></div><Card><CardHeader><CardTitle>Ordini recenti</CardTitle></CardHeader><CardContent className="p-0"><DataTable columns={recentCols} rows={p.recent_orders} getRowId={r=>`${r.order_id}-${r.order_date}`}/></CardContent></Card></>}{q.isError&&<Card><CardContent className="py-10 text-center text-destructive">Impossibile caricare il prodotto.</CardContent></Card>}</div>;
}
