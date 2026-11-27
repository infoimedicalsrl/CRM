import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/app/page-header";
import { ExportMenu } from "@/components/app/export-menu";
import { SearchInput } from "@/components/app/search-input";
import { DataTable, type DataTableColumn } from "@/components/app/data-table";
import { Card, CardContent } from "@/components/ui/card";
import { getCustomers } from "@/services/customers";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { Customer } from "@/types";

export const Route = createFileRoute("/customers/")({ component: CustomersPage });
function CustomersPage(){const navigate=useNavigate();const[search,setSearch]=useState("");const q=useQuery({queryKey:["customers",search],queryFn:()=>getCustomers({search}),retry:false});const cols:DataTableColumn<Customer>[]=[{key:"name",header:"Cliente",cell:c=><div><div className="font-medium">{c.name}</div><div className="text-xs text-muted-foreground">{c.vat_number ?? ""}</div></div>,sortValue:c=>c.name},{key:"orders",header:"Ordini",align:"right",cell:c=>formatNumber(c.orders_count),sortValue:c=>c.orders_count ?? 0},{key:"products",header:"Prodotti",align:"right",cell:c=>formatNumber(c.products_count),sortValue:c=>c.products_count ?? 0},{key:"qty",header:"Quantità",align:"right",cell:c=>formatNumber(c.total_quantity),sortValue:c=>c.total_quantity ?? 0},{key:"net",header:"Fatturato netto",align:"right",cell:c=><span className="font-semibold">{formatCurrency(c.net_revenue)}</span>,sortValue:c=>c.net_revenue ?? 0}];return <div className="space-y-6"><PageHeader title="Clienti" subtitle="Consulta e rinomina i clienti senza modificare la loro identità fiscale." actions={<ExportMenu path="/api/exports/customers" params={{search}}/>}/><Card><CardContent className="pt-6"><SearchInput value={search} onChange={setSearch} placeholder="Cerca cliente o P.IVA…" className="max-w-xl"/></CardContent></Card><Card><DataTable columns={cols} rows={q.data} isLoading={q.isLoading} isError={q.isError} onRetry={()=>q.refetch()} onRowClick={c=>navigate({to:"/customers/$id",params:{id:String(c.id)}})} getRowId={c=>String(c.id)} emptyTitle="Nessun cliente trovato" defaultSortKey="net"/></Card></div>}
