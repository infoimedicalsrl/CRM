from __future__ import annotations

import csv
from io import BytesIO, StringIO
from typing import Iterable, Sequence

from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Font


def export_response(filename: str, headers: Sequence[str], rows: Iterable[Sequence[object]], fmt: str) -> Response:
    safe_rows = [["" if value is None else value for value in row] for row in rows]
    if fmt == "csv":
        stream = StringIO(newline="")
        writer = csv.writer(stream, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        writer.writerows(safe_rows)
        data = ("\ufeff" + stream.getvalue()).encode("utf-8")
        return Response(
            content=data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "Dati"
    ws.append(list(headers))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in safe_rows:
        ws.append(list(row))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for column in ws.columns:
        width = min(max(len(str(cell.value or "")) for cell in column) + 2, 60)
        ws.column_dimensions[column[0].column_letter].width = max(width, 12)
    output = BytesIO()
    wb.save(output)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
    )
