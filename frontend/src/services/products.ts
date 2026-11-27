import { apiGet } from "./api";
import type { Product } from "@/types";

export interface ProductsFilters { search?: string; }
interface RawProduct { id:number; supplier_product_code:string; description?:string|null; quantity:number; orders:number; customers:number; net:number; vat:number; gross:number; zero_value_quantity:number; }
export async function getProducts(filters?: ProductsFilters): Promise<Product[]> {
  const rows = await apiGet<RawProduct[]>("/api/products", { search: filters?.search });
  return rows.map((p) => ({ id:p.id, supplier_product_code:p.supplier_product_code, description:p.description, quantity_ordered:Number(p.quantity), orders_count:p.orders, customers_count:p.customers, net_revenue:Number(p.net), vat_amount:Number(p.vat), gross_revenue:Number(p.gross), zero_value_quantity:Number(p.zero_value_quantity) }));
}

export interface ProductDetail extends Product {
  average_price?: number;
  by_customer: Array<{ customer_id:number; customer:string; vat_number?:string|null; unit_code?:string|null; quantity:number; orders:number; net:number }>;
  trend: Array<{ order_date:string; unit_code?:string|null; quantity:number; net:number; average_price:number }>;
  recent_orders: Array<{order_id:number;order_number:string;order_date:string;customer:string;quantity:number;unit_code?:string|null;unit_price:number;line_net:number}>;
}
interface RawProductDetail { id:number; supplier_product_code:string; description?:string|null; summary:{quantity:number;net:number;vat:number;gross:number;orders:number;customers:number;zero_value_quantity:number;average_price:number}; by_customer:ProductDetail["by_customer"]; trend:ProductDetail["trend"]; recent_orders?:ProductDetail["recent_orders"]; }
export async function getProduct(id: string): Promise<ProductDetail> {
  const p = await apiGet<RawProductDetail>(`/api/products/${encodeURIComponent(id)}`);
  return { id:p.id, supplier_product_code:p.supplier_product_code, description:p.description, quantity_ordered:Number(p.summary.quantity), net_revenue:Number(p.summary.net), vat_amount:Number(p.summary.vat), gross_revenue:Number(p.summary.gross), orders_count:p.summary.orders, customers_count:p.summary.customers, zero_value_quantity:Number(p.summary.zero_value_quantity), average_price:Number(p.summary.average_price), by_customer:p.by_customer.map(x=>({...x,quantity:Number(x.quantity),net:Number(x.net)})), trend:p.trend.map(x=>({...x,quantity:Number(x.quantity),net:Number(x.net),average_price:Number(x.average_price)})), recent_orders:(p.recent_orders??[]).map(x=>({...x,quantity:Number(x.quantity),unit_price:Number(x.unit_price),line_net:Number(x.line_net)})) };
}


export interface ProductCodeVariantGroup {
  product_id:number; canonical_code:string; description?:string|null;
  variants:Array<{code:string;occurrences:number;first_seen_at?:string|null;last_seen_at?:string|null}>;
}
export function getProductCodeVariants(): Promise<ProductCodeVariantGroup[]> {
  return apiGet<ProductCodeVariantGroup[]>("/api/products/code-variants");
}
