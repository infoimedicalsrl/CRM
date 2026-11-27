from __future__ import annotations

from decimal import Decimal
from .models import ParsedOrder

TOLERANCE = Decimal("0.02")


class OrderValidationError(ValueError):
    pass


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= TOLERANCE


def validate_order(order: ParsedOrder) -> list[str]:
    warnings: list[str] = []

    line_net_sum = sum((line.line_net for line in order.lines), Decimal("0"))
    line_vat_sum = sum((line.line_vat for line in order.lines), Decimal("0"))

    if not _close(line_net_sum, order.total_net):
        raise OrderValidationError(
            f"Somma imponibili righe {line_net_sum} diversa dal totale ordine {order.total_net}"
        )

    if not _close(order.total_net + order.total_vat, order.total_gross):
        raise OrderValidationError(
            f"Totali ordine incoerenti: {order.total_net} + {order.total_vat} != {order.total_gross}"
        )

    if not _close(line_vat_sum, order.total_vat):
        warnings.append(
            f"IVA calcolata dalle righe ({line_vat_sum}) diversa dall'IVA dichiarata ({order.total_vat}); possibile arrotondamento/gestione UBL avanzata"
        )

    for line in order.lines:
        expected = line.quantity * line.unit_price
        if not _close(expected, line.line_net):
            # Important: zero-value/allowance lines are valid and must not be dropped.
            warnings.append(
                f"Riga {line.line_number}: quantità×prezzo={expected} ma imponibile riga={line.line_net}"
            )

    return warnings
