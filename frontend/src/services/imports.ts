import { apiGet, apiPostForm } from "./api";
import type { ImportJob, ImportsResponse } from "@/types";
interface RawImport { id:number;filename:string;status:string;error_message?:string|null;warnings?:string|null;started_at?:string|null;completed_at?:string|null; }
export async function getImports(): Promise<ImportsResponse> {
  const rows = await apiGet<RawImport[]>("/api/imports");
  const items: ImportJob[] = rows.map(x=>({id:x.id,file_name:x.filename,status:x.status,created_at:x.started_at,completed_at:x.completed_at,message:x.error_message ?? x.warnings ?? undefined}));
  return {items,total:items.length,success:items.filter(x=>x.status==="SUCCESS").length,errors:items.filter(x=>x.status==="ERROR").length};
}
export function uploadImport(file: File) {
  const form = new FormData(); form.append("file", file);
  return apiPostForm<{status:string;order_id:number;order_number:string;warnings?:string[]}>("/api/imports/upload", form);
}

