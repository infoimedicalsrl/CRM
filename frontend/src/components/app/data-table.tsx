import { useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, LoadingSkeleton } from "./states";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number;
  align?: "left" | "right";
  className?: string;
  headerHint?: string;
}

export function DataTable<T>({
  columns,
  rows,
  isLoading,
  isError,
  errorMessage,
  onRetry,
  onRowClick,
  emptyTitle = "Nessun dato disponibile",
  emptyDescription,
  emptyAction,
  defaultSortKey,
  defaultSortDir = "desc",
  getRowId,
}: {
  columns: DataTableColumn<T>[];
  rows: T[] | undefined;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  onRowClick?: (row: T) => void;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  defaultSortKey?: string;
  defaultSortDir?: "asc" | "desc";
  getRowId?: (row: T, index: number) => string;
}) {
  const [sortKey, setSortKey] = useState<string | undefined>(defaultSortKey);
  const [sortDir, setSortDir] = useState<"asc" | "desc">(defaultSortDir);

  const sortedRows = useMemo(() => {
    if (!rows) return [];
    const column = columns.find((c) => c.key === sortKey);
    if (!column?.sortValue) return rows;
    const factor = sortDir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = column.sortValue!(a);
      const bv = column.sortValue!(b);
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * factor;
      return String(av).localeCompare(String(bv), "it") * factor;
    });
  }, [rows, columns, sortKey, sortDir]);

  if (isLoading) return <LoadingSkeleton rows={6} />;
  if (isError) return <ErrorState message={errorMessage} onRetry={onRetry} />;
  if (!rows || rows.length === 0)
    return <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />;

  return (
    <div className="w-full overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            {columns.map((column) => {
              const sortable = Boolean(column.sortValue);
              const active = sortKey === column.key;
              return (
                <TableHead
                  key={column.key}
                  className={cn(
                    "whitespace-nowrap text-xs uppercase tracking-wide",
                    column.align === "right" && "text-right",
                    column.className,
                  )}
                >
                  {sortable ? (
                    <button
                      type="button"
                      className={cn(
                        "inline-flex items-center gap-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        column.align === "right" && "flex-row-reverse",
                        active && "text-foreground",
                      )}
                      onClick={() => {
                        if (active) setSortDir(sortDir === "asc" ? "desc" : "asc");
                        else {
                          setSortKey(column.key);
                          setSortDir("desc");
                        }
                      }}
                      aria-label={`Ordina per ${column.header}`}
                    >
                      {column.header}
                      {active ? (
                        sortDir === "asc" ? (
                          <ArrowUp className="size-3" aria-hidden />
                        ) : (
                          <ArrowDown className="size-3" aria-hidden />
                        )
                      ) : (
                        <ChevronsUpDown className="size-3 opacity-40" aria-hidden />
                      )}
                    </button>
                  ) : (
                    column.header
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedRows.map((row, index) => (
            <TableRow
              key={getRowId?.(row, index) ?? index}
              className={cn(onRowClick && "cursor-pointer")}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={() => onRowClick?.(row)}
              onKeyDown={(event) => {
                if (onRowClick && event.key === "Enter") onRowClick(row);
              }}
            >
              {columns.map((column) => (
                <TableCell
                  key={column.key}
                  className={cn(
                    "whitespace-nowrap",
                    column.align === "right" && "text-right tabular-nums",
                    column.className,
                  )}
                >
                  {column.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
