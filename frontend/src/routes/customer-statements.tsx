import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { RefreshCw, FileSpreadsheet, CheckCircle2, AlertTriangle, Upload, ChevronDown } from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { apiGet, apiPost, apiPostForm, apiBlobUrl, humanizeError } from "@/services/api";

export const Route = createFileRoute("/customer-statements")({ component: CustomerStatementsPage });
type StatementRow = { id: number; office_document_type: string | null; document_number: string; order_number: string | null; amount: number | null; vat_withholdings: number | null; paid: number | null; balance: number | null; liquidated: string | null; row_date: string | null; status: string | null; match_status: string; match_note: string | null; invoice_id: number | null; invoice_number: string | null };
type StatementImport = { id: number; filename: string; file_format: string; imported_at: string; source_year: number; rows_imported: number; rows_ignored_other_year: number; rows_unmatched: number; rows_matched: number; rows?: StatementRow[] };
const eur = (v: number | null) => v === null || v === undefined ? "—" : new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);

function CustomerStatementsPage() {
  const [items, setItems] = useState<StatementImport[]>([]);
  const [active, setActive] = useState<StatementImport | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importMessage, setImportMessage] = useState("");
  const [targetDocument, setTargetDocument] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const list = await apiGet<StatementImport[]>("/api/customer-statements");
      setItems(list);
      if (active) {
        const updated = list.find((x) => x.id === active.id);
        if (updated) setActive(await apiGet<StatementImport>(`/api/customer-statements/${updated.id}`));
        else setActive(null);
      } else if (list.length) {
        setActive(await apiGet<StatementImport>(`/api/customer-statements/${list[0].id}`));
      }
      setError("");
    } catch (e) { setError(humanizeError(e)); }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const doc = params.get("document_number") || "";
    const invoice = params.get("invoice_number") || "";
    setTargetDocument(doc || invoice);
    void (async () => {
      try {
        const list = await apiGet<StatementImport[]>("/api/customer-statements");
        setItems(list);
        if (doc || invoice) {
          for (const item of list) {
            const detail = await apiGet<StatementImport>(`/api/customer-statements/${item.id}`);
            if ((detail.rows ?? []).some((r) => (doc && r.document_number === doc) || (invoice && r.invoice_number === invoice))) { setActive(detail); break; }
          }
        } else if (list.length) setActive(await apiGet<StatementImport>(`/api/customer-statements/${list[0].id}`));
      } catch (e) { setError(humanizeError(e)); }
    })();
  }, []);

  async function openItem(item: StatementImport) {
    try { setActive(await apiGet<StatementImport>(`/api/customer-statements/${item.id}`)); setError(""); }
    catch (e) { setError(humanizeError(e)); }
  }

  async function rematchStatements() {
    try {
      setError(""); setImportMessage("");
      const result = await apiPost<{ rows_processed: number; rows_matched: number; rows_unmatched: number }>("/api/customer-statements/rematch", {});
      setImportMessage(`Abbinamenti aggiornati: ${result.rows_matched} abbinate su ${result.rows_processed}; ${result.rows_unmatched} da verificare.`);
      await load();
    } catch (e) { setError(humanizeError(e)); }
  }

  async function importStatement() {
    if (!importFile) return;
    setImportBusy(true); setError(""); setImportMessage("");
    try {
      const fd = new FormData(); fd.append("file", importFile);
      const r = await apiPostForm<{ filename: string; rows_imported: number; rows_matched: number; rows_unmatched: number }>("/api/customer-statements/import", fd);
      setImportMessage(`Importazione completata: ${r.rows_imported} righe, ${r.rows_matched} abbinate, ${r.rows_unmatched} da verificare.`);
      setImportFile(null); if (fileInput.current) fileInput.current.value = "";
      const list = await apiGet<StatementImport[]>("/api/customer-statements"); setItems(list);
      if (list.length) setActive(await apiGet<StatementImport>(`/api/customer-statements/${list[0].id}`));
    } catch (e) { setError(humanizeError(e)); }
    finally { setImportBusy(false); }
  }

  useEffect(() => {
    if (!targetDocument || !active) return;
    const row = (active.rows ?? []).find((r) => r.document_number === targetDocument || r.invoice_number === targetDocument);
    if (row) window.setTimeout(() => document.getElementById(`statement-row-${row.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 250);
  }, [active, targetDocument]);

  const rows = active?.rows ?? [];
  const visibleRows = rows.filter((r) => !search || [r.document_number, r.order_number, r.office_document_type, r.status, r.invoice_number].some((x) => (x ?? "").toLowerCase().includes(search.toLowerCase())));
  const matchedCount = rows.filter((r) => r.match_status === "ABBINATA_INCASSATA").length;

  return <main className="w-full min-w-0 space-y-5 p-4 md:p-6">
    <PageHeader title="Estratto conto online" actions={<div className="flex flex-wrap items-center gap-2"><button onClick={() => void rematchStatements()} title="Ricalcola gli abbinamenti con tutte le fatture presenti" className="inline-flex h-9 items-center gap-2 rounded-md border bg-card px-3 text-sm">Ricalcola abbinamenti</button><button onClick={() => void load()} title="Aggiorna archivio" aria-label="Aggiorna archivio" className="inline-flex h-9 items-center gap-2 rounded-md border bg-card px-3 text-sm"><RefreshCw className="size-4"/> Aggiorna</button></div>} />

    <input ref={fileInput} type="file" accept=".pdf,.csv,application/pdf,text/csv" className="hidden" onChange={(e) => { const file = e.target.files?.[0] ?? null; setImportFile(file); if (file) { setImportMessage(""); setError(""); } }} />
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <article className="rounded-xl border bg-card p-5"><div className="flex items-center gap-2 text-sm font-medium text-muted-foreground"><FileSpreadsheet className="size-4"/>Righe importate</div><div className="mt-3 text-3xl font-semibold tracking-tight">{active ? active.rows_imported : 0}</div><p className="mt-2 text-sm text-muted-foreground">Righe presenti nell’estratto selezionato</p></article>
      <article className="rounded-xl border bg-card p-5"><div className="flex items-center gap-2 text-sm font-medium text-muted-foreground"><CheckCircle2 className="size-4"/>Abbinate</div><div className="mt-3 text-3xl font-semibold tracking-tight">{matchedCount}</div><p className="mt-2 text-sm text-muted-foreground">Righe abbinate a una fattura di vendita</p></article>
      <article className="rounded-xl border bg-card p-5"><div className="text-sm font-medium text-muted-foreground">Carica estratto conto</div><p className="mt-2 text-sm text-muted-foreground">Seleziona un file CSV oppure un PDF testuale.</p><button type="button" disabled={importBusy} onClick={() => importFile ? void importStatement() : fileInput.current?.click()} className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"><Upload className="size-4"/>{importBusy ? "Importazione…" : importFile ? `Importa ${importFile.name}` : "Scegli file"}</button>{importFile && <button type="button" className="mt-2 w-full text-xs text-muted-foreground underline" onClick={() => { setImportFile(null); if (fileInput.current) fileInput.current.value = ""; }}>Rimuovi file selezionato</button>}</article>
    </section>

    {importMessage && <p role="status" className="rounded-md bg-muted p-3 text-sm">{importMessage}</p>}
    {error && <p role="alert" className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">{error}</p>}

    <details className="group rounded-xl border bg-card">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4 font-semibold [&::-webkit-details-marker]:hidden"><span>Storico importazioni <span className="ml-2 text-sm font-normal text-muted-foreground">{items.length} file</span></span><ChevronDown className="size-4 transition-transform group-open:rotate-180"/></summary>
      <div className="grid gap-2 border-t p-3 sm:grid-cols-2 xl:grid-cols-3">{items.length === 0 ? <p className="p-2 text-sm text-muted-foreground">Nessun estratto conto importato.</p> : items.map((item) => <button key={item.id} onClick={() => void openItem(item)} className={`rounded-lg border p-3 text-left ${active?.id === item.id ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`}><span className="flex items-center gap-2 font-medium"><FileSpreadsheet className="size-4 shrink-0"/><span className="truncate">{item.filename}</span></span><span className="mt-1 block text-xs text-muted-foreground">Importato il {new Date(item.imported_at).toLocaleString("it-IT")}</span><span className="mt-2 block text-xs">{item.rows_matched} abbinate · {item.rows_unmatched} da verificare · {item.rows_ignored_other_year} escluse</span></button>)}</div>
    </details>

    <section className="w-full min-w-0 rounded-xl border bg-card p-3 md:p-5">
      {!active ? <div className="py-16 text-center text-sm text-muted-foreground">Carica un estratto conto oppure seleziona un file dallo storico importazioni.</div> : <>
        {active.file_format === "PDF" && <div className="mb-4 overflow-hidden rounded-lg border bg-muted/20"><AuthedPdfFrame path={`/api/customer-statements/${active.id}/file`}/></div>}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">Movimenti dell’estratto conto</h2><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca documento, ordinativo, stato…" className="h-9 w-full max-w-sm rounded-md border bg-background px-3 text-sm"/></div>
        <div className="w-full overflow-x-auto"><table className="w-full min-w-[1050px] table-auto text-left text-sm"><thead><tr className="border-b text-muted-foreground"><th className="whitespace-nowrap p-2">Data liquidazione</th><th className="p-2">Ufficio / tipo documento</th><th className="p-2">Doc.</th><th className="p-2">Ordinativo</th><th className="whitespace-nowrap p-2 text-right">Importo</th><th className="whitespace-nowrap p-2 text-right">IVA / ritenute</th><th className="whitespace-nowrap p-2 text-right">Pagato</th><th className="whitespace-nowrap p-2 text-right">Saldo</th><th className="p-2">Stato</th><th className="p-2">Esito match</th></tr></thead><tbody>{visibleRows.map((r) => <tr id={`statement-row-${r.id}`} key={r.id} className={`border-b align-top ${targetDocument && (r.document_number === targetDocument || r.invoice_number === targetDocument) ? "bg-amber-100 ring-2 ring-inset ring-amber-500" : ""}`}><td className="whitespace-nowrap p-2">{r.row_date || r.liquidated || "—"}</td><td className="p-2">{r.office_document_type || "—"}</td><td className="p-2 font-medium">{r.document_number}</td><td className="p-2">{r.order_number || "—"}</td><td className="whitespace-nowrap p-2 text-right">{eur(r.amount)}</td><td className="whitespace-nowrap p-2 text-right">{eur(r.vat_withholdings)}</td><td className="whitespace-nowrap p-2 text-right">{eur(r.paid)}</td><td className="whitespace-nowrap p-2 text-right">{eur(r.balance)}</td><td className="p-2">{r.status || "—"}</td><td className="min-w-48 p-2"><div className="flex items-center gap-1">{r.match_status === "ABBINATA_INCASSATA" ? <CheckCircle2 className="size-4 shrink-0 text-emerald-600"/> : <AlertTriangle className="size-4 shrink-0 text-amber-600"/>}<span className="text-xs">{r.match_status.replaceAll("_", " ")}{r.invoice_number ? ` · Fattura ${r.invoice_number}` : ""}</span></div>{r.match_note && <p className="mt-1 max-w-64 text-xs text-muted-foreground">{r.match_note}</p>}</td></tr>)}{visibleRows.length === 0 && <tr><td colSpan={10} className="p-8 text-center text-muted-foreground">Nessuna riga corrispondente alla ricerca.</td></tr>}</tbody></table></div>
      </>}
    </section>
  </main>;
}


function AuthedPdfFrame({ path }: { path: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let current: string | null = null; let cancelled = false;
    setUrl(null); setFailed(false);
    apiBlobUrl(path).then((u) => { if (cancelled) URL.revokeObjectURL(u); else { current = u; setUrl(u); } }).catch(() => setFailed(true));
    return () => { cancelled = true; if (current) URL.revokeObjectURL(current); };
  }, [path]);
  if (failed) return <p className="p-4 text-sm text-muted-foreground">Anteprima non disponibile.</p>;
  if (!url) return <p className="p-4 text-sm text-muted-foreground">Caricamento anteprima…</p>;
  return <iframe title="Anteprima PDF estratto conto" src={url} className="h-[420px] w-full"/>;
}
