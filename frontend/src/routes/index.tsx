import { useMemo, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer,
  Tooltip as RTooltip, XAxis, YAxis,
} from "recharts";
import {
  ArrowRight, CalendarDays, FileText, Lightbulb,
  RefreshCw, SlidersHorizontal, TrendingUp, Users,
} from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { GlobalFilters } from "@/components/app/global-filters";
import { ChartSkeleton, ErrorState, KpiSkeleton } from "@/components/app/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { formatCurrency } from "@/lib/format";
import { getDashboard } from "@/services/dashboard";
import { apiGet } from "@/services/api";
import type { GlobalFilterState } from "@/types";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [{ title: "Dashboard — Peppol Sales Analytics" }, { name: "description", content: "Panoramica economica e operativa di Peppol Sales Analytics." }] }),
  component: DashboardPage,
});

type FinancialSummary = { invoice_net: number; invoice_vat: number; invoice_count: number; received_total: number };

type SalesInvoice = {
  id: number; invoice_number: string; issue_date: string; customer_name: string;
  net_amount: number; vat_amount: number; gross_amount: number; status: string;
  source_filename?: string; source_format?: string;
};

const STATUS_COLORS: Record<string, string> = {
  INCASSATA: "#36B989", INCASSO_PARZIALE: "#F5A342", DA_INCASSARE: "#438BFA",
  SCADUTA: "#F46D67", ANNULLATA: "#A3AEC2",
};
const MONTHS = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

function DashboardPage() {
  const navigate = useNavigate();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(String(currentYear));
  const [filters, setFilters] = useState<GlobalFilterState>({ from: `${currentYear}-01-01`, to: `${currentYear}-12-31` });
  const [filtersOpen, setFiltersOpen] = useState(false);
  const dashboard = useQuery({ queryKey: ["dashboard", filters], queryFn: () => getDashboard(filters), retry: false });
  const invoices = useQuery({ queryKey: ["dashboard", "sales-invoices"], queryFn: () => apiGet<SalesInvoice[]>("/api/sales-invoices"), retry: false });
  const financial = useQuery({ queryKey: ["dashboard", "financial-summary", filters.from, filters.to], queryFn: () => apiGet<FinancialSummary>("/api/dashboard/financial-summary", { date_from: filters.from, date_to: filters.to }), retry: false });
  const data = dashboard.data;
  const allInvoices = invoices.data ?? [];
  const yearInvoices = useMemo(() => allInvoices.filter((invoice) => (!filters.from || invoice.issue_date >= filters.from) && (!filters.to || invoice.issue_date <= filters.to)), [allInvoices, filters.from, filters.to]);
  // I grafici annuali seguono sempre l'anno selezionato, anche quando i filtri globali
  // hanno un intervallo personalizzato o attraversano due anni.
  const selectedYearInvoices = useMemo(() => allInvoices.filter((invoice) => (invoice.issue_date || "").slice(0, 4) === year), [allInvoices, year]);
  const invoiceStatus = useMemo(() => {
    const groups = new Map<string, number>();
    for (const invoice of yearInvoices) groups.set(invoice.status, (groups.get(invoice.status) ?? 0) + 1);
    return Array.from(groups, ([status, value]) => ({ status, label: statusLabel(status), value }));
  }, [yearInvoices]);
  const topCustomers = (data?.top_customers ?? []).slice(0, 5);
  // I due valori (netto e lordo) sono due serie di barre affiancate per ogni mese.
  // Si usano le fatture emesse e si crea sempre una voce per tutti i 12 mesi.
  const invoiceTrend = useMemo(() => {
    const values = MONTHS.map((month) => ({ month, net: 0, gross: 0 }));
    for (const invoice of selectedYearInvoices) {
      const issueDate = (invoice.issue_date || "").slice(0, 10);
      const monthNumber = Number(issueDate.slice(5, 7));
      if (!/^\d{4}-\d{2}-\d{2}$/.test(issueDate) || !Number.isInteger(monthNumber) || monthNumber < 1 || monthNumber > 12) continue;
      const entry = values[monthNumber - 1];
      const net = Number(invoice.net_amount);
      const gross = Number(invoice.gross_amount);
      entry.net += Number.isFinite(net) ? net : 0;
      entry.gross += Number.isFinite(gross) ? gross : 0;
    }
    return values;
  }, [selectedYearInvoices]);
  const invoiceCustomerDistribution = useMemo(() => {
    const totals = new Map<string, { name: string; gross_revenue: number }>();
    for (const invoice of selectedYearInvoices) {
      const name = (invoice.customer_name || "Cliente non indicato").trim() || "Cliente non indicato";
      const entry = totals.get(name) ?? { name, gross_revenue: 0 };
      const gross = Number(invoice.gross_amount);
      entry.gross_revenue += Number.isFinite(gross) ? gross : 0;
      totals.set(name, entry);
    }
    const ranked = Array.from(totals.values()).sort((a, b) => b.gross_revenue - a.gross_revenue);
    const principal = ranked.slice(0, 4);
    const otherTotal = ranked.slice(4).reduce((sum, customer) => sum + customer.gross_revenue, 0);
    if (otherTotal > 0) principal.push({ name: "Altri clienti", gross_revenue: otherTotal });
    return principal;
  }, [selectedYearInvoices]);
  const selectedYearGross = useMemo(() => selectedYearInvoices.reduce((sum, invoice) => {
    const gross = Number(invoice.gross_amount);
    return sum + (Number.isFinite(gross) ? gross : 0);
  }, 0), [selectedYearInvoices]);
  const hasYearRevenue = invoiceTrend.some((item) => item.net > 0 || item.gross > 0);
  const latestInvoices = yearInvoices.slice().sort((a, b) => b.issue_date.localeCompare(a.issue_date)).slice(0, 5);
  const activities = latestInvoices.slice(0, 5).map((invoice) => ({ id: `invoice-${invoice.id}`, title: invoice.status === "INCASSATA" ? "Fattura incassata" : "Fattura registrata", detail: `${invoice.invoice_number} · ${invoice.customer_name}`, date: invoice.issue_date }));

  function changeYear(nextYear: string) {
    setYear(nextYear);
    setFilters((previous) => ({ ...previous, from: `${nextYear}-01-01`, to: `${nextYear}-12-31` }));
  }

  return (
    <div className="dashboard-page space-y-4">
      <PageHeader
        title="Dashboard"
        subtitle="Panoramica della tua attività commerciale"
        actions={<div className="flex flex-wrap items-center gap-2">
          <label className="dashboard-year-select"><CalendarDays className="size-4" aria-hidden /><span className="sr-only">Anno di riferimento</span><select aria-label="Anno di riferimento" value={year} onChange={(event) => changeYear(event.target.value)}>{Array.from({ length: 6 }, (_, i) => currentYear - i).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <Button variant="ghost" size="sm" onClick={() => { void dashboard.refetch(); void invoices.refetch(); void financial.refetch(); }}><RefreshCw className="size-4" aria-hidden /> Aggiorna</Button>
          <Button variant="outline" size="sm" onClick={() => setFiltersOpen(true)}><SlidersHorizontal className="size-4" aria-hidden /> Filtri</Button>
        </div>}
      />

      <Dialog open={filtersOpen} onOpenChange={setFiltersOpen}>
        <DialogContent className="w-[calc(100%_-_2rem)] max-w-3xl p-0 sm:rounded-2xl">
          <div className="border-b px-6 py-5"><DialogHeader><DialogTitle>Filtra dashboard</DialogTitle><DialogDescription>Il periodo iniziale corrisponde all'anno solare selezionato.</DialogDescription></DialogHeader></div>
          <div className="px-6 py-6"><GlobalFilters value={filters} onApply={(value) => { setFilters(value); if (value.from?.slice(0, 4) === value.to?.slice(0, 4)) setYear(value.from.slice(0, 4)); }} bare onApplied={() => setFiltersOpen(false)} /></div>
        </DialogContent>
      </Dialog>

      {dashboard.isLoading ? <KpiSkeleton /> : dashboard.isError ? <Card><ErrorState onRetry={() => dashboard.refetch()} /></Card> : <>
        <div className="dashboard-main-grid">
          <div className="dashboard-primary-column space-y-3">
            <Card className="dashboard-panel dashboard-economic-panel">
              <CardHeader className="dashboard-panel-header"><CardTitle>Riepilogo economico {year}</CardTitle></CardHeader>
              <CardContent className="dashboard-economic-grid">
                <MetricCard label="Fatturato netto" value={financial.isError ? "—" : formatCurrency(financial.data?.invoice_net)} tone="blue" hint="Somma degli imponibili delle fatture emesse" />
                <MetricCard label="Fatturato lordo" value={formatCurrency(yearInvoices.reduce((sum, invoice) => sum + Number(invoice.gross_amount || 0), 0))} tone="green" hint="Totale fatture emesse, IVA inclusa" />
                <MetricCard label="IVA" value={financial.isError ? "—" : formatCurrency(financial.data?.invoice_vat)} tone="purple" hint="Somma dell'IVA delle fatture emesse" />
              </CardContent>
            </Card>

            <div className="grid gap-3 xl:grid-cols-[1.18fr_0.92fr]">
              <Card className="dashboard-panel">
                <CardHeader className="dashboard-panel-header dashboard-chart-header"><CardTitle>Andamento fatturato {year}</CardTitle></CardHeader>
                <CardContent className="dashboard-revenue-chart-content">
                  {invoices.isLoading ? <ChartSkeleton /> : invoices.isError ? <p className="w-full py-12 text-center text-sm text-muted-foreground">Impossibile caricare le fatture. Usa “Aggiorna” e riprova.</p> : <>
                    <ResponsiveContainer width="100%" height={250}>
                      <BarChart data={invoiceTrend} barGap={4} barCategoryGap="18%" margin={{ top: 8, right: 10, left: 4, bottom: 4 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#E2EAF5" vertical={false} />
                        <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#526782" }} axisLine={false} tickLine={false} interval={0} />
                        <YAxis domain={[0, (max: number) => Math.max(max, 1000)]} tickFormatter={(value) => value >= 1000 ? `€${Math.round(value / 1000)}k` : `€${value}`} tick={{ fontSize: 10, fill: "#526782" }} axisLine={false} tickLine={false} width={48} />
                        <RTooltip formatter={(value: number, name: string) => [formatCurrency(value), name]} />
                        <Legend verticalAlign="top" align="right" height={28} iconType="circle" wrapperStyle={{ fontSize: 11, color: "#526782" }} />
                        <Bar dataKey="net" name="Netto" fill="#438BFA" radius={[4, 4, 0, 0]} maxBarSize={22} />
                        <Bar dataKey="gross" name="Lordo" fill="#52C1D7" radius={[4, 4, 0, 0]} maxBarSize={22} />
                      </BarChart>
                    </ResponsiveContainer>
                    {!hasYearRevenue && <p className="-mt-2 pb-2 text-center text-xs text-muted-foreground">Nessuna fattura con importi registrati nel {year}: il grafico è pronto ma non ci sono barre da rappresentare.</p>}
                  </>}
                </CardContent>
              </Card>
              <Card className="dashboard-panel">
                <CardHeader className="dashboard-panel-header"><CardTitle>Distribuzione fatturato per cliente</CardTitle></CardHeader>
                <CardContent className="dashboard-donut-content">
                  {invoices.isLoading ? <ChartSkeleton /> : invoices.isError ? <p className="w-full py-12 text-center text-sm text-muted-foreground">Impossibile caricare le fatture.</p> : invoiceCustomerDistribution.length === 0 ? <p className="w-full py-12 text-center text-sm text-muted-foreground">Nessuna fattura emessa nel {year}.</p> : <>
                    <div className="dashboard-donut-chart">
                      <ResponsiveContainer width="100%" height={210}>
                        <PieChart>
                          <Pie data={invoiceCustomerDistribution} dataKey="gross_revenue" nameKey="name" innerRadius={58} outerRadius={82} paddingAngle={2} stroke="white" strokeWidth={2}>
                            {invoiceCustomerDistribution.map((customer, index) => <Cell key={customer.name} fill={["#438BFA", "#52B8D9", "#F5A342", "#A879F7", "#36B989"][index % 5]} />)}
                          </Pie>
                          <RTooltip formatter={(value: number) => formatCurrency(value)} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="dashboard-donut-center"><strong>{formatCurrency(selectedYearGross)}</strong><span>fatturato lordo</span></div>
                    </div>
                    <div className="dashboard-legend">{invoiceCustomerDistribution.map((customer, index) => {
                      const color = ["#438BFA", "#52B8D9", "#F5A342", "#A879F7", "#36B989"][index % 5];
                      const share = selectedYearGross > 0 ? customer.gross_revenue / selectedYearGross * 100 : 0;
                      return <div className="dashboard-legend-row" key={customer.name}><span className="dashboard-legend-dot" style={{ background: color }} /><span className="dashboard-legend-name">{customer.name}</span><span className="dashboard-legend-share">{share.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%</span><strong>{formatCurrency(customer.gross_revenue)}</strong></div>;
                    })}</div>
                  </>}
                </CardContent>
              </Card>
            </div>

            <div className="grid gap-3 xl:grid-cols-2">
              <Card className="dashboard-panel">
                <CardHeader className="dashboard-panel-header"><CardTitle>Fatture per stato</CardTitle></CardHeader>
                <CardContent className="dashboard-donut-content">
                  {invoices.isLoading ? <div className="p-6 text-sm text-muted-foreground">Caricamento fatture…</div> : invoices.isError ? <p className="text-sm text-muted-foreground">Archivio fatture non disponibile.</p> : invoiceStatus.length === 0 ? <p className="p-6 text-sm text-muted-foreground">Nessuna fattura registrata nel {year}.</p> : <><div className="dashboard-status-chart"><ResponsiveContainer width="100%" height={190}><PieChart><Pie data={invoiceStatus} dataKey="value" nameKey="label" innerRadius={48} outerRadius={72} paddingAngle={2}>{invoiceStatus.map((item) => <Cell key={item.status} fill={STATUS_COLORS[item.status] ?? "#A3AEC2"} />)}</Pie><RTooltip formatter={(value: number) => [value, "Fatture"]} /></PieChart></ResponsiveContainer></div><div className="dashboard-status-list">{invoiceStatus.map((item) => <div className="dashboard-status-row" key={item.status}><span className="dashboard-legend-dot" style={{ background: STATUS_COLORS[item.status] ?? "#A3AEC2" }} /><span>{item.label}</span><strong>{item.value} <small>({Math.round(item.value / yearInvoices.length * 100)}%)</small></strong></div>)}</div></>}
                </CardContent>
              </Card>
              <Card className="dashboard-panel">
                <CardHeader className="dashboard-panel-header"><CardTitle>Top 5 clienti per fatturato</CardTitle><Button variant="ghost" size="sm" onClick={() => navigate({ to: "/customers" })}>Vedi tutti <ArrowRight className="size-3.5" /></Button></CardHeader>
                <CardContent className="dashboard-top-customers">{topCustomers.length === 0 ? <p className="text-sm text-muted-foreground">Nessun cliente nel periodo.</p> : topCustomers.map((customer, index) => { const max = Math.max(...topCustomers.map((entry) => entry.net_revenue ?? 0), 1); return <button key={customer.id} type="button" onClick={() => navigate({ to: "/customers/$id", params: { id: customer.id } })} className="dashboard-customer-row"><span className="dashboard-customer-rank">{index + 1}.</span><span className="dashboard-customer-detail"><span className="dashboard-customer-name">{customer.name}</span><span className="dashboard-progress-track"><span className="dashboard-progress-fill" style={{ width: `${Math.max(3, (customer.net_revenue ?? 0) / max * 100)}%` }} /></span></span><strong>{formatCurrency(customer.net_revenue)}</strong></button>; })}</CardContent>
              </Card>
            </div>
            <div className="dashboard-tip"><Lightbulb className="size-6 shrink-0" /><div className="min-w-0 flex-1"><strong>Suggerimento</strong><p>Per ottenere un'analisi più dettagliata, vai alla sezione Report e genera i tuoi report personalizzati.</p></div><Button size="sm" onClick={() => navigate({ to: "/analytics" })}>Vai ai report <ArrowRight className="size-4" /></Button></div>
          </div>

          <aside className="dashboard-side-column space-y-3">
            <Card className="dashboard-panel dashboard-side-panel"><CardHeader className="dashboard-panel-header"><CardTitle>Ultime fatture emesse</CardTitle><Button variant="ghost" size="sm" onClick={() => navigate({ to: "/sales-invoices" })}>Vedi tutte <ArrowRight className="size-3.5" /></Button></CardHeader><CardContent className="dashboard-invoice-list">{invoices.isLoading ? <p className="p-4 text-sm text-muted-foreground">Caricamento…</p> : latestInvoices.length === 0 ? <p className="p-4 text-sm text-muted-foreground">Nessuna fattura nell'anno selezionato.</p> : latestInvoices.map((invoice) => <button key={invoice.id} type="button" className="dashboard-invoice-row" onClick={() => navigate({ to: "/sales-invoices/$id", params: { id: String(invoice.id) } })}><span className="dashboard-invoice-main"><strong>{invoice.invoice_number}</strong><span>{invoice.customer_name}</span><time>{formatDate(invoice.issue_date)}</time></span><span className="dashboard-invoice-total"><strong>{formatCurrency(invoice.gross_amount)}</strong><span className={`dashboard-status-pill ${invoice.status === "INCASSATA" ? "is-paid" : invoice.status === "SCADUTA" ? "is-overdue" : "is-open"}`}>{statusLabel(invoice.status)}</span></span></button>)}</CardContent></Card>
            <Card className="dashboard-panel dashboard-side-panel"><CardHeader className="dashboard-panel-header"><CardTitle>Attività recenti</CardTitle><Button variant="ghost" size="sm" onClick={() => navigate({ to: "/imports" })}>Vedi tutte <ArrowRight className="size-3.5" /></Button></CardHeader><CardContent className="dashboard-activity-list">{activities.length === 0 ? <p className="p-4 text-sm text-muted-foreground">Nessuna attività da mostrare.</p> : activities.map((activity) => <div className="dashboard-activity-row" key={activity.id}><span className="dashboard-activity-copy"><strong>{activity.title}</strong><span>{activity.detail}</span></span><time>{formatDate(activity.date)}</time></div>)}</CardContent></Card>
          </aside>
        </div>
      </>}
    </div>
  );
}

function MetricCard({ label, value, tone, hint }: { label: string; value: string; tone: "blue" | "green" | "purple" | "orange"; hint: string }) {
  return <div className={`dashboard-metric tone-${tone}`}><div className="dashboard-metric-heading"><span>{label}</span></div><strong className="dashboard-metric-value">{value}</strong><span className="dashboard-metric-hint">{hint}</span></div>;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = { INCASSATA: "Incassata", INCASSO_PARZIALE: "Parziale", DA_INCASSARE: "Da incassare", SCADUTA: "Scaduta", ANNULLATA: "Annullata" };
  return labels[status] ?? status.replaceAll("_", " ").toLowerCase();
}
function formatDate(value: string) {
  if (!value) return "—";
  const date = new Date(`${value.slice(0, 10)}T12:00:00`);
  return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}
