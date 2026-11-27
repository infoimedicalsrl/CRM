import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { apiDownload, humanizeError, type QueryParams } from "@/services/api";

export function ExportMenu({ path, params }: { path: string; params?: QueryParams }) {
  const run = async (format: "csv" | "xlsx") => {
    try { await apiDownload(path, { ...params, format }); }
    catch (error) { toast.error(humanizeError(error)); }
  };
  return <DropdownMenu>
    <DropdownMenuTrigger asChild><Button variant="outline"><Download className="size-4"/>Esporta</Button></DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <DropdownMenuItem onClick={() => run("xlsx")}><FileSpreadsheet className="size-4"/>Excel (.xlsx)</DropdownMenuItem>
      <DropdownMenuItem onClick={() => run("csv")}><FileText className="size-4"/>CSV</DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>;
}
