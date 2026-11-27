import { apiGet } from "./api";
export interface GlobalSearchResults { orders:Array<{id:number;order_number:string;order_date?:string;customer:string}>; customers:Array<{id:number;name:string;vat_number?:string|null}>; products:Array<{id:number;supplier_product_code:string;description?:string|null}> }
export function globalSearch(q:string){ return apiGet<GlobalSearchResults>("/api/search", {q}); }
