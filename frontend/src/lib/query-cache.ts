import { QueryClient, keepPreviousData } from "@tanstack/react-query";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";

export const CACHE_KEY = "peppol-query-cache";
export const CACHE_USER_KEY = "peppol-cache-user";
export const CACHE_MAX_AGE = 12 * 60 * 60 * 1000; // 12 ore

// Stale-while-revalidate: si mostrano subito gli ultimi dati noti e si aggiornano in background.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: 30_000,          // entro 30 s non si richiede di nuovo al server
      gcTime: CACHE_MAX_AGE,      // la cache resta in memoria (e su disco) fino a 12 ore
      placeholderData: keepPreviousData, // cambiando filtri la tabella non si svuota
      refetchOnWindowFocus: true, // tornando sulla scheda i dati si riallineano in background
    },
  },
});

export const queryPersister = createSyncStoragePersister({
  storage: typeof window !== "undefined" ? window.localStorage : undefined,
  key: CACHE_KEY,
  throttleTime: 1000,
});

/** Svuota cache in memoria e su disco (logout o cambio utente). */
export function clearQueryCache() {
  queryClient.clear();
  try {
    window.localStorage.removeItem(CACHE_KEY);
    window.localStorage.removeItem(CACHE_USER_KEY);
  } catch { /* storage non disponibile */ }
}
