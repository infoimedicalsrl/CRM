const currencyFormatter = new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const numberFormatter = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 2 });

export function formatCurrency(value?: number | null): string {
  return `€ ${currencyFormatter.format(typeof value === "number" && isFinite(value) ? value : 0)}`;
}

export function formatNumber(value?: number | null): string {
  return numberFormatter.format(typeof value === "number" && isFinite(value) ? value : 0);
}

export function formatPercent(value?: number | null, fractionDigits = 1): string {
  const n = typeof value === "number" && isFinite(value) ? value : 0;
  return `${new Intl.NumberFormat("it-IT", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(n)}%`;
}

/** dd/MM/yyyy */
export function formatDate(value?: string | Date | null): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return typeof value === "string" ? value : "—";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

export function formatDateTime(value?: string | Date | null): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return typeof value === "string" ? value : "—";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
