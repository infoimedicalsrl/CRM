import { apiDelete, apiGet, apiPatch, apiPost, type QueryParams } from "./api";
import type { Order } from "@/types";

export interface OrdersFilters { search?: string; customerId?: string; from?: string; to?: string; }
interface RawOrder { id:number; order_number:string; order_date?:string|null; customer_id?:number; customer?:string; customer_vat?:string|null; currency?:string|null; total_net:number; total_vat:number; total_gross:number; }
interface RawDeliveryLine { order_line_id:number; product_id:number; supplier_product_code:string; description?:string|null; unit_code?:string|null; ordered_quantity:number; delivered_quantity:number; ddt_delivered_quantity?:number; manual_delivered_quantity?:number|null; residual_quantity:number; over_quantity:number; status:string }
interface RawDelivery { status:string; ordered_quantity:number; delivered_quantity:number; residual_quantity:number; over_quantity?:number; lines:RawDeliveryLine[]; ddts:Array<{id:number;number:string;date?:string|null;quantity:number;status:string}> }
interface RawDetail extends Omit<RawOrder, "customer"> { delivery:RawDelivery; customer:{id:number;name:string;vat_number?:string|null;peppol_endpoint?:string|null}; source_filename?:string|null; lines:Array<{id:number;product_id:number;line_number?:string|null;supplier_product_code:string;description?:string|null;quantity:number;unit_code?:string|null;unit_price:number;line_net:number;vat_category?:string|null;vat_rate:number;line_vat:number;line_gross:number;is_zero_value:boolean}> }

function toParams(filters?: OrdersFilters): QueryParams {
  return { search: filters?.search, customer_id: filters?.customerId, date_from: filters?.from, date_to: filters?.to };
}

export async function getOrders(filters?: OrdersFilters): Promise<Order[]> {
  const data = await apiGet<RawOrder[]>("/api/orders", toParams(filters));
  return data.map((o) => ({ id:o.id, order_number:o.order_number, order_date:o.order_date, customer_id:o.customer_id, customer_name:o.customer, customer_vat:o.customer_vat, currency:o.currency, net_amount:Number(o.total_net), vat_amount:Number(o.total_vat), total_amount:Number(o.total_gross) }));
}

export async function getOrder(id: string): Promise<Order> {
  const o = await apiGet<RawDetail>(`/api/orders/${encodeURIComponent(id)}`);
  return {
    id:o.id, order_number:o.order_number, order_date:o.order_date, customer_id:o.customer.id, customer_name:o.customer.name, customer_vat:o.customer.vat_number,
    customer:o.customer, currency:o.currency, net_amount:Number(o.total_net), vat_amount:Number(o.total_vat), total_amount:Number(o.total_gross), source_file:o.source_filename,
    delivery:o.delivery,
    lines:o.lines.map((l) => ({ id:l.id, product_id:l.product_id, line_number:l.line_number, supplier_product_code:l.supplier_product_code, description:l.description, quantity:Number(l.quantity), unit:l.unit_code, unit_price:Number(l.unit_price), line_net:Number(l.line_net), vat_category:l.vat_category, vat_rate:Number(l.vat_rate), vat_amount:Number(l.line_vat), line_total:Number(l.line_gross), is_zero_value:l.is_zero_value }))
  };
}


export interface OrderLineUpdatePayload {
  id: number;
  line_number?: string | null;
  supplier_product_code?: string;
  description?: string | null;
  quantity?: number;
  unit_code?: string | null;
  unit_price?: number;
  vat_category?: string | null;
  vat_rate?: number;
}

export interface OrderUpdatePayload {
  order_number?: string;
  order_date?: string;
  customer_id?: number;
  lines?: OrderLineUpdatePayload[];
}

export function updateOrder(id: string | number, payload: OrderUpdatePayload): Promise<Order> {
  return apiPatch<Order>(`/api/orders/${encodeURIComponent(String(id))}`, payload);
}

export function deleteOrder(id: string | number) {
  return apiDelete<{ status: string; id: number }>(`/api/orders/${encodeURIComponent(String(id))}`);
}

export interface RestorePreview { available:boolean;source_file:string;current:unknown;original:{order_number:string;order_date:string;customer_name:string;customer_vat:string;total_net:number;total_vat:number;total_gross:number;lines:Array<{line_number:string;supplier_product_code:string;description?:string|null;quantity:number;unit_code?:string|null;unit_price:number;vat_rate:number}>}; }
export function getRestorePreview(id:string|number){ return apiGet<RestorePreview>(`/api/orders/${encodeURIComponent(String(id))}/restore-preview`); }
export function restoreOrder(id:string|number){ return apiPost<{status:string;order_id:number;order_number:string}>(`/api/orders/${encodeURIComponent(String(id))}/restore`); }


export function updateOrderDeliveryLine(orderId:string|number, orderLineId:number, deliveredQuantity:number|null){
  return apiPatch<Order>(`/api/orders/${encodeURIComponent(String(orderId))}/delivery-lines/${encodeURIComponent(String(orderLineId))}`, {delivered_quantity: deliveredQuantity});
}
