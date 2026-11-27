import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Search, ReceiptText, Users, Boxes } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { globalSearch } from "@/services/search";

export function GlobalSearch(){
 const [open,setOpen]=useState(false); const [text,setText]=useState(""); const [q,setQ]=useState(""); const nav=useNavigate();
 useEffect(()=>{const t=setTimeout(()=>setQ(text.trim()),250);return()=>clearTimeout(t)},[text]);
 useEffect(()=>{const h=(e:KeyboardEvent)=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){e.preventDefault();setOpen(true)}};window.addEventListener("keydown",h);return()=>window.removeEventListener("keydown",h)},[]);
 const query=useQuery({queryKey:["global-search",q],queryFn:()=>globalSearch(q),enabled:q.length>=2,retry:false});
 const go=(to:string,params?:Record<string,string>)=>{setOpen(false);setText(""); nav({to,params} as any)};
 return <><Button variant="outline" size="sm" onClick={()=>setOpen(true)} className="hidden min-w-40 justify-start text-muted-foreground sm:flex"><Search className="size-4"/>Cerca…<span className="ml-auto text-xs">⌘K</span></Button>
 <Dialog open={open} onOpenChange={setOpen}><DialogContent className="max-w-2xl"><DialogHeader><DialogTitle>Ricerca globale</DialogTitle></DialogHeader><Input autoFocus value={text} onChange={e=>setText(e.target.value)} placeholder="Ordine, cliente, P.IVA, codice o descrizione prodotto…" />
 <div className="max-h-[55vh] space-y-5 overflow-auto pt-2">{q.length<2?<p className="text-sm text-muted-foreground">Inserisci almeno 2 caratteri.</p>:query.isLoading?<p className="text-sm text-muted-foreground">Ricerca…</p>:query.data&&<>
 <Section icon={ReceiptText} title="Ordini">{query.data.orders.map(x=><button key={x.id} onClick={()=>go('/orders/$id',{id:String(x.id)})} className="block w-full rounded-md px-3 py-2 text-left hover:bg-accent"><b>{x.order_number}</b><span className="ml-2 text-sm text-muted-foreground">{x.customer}</span></button>)}</Section>
 <Section icon={Users} title="Clienti">{query.data.customers.map(x=><button key={x.id} onClick={()=>go('/customers/$id',{id:String(x.id)})} className="block w-full rounded-md px-3 py-2 text-left hover:bg-accent"><b>{x.name}</b><span className="ml-2 text-sm text-muted-foreground">{x.vat_number}</span></button>)}</Section>
 <Section icon={Boxes} title="Prodotti">{query.data.products.map(x=><button key={x.id} onClick={()=>go('/products/$id',{id:x.supplier_product_code})} className="block w-full rounded-md px-3 py-2 text-left hover:bg-accent"><b>{x.supplier_product_code}</b><div className="text-sm text-muted-foreground">{x.description}</div></button>)}</Section>
 {query.data.orders.length+query.data.customers.length+query.data.products.length===0&&<p className="text-sm text-muted-foreground">Nessun risultato.</p>}</>}</div></DialogContent></Dialog></>;
}
function Section({icon:Icon,title,children}:{icon:any;title:string;children:any}){return <div><div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground"><Icon className="size-4"/>{title}</div>{children}</div>}
