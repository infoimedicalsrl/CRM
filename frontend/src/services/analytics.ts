import { apiGet } from "./api";
import { filtersToParams } from "./dashboard";
import type { GlobalFilterState, ProductCustomerRow, ZeroValueLine } from "@/types";

interface RawProductCustomer { customer_id:number; customer:string; product_id:number; supplier_product_code:string; description?:string|null; unit_code?:string|null; quantity:number; net:number; }
export async function getProductCustomerRows(filters?: GlobalFilterState): Promise<ProductCustomerRow[]> {
  const rows = await apiGet<RawProductCustomer[]>("/api/analytics/product-customer", filtersToParams(filters));
  return rows.map(r=>({...r,quantity:Number(r.quantity),net:Number(r.net)}));
}
interface RawZero { id:number; product_id:number;supplier_product_code:string;description?:string|null;customer_id:number;customer:string;order_id:number;order_number:string;order_date?:string|null;quantity:number;unit_code?:string|null; }
export async function getZeroValueLines(filters?: GlobalFilterState): Promise<ZeroValueLine[]> {
  const rows = await apiGet<RawZero[]>("/api/analytics/zero-value", filtersToParams(filters));
  return rows.map(r=>({id:r.id,product_id:r.product_id,supplier_product_code:r.supplier_product_code,description:r.description,customer_id:r.customer_id,customer_name:r.customer,order_id:r.order_id,order_number:r.order_number,order_date:r.order_date,quantity:Number(r.quantity),unit:r.unit_code}));
}
