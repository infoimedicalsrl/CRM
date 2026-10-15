import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getCustomers } from "@/services/customers";
import { updateOrder, type OrderUpdatePayload } from "@/services/orders";
import { humanizeError } from "@/services/api";
import type { Order, OrderLine } from "@/types";

interface EditableLine extends OrderLine {
  quantity: number;
  unit_price: number;
  vat_rate: number;
}

export function OrderEditDialog({
  order,
  open,
  onOpenChange,
  onSaved,
}: {
  order: Order;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: () => void;
}) {
  const queryClient = useQueryClient();
  const customers = useQuery({ queryKey: ["customers"], queryFn: () => getCustomers(), staleTime: 60_000 });
  const [number, setNumber] = useState(order.order_number);
  const [date, setDate] = useState(order.order_date ?? "");
  const [customerId, setCustomerId] = useState(String(order.customer_id ?? ""));
  const [lines, setLines] = useState<EditableLine[]>([]);

  useEffect(() => {
    if (!open) return;
    setNumber(order.order_number);
    setDate(order.order_date ?? "");
    setCustomerId(String(order.customer_id ?? ""));
    setLines((order.lines ?? []).map((line) => ({
      ...line,
      quantity: Number(line.quantity ?? 0),
      unit_price: Number(line.unit_price ?? 0),
      vat_rate: Number(line.vat_rate ?? 0),
    })));
  }, [open, order]);

  const mutation = useMutation({
    mutationFn: (payload: OrderUpdatePayload) => updateOrder(order.id, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["products"] }),
        queryClient.invalidateQueries({ queryKey: ["customers"] }),
        queryClient.invalidateQueries({ queryKey: ["analytics"] }),
      ]);
      onOpenChange(false);
      onSaved?.();
    },
  });

  function patchLine(index: number, patch: Partial<EditableLine>) {
    setLines((current) => current.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  function save() {
    mutation.mutate({
      order_number: number.trim(),
      order_date: date,
      customer_id: Number(customerId),
      lines: lines.map((line) => ({
        id: Number(line.id),
        line_number: line.line_number,
        supplier_product_code: line.supplier_product_code,
        description: line.description,
        quantity: Number(line.quantity),
        unit_code: line.unit ?? "PZ",
        unit_price: Number(line.unit_price),
        vat_category: line.vat_category,
        vat_rate: Number(line.vat_rate),
      })),
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-5xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Modifica ordine</DialogTitle>
          <DialogDescription>
            Le modifiche agiscono sui dati salvati. Il documento originale importato non viene modificato.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="edit-order-number">Numero ordine</Label>
            <Input id="edit-order-number" value={number} onChange={(e) => setNumber(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-order-date">Data</Label>
            <Input id="edit-order-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-order-customer">Cliente</Label>
            <select
              id="edit-order-customer"
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
            >
              {(customers.data ?? []).map((customer) => (
                <option key={customer.id} value={customer.id}>{customer.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <h3 className="font-semibold">Righe ordine</h3>
            <p className="text-xs text-muted-foreground">C62 e PZ vengono trattati entrambi come PZ.</p>
          </div>
          <div className="space-y-3">
            {lines.map((line, index) => (
              <div key={line.id ?? index} className="grid gap-3 rounded-lg border p-3 md:grid-cols-12">
                <div className="space-y-1 md:col-span-2">
                  <Label className="text-xs">Codice</Label>
                  <Input value={line.supplier_product_code} onChange={(e) => patchLine(index, { supplier_product_code: e.target.value })} />
                </div>
                <div className="space-y-1 md:col-span-4">
                  <Label className="text-xs">Descrizione</Label>
                  <Input value={line.description ?? ""} onChange={(e) => patchLine(index, { description: e.target.value })} />
                </div>
                <div className="space-y-1 md:col-span-2">
                  <Label className="text-xs">Quantità</Label>
                  <Input type="number" step="0.0001" min="0" value={line.quantity} onChange={(e) => patchLine(index, { quantity: Number(e.target.value) })} />
                </div>
                <div className="space-y-1 md:col-span-1">
                  <Label className="text-xs">UM</Label>
                  <Input value={(line.unit ?? "PZ").toUpperCase() === "C62" ? "PZ" : (line.unit ?? "PZ")} onChange={(e) => patchLine(index, { unit: e.target.value })} />
                </div>
                <div className="space-y-1 md:col-span-2">
                  <Label className="text-xs">Prezzo unitario</Label>
                  <Input type="number" step="0.00001" min="0" value={line.unit_price} onChange={(e) => patchLine(index, { unit_price: Number(e.target.value) })} />
                </div>
                <div className="space-y-1 md:col-span-1">
                  <Label className="text-xs">IVA %</Label>
                  <Input type="number" step="0.01" min="0" value={line.vat_rate} onChange={(e) => patchLine(index, { vat_rate: Number(e.target.value) })} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {mutation.isError && <p className="text-sm text-destructive">{humanizeError(mutation.error)}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={save} disabled={mutation.isPending || !number.trim() || !date || !customerId}>
            <Save className="size-4" />
            {mutation.isPending ? "Salvataggio…" : "Salva modifiche"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
