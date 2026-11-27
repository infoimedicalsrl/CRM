import { apiGet, apiPatch } from "./api";
import type { Customer, Order, Product } from "@/types";

export interface CustomersFilters { search?: string; }
interface RawCustomer { id:number; name:string; vat_number?:string|null; peppol_endpoint?:string|null; orders:number; products:number; quantity:number; net:number; gross:number; }
export async function getCustomers(filters?: CustomersFilters): Promise<Customer[]> {
  const rows = await apiGet<RawCustomer[]>("/api/customers", { search: filters?.search });
  return rows.map((c) => ({ id:c.id, name:c.name, vat_number:c.vat_number, peppol_endpoint:c.peppol_endpoint, orders_count:c.orders, products_count:c.products, total_quantity:Number(c.quantity), net_revenue:Number(c.net), gross_revenue:Number(c.gross) }));
}

export interface CustomerDetail extends Customer {
  vat_amount?: number;
  average_order_value?: number;
  products: Array<Product & { quantity_ordered:number; unit?:string|null }>;
  orders: Order[];
  trend: Array<{period:string;net:number;orders:number}>;
  last_order?: {id:number;order_number:string;order_date?:string|null;total_gross:number}|null;
}
interface RawCustomerDetail { id:number; name:string; vat_number?:string|null; peppol_endpoint?:string|null; summary:{orders:number;products:number;net:number;vat:number;gross:number;average_order:number}; trend?:Array<{period:string;net:number;orders:number}>; last_order?:{id:number;order_number:string;order_date?:string|null;total_gross:number}|null; products:Array<{product_id:number;supplier_product_code:string;description?:string|null;unit_code?:string|null;quantity:number;orders:number;net:number}>; orders:Array<{id:number;order_number:string;order_date?:string|null;total_net:number;total_vat:number;total_gross:number}> }
export async function getCustomer(id: string): Promise<CustomerDetail> {
  const c = await apiGet<RawCustomerDetail>(`/api/customers/${encodeURIComponent(id)}`);
  return { id:c.id,name:c.name,vat_number:c.vat_number,peppol_endpoint:c.peppol_endpoint,orders_count:c.summary.orders,products_count:c.summary.products,net_revenue:Number(c.summary.net),vat_amount:Number(c.summary.vat),gross_revenue:Number(c.summary.gross),average_order_value:Number(c.summary.average_order),trend:(c.trend??[]).map(x=>({...x,net:Number(x.net),orders:Number(x.orders)})),last_order:c.last_order?{...c.last_order,total_gross:Number(c.last_order.total_gross)}:null,products:c.products.map(p=>({id:p.product_id,supplier_product_code:p.supplier_product_code,description:p.description,quantity_ordered:Number(p.quantity),unit:p.unit_code,orders_count:p.orders,net_revenue:Number(p.net)})),orders:c.orders.map(o=>({id:o.id,order_number:o.order_number,order_date:o.order_date,net_amount:Number(o.total_net),vat_amount:Number(o.total_vat),total_amount:Number(o.total_gross)})) };
}
export function updateCustomerName(id: string | number, name: string) {
  return apiPatch<Customer>(`/api/customers/${encodeURIComponent(String(id))}`, { name });
}
