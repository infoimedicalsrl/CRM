import { supabase } from "@/lib/supabase";

export const API_BASE_URL =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? window.location.origin;

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export type QueryParams = Record<string, string | number | undefined | null>;

export function buildApiUrl(path: string, params?: QueryParams) {
  const url = new URL(path.startsWith("/") ? path : `/${path}`, API_BASE_URL);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function parseBody(response: Response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Sessione scaduta/non valida: si torna alla schermata di login. */
async function handleUnauthorized(status: number) {
  if (status === 401) await supabase.auth.signOut();
}

async function request<T>(path: string, init?: RequestInit, params?: QueryParams): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildApiUrl(path, params), {
      ...init,
      headers: {
        Accept: "application/json",
        ...(await authHeaders()),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("Server non raggiungibile.", 0);
  }
  await handleUnauthorized(response.status);
  if (response.status === 413) throw new ApiError("File troppo grande: il limite per singolo file è circa 4 MB.", 413);

  const body = await parseBody(response);
  if (!response.ok) {
    throw new ApiError(extractMessage(body) ?? "Richiesta non riuscita.", response.status, body);
  }
  return body as T;
}

export function apiGet<T>(path: string, params?: QueryParams) {
  return request<T>(path, { method: "GET" }, params);
}

export function apiPost<T>(path: string, payload?: unknown) {
  return request<T>(path, { method: "POST", headers: payload !== undefined ? { "Content-Type": "application/json" } : undefined, body: payload !== undefined ? JSON.stringify(payload) : undefined });
}

export function apiPatch<T>(path: string, payload: unknown) {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function apiDelete<T>(path: string) {
  return request<T>(path, { method: "DELETE" });
}

export function apiPostForm<T>(path: string, formData: FormData) {
  return request<T>(path, { method: "POST", body: formData });
}

function extractMessage(body: unknown): string | null {
  if (typeof body === "string") return body;
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    for (const key of ["detail", "message", "error"]) {
      const value = record[key];
      if (typeof value === "string") return value;
    }
  }
  return null;
}

export function humanizeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return "Impossibile contattare il server.";
    if (error.status === 404) return "Risorsa non trovata.";
    // HTTP 409 è usato per più conflitti: si mostra il messaggio esatto del backend.
    if (error.message && !/traceback|file \"/i.test(error.message)) return error.message;
  }
  return "Impossibile recuperare i dati dal server.";
}


export async function apiDownload(path: string, params?: QueryParams): Promise<void> {
  let response: Response;
  try {
    response = await fetch(buildApiUrl(path, params), { headers: await authHeaders() });
  } catch {
    throw new ApiError("Server non raggiungibile.", 0);
  }
  await handleUnauthorized(response.status);
  if (!response.ok) {
    const body = await parseBody(response);
    throw new ApiError(extractMessage(body) ?? "Esportazione non riuscita.", response.status, body);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] ?? "export";
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
  URL.revokeObjectURL(url);
}


/** Scarica un file protetto (PDF/CSV) con il token e restituisce un URL temporaneo per il browser. */
export async function apiBlobUrl(path: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch(buildApiUrl(path), { headers: await authHeaders() });
  } catch {
    throw new ApiError("Server non raggiungibile.", 0);
  }
  await handleUnauthorized(response.status);
  if (!response.ok) {
    const body = await parseBody(response);
    throw new ApiError(extractMessage(body) ?? "Documento non disponibile.", response.status, body);
  }
  return URL.createObjectURL(await response.blob());
}

export async function apiOpenFile(path: string): Promise<void> {
  const url = await apiBlobUrl(path);
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export interface BulkUploadResult {
  total: number; success: number; duplicates: number; errors: number;
  items: Array<{ file: string; status: string; ddt_number?: string; message: string }>;
  message: string;
}

/**
 * Le funzioni serverless accettano richieste di circa 4 MB: i file vengono inviati a gruppi
 * sotto questa soglia (ognuno oltre soglia viaggia da solo) e gli esiti vengono uniti.
 */
export async function postFilesInBatches(path: string, files: File[], limitBytes = 3_500_000): Promise<BulkUploadResult> {
  const batches: File[][] = [];
  let current: File[] = []; let size = 0;
  for (const f of files) {
    if (current.length && size + f.size > limitBytes) { batches.push(current); current = []; size = 0; }
    current.push(f); size += f.size;
  }
  if (current.length) batches.push(current);
  const merged: BulkUploadResult = { total: 0, success: 0, duplicates: 0, errors: 0, items: [], message: "" };
  for (const batch of batches) {
    try {
      const fd = new FormData();
      batch.forEach((f) => fd.append("files", f));
      const r = await apiPostForm<Partial<BulkUploadResult>>(path, fd);
      merged.total += r.total ?? 0; merged.success += r.success ?? 0;
      merged.duplicates += r.duplicates ?? 0; merged.errors += r.errors ?? 0;
      merged.items.push(...(r.items ?? []));
    } catch (error) {
      for (const f of batch) merged.items.push({ file: f.name, status: "ERRORE", message: humanizeError(error) });
      merged.total += batch.length; merged.errors += batch.length;
    }
  }
  merged.message = `Elaborati ${merged.total} file: ${merged.success} importati, ${merged.duplicates} duplicati, ${merged.errors} errori.`;
  return merged;
}
