import { apiDelete, apiGet, apiPatch, apiPostForm, type QueryParams } from "./api";
import type { DDTDetail, DDTListItem } from "@/types";

export interface DDTFilters { search?:string; customerId?:string; from?:string; to?:string; status?:string; }
function params(f?:DDTFilters):QueryParams{return {search:f?.search,customer_id:f?.customerId,date_from:f?.from,date_to:f?.to,status:f?.status};}
export function getDDTs(filters?:DDTFilters){return apiGet<DDTListItem[]>("/api/ddts",params(filters));}
export function getDDT(id:string){return apiGet<DDTDetail>(`/api/ddts/${encodeURIComponent(id)}`);}
export const ddtPdfPath=(id:string|number)=>`/api/ddts/${encodeURIComponent(String(id))}/pdf`;
export function uploadDDT(file:File){const fd=new FormData();fd.append("file",file);return apiPostForm<{status:string;ddt_id:number;ddt_number:string;line_count:number;warnings:string[]}>("/api/ddts/upload",fd);}
export function getDDTSuggestions(id:string){return apiGet<Array<{id:number;order_number:string;order_date?:string|null;customer_id:number;match_products:number;reference_match?:boolean;score:number}>>(`/api/ddts/${encodeURIComponent(id)}/suggestions`);}
export interface DDTUpdatePayload {ddt_number?:string;ddt_date?:string;customer_id?:number;order_id?:number|null;lines?:Array<{id:number;supplier_product_code?:string;description?:string;quantity?:number;unit_code?:string;lot_number?:string;expiry_date?:string;is_gift?:boolean}>;}
export function updateDDT(id:string|number,payload:DDTUpdatePayload){return apiPatch<DDTDetail>(`/api/ddts/${encodeURIComponent(String(id))}`,payload);}
export function linkDDT(id:string|number,orderId:number|null){return apiPatch<DDTDetail>(`/api/ddts/${encodeURIComponent(String(id))}/link`,{order_id:orderId});}
export function markDDTLineGift(ddtId:string|number,lineId:string|number,isGift:boolean){return apiPatch<DDTDetail>(`/api/ddts/${encodeURIComponent(String(ddtId))}/lines/${encodeURIComponent(String(lineId))}/gift`,{is_gift:isGift});}
export function deleteDDT(id:string|number){return apiDelete<{status:string;id:number}>(`/api/ddts/${encodeURIComponent(String(id))}`);}
export function exportDDTs(format:"xlsx"|"csv"="xlsx"){return apiGet("/api/exports/ddts",{format});}

export interface DDTManualOrder {
  id:number; order_number:string; order_date?:string|null; customer_id:number; customer_name:string; customer_vat?:string|null; reference_match:boolean; same_customer?:boolean;
}
export function searchDDTOrders(id:string|number, search?:string){
  return apiGet<DDTManualOrder[]>(`/api/ddts/${encodeURIComponent(String(id))}/orders`,{search});
}
