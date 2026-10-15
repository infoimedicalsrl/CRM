"""Parser locale per estratti conto BPER aziendali in PDF testuale.

Legge le colonne DATA, VALUTA, USCITE, INGRESSO e DESCRIZIONE senza usare
servizi esterni. Gli importi di fattura dentro la descrizione non sono mai
usati come importi bancari quando le colonne sono identificabili.
"""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from pypdf import PdfReader

_DATE_TOKEN = r"(?:\d{2}[./-]\d{2}[./-](?:\d{2}|\d{4})|\d{4}-\d{2}-\d{2})"
DATE_RE = re.compile(rf"^\s*({_DATE_TOKEN})(?:\s+({_DATE_TOKEN}))?\s+(.*)$")
MONEY_RE = re.compile(r"(?<![\w/])[+＋\-−]?\s*(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{2})(?:\s*[-−])?(?!\w)")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30}\b")


def parse_date(value: str) -> date:
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value): return date.fromisoformat(value)
    value = value.replace(".", "/").replace("-", "/")
    day, month, year = value.split("/")
    if len(year) == 2: year = ("20" if int(year) <= 79 else "19") + year
    return date(int(year), int(month), int(day))


def money(value: str) -> Decimal:
    value = value.strip().replace("−", "-").replace(" ", "")
    trailing_minus = value.endswith("-")
    value = value.rstrip("-").replace(".", "").replace(",", ".")
    negative = value.startswith("-") or trailing_minus
    value = value.lstrip("+-")
    result = Decimal(value)
    return -abs(result) if negative else result


def extract_description_details(description: str) -> dict[str, Any]:
    """Estrae dati utili dalla causale senza confonderli con il movimento bancario."""
    text = re.sub(r"\s+", " ", description).strip()
    beneficiary = None

    # Commissioni e canoni bancari: la controparte è sempre Bper.
    bper_patterns = (
        r"COMM\.?\s*BON\.?\s*ISTANTANEO",
        r"COMPETENZE\s+SPESE\s+ED\s+ONERI",
        r"CANONE\s+SERVIZI\s+TELEMATICI\s+ADD\.?\s*CANONE\s+CORPORATE\s+BANKING",
    )
    if any(re.search(pattern, text, re.I) for pattern in bper_patterns):
        beneficiary = "Bper"
    else:
        # Bonifico istantaneo: la controparte è esattamente il testo tra
        # "a favore di" e il token EUR, tollerando due punti/virgole dopo EUR.
        m_special = re.search(
            r"\bDISPOSIZIONE\s+BONIFICO\s+ISTANTANEO\b.*?\ba\s+favore\s+di\s*(.+?)\s+EUR(?=\b|\s|:)",
            text, re.I,
        )
        if m_special:
            beneficiary = m_special.group(1).strip(" \t,;:-")[:255] or None
        else:
            # BONIFICO o/c: testo tra ':' e 'ABI-CAB:'.
            m_special = re.search(
                r"BONIFICO\s+o/c\s*:\s*(.+?)\s+ABI\s*[-–]?\s*CAB\s*:", text, re.I,
            )
            if m_special:
                beneficiary = m_special.group(1).strip(" ,;:-")[:255] or None
            else:
                # Addebito B2B: nominativo prima della forma societaria "S P A N".
                m_special = re.search(r"ADDEBITO\s+B2B\s+(.+?)\s+S\s+P\s+A\s+N\b", text, re.I)
                if m_special:
                    beneficiary = m_special.group(1).strip(" ,;:-")[:255] or None
                else:
                    # Pagamento internazionale: isoliamo prima il testo del negozio,
                    # escludendo la coda tecnica Operazione carta / numero carta / data.
                    m_head = re.search(
                        r"PAGAMENTO\s+SU\s+CIRCUITO\s+INTERNAZIONALE\s+(.+?)(?=\s+Operazione\s+carta\b|$)",
                        text, re.I,
                    )
                    if m_head:
                        merchant_area = m_head.group(1).strip()
                        # La città è il testo finale prima di ITA (es. CATANIA ITA,
                        # GRAVINA DI CT ITA, ROMA ITA). Usiamo un elenco esteso e
                        # prendiamo l'ultima corrispondenza, evitando di tagliare il negozio.
                        cities = (
                            r"GRAVINA\s+DI\s+CT|REGGIO\s+CALABRIA|SAN\s+GIOVANNI\s+LA\s+PUNTA|"
                            r"CALTANISSETTA|LAMEZIA\s+TERME|BOLZANO|CAMPOBASSO|FORLI|FORLÌ|LA\s+SPEZIA|"
                            r"CATANIA|ROMA|MILANO|PALERMO|MESSINA|SIRACUSA|ACIREALE|AGRIGENTO|TRAPANI|RAGUSA|ENNA|TAORMINA|"
                            r"BOLOGNA|FIRENZE|TORINO|NAPOLI|BARI|VERONA|VENEZIA|PADOVA|PISA|GENOVA|LECCE|PERUGIA|ANCONA|"
                            r"MODENA|PARMA|RIMINI|TRENTO|TRIESTE|CAGLIARI|OLBIA|SASSARI|CATANZARO|COSENZA|MONZA|BERGAMO|"
                            r"BRESCIA|COMO|VARESE|LIVORNO|LUCCA|AREZZO|SIENA|FERRARA|RAVENNA|SALERNO|CASERTA|TARANTO|"
                            r"BRINDISI|FOGGIA|POTENZA|MATERA|LONDON|PARIS|BERLIN|MADRID|BARCELONA"
                        )
                        city_matches = list(re.finditer(rf"\b(?:{cities})\s+(?=ITA\b)", merchant_area, re.I))
                        if city_matches:
                            beneficiary = merchant_area[:city_matches[-1].start()].strip(" ,;:-")[:255] or None
                        else:
                            # Fallback: se manca ITA ma compare la coda tecnica, elimina
                            # solo data/operazione; non inventa una città non riconosciuta.
                            beneficiary = merchant_area.strip(" ,;:-")[:255] or None

    m = None if beneficiary else re.search(r"\ba favore di\s+(.+?)(?=\s+(?:Num\.?\s*Bon\.?\s*Sepa|Bonifico|CIG\s*:|CUP\s*:|FATTURA\s+N\.?|FA\s+\d)|$)", text, re.I)
    if not beneficiary and not m:
        m = re.search(r"\b(?:beneficiario|ordinante)\s*[:\-]?\s*(.+?)(?=\s+(?:IBAN\b|CIG\s*:|CUP\s*:|FATTURA\s+N\.?|Num\.?\s*Bon\.?\s*Sepa)|$)", text, re.I)
    if not beneficiary and m:
        beneficiary = m.group(1).strip(" ,;:-")[:255] or None

    # Associa ogni fattura al CIG che segue nella stessa porzione di causale.
    invoices = []
    invoice_re = re.compile(r"\bFATTURA\s+N\.?\s*([\w./-]+(?:\s+[A-Z]{1,3})?)(.*?)(?=\bFATTURA\s+N\.?\s*[\w./-]+|$)", re.I)
    for im in invoice_re.finditer(text):
        segment = im.group(2)
        cig_match = re.search(r"(?<![A-Z])CIG\s*:\s*([A-Z0-9]+)", segment, re.I)
        invoices.append({"number": im.group(1).strip(), "cig": cig_match.group(1).upper() if cig_match else None})
    first_invoice = invoice_re.search(text)
    cig_matches = list(re.finditer(r"(?<![A-Z])CIG\s*:\s*([A-Z0-9]+)", text, re.I))
    if invoices and first_invoice:
        preceding = [m for m in cig_matches if m.start() < first_invoice.start()]
        if preceding:
            invoices[0]["cig"] = preceding[-1].group(1).upper()
    all_cigs = list(dict.fromkeys(m.group(1).upper() for m in cig_matches))
    linked = {x.get("cig") for x in invoices if x.get("cig")}
    for cig in all_cigs:
        if cig not in linked:
            invoices.append({"number": None, "cig": cig})
    invoice_amounts = [money(x) for x in re.findall(r"\bFA\s*((?:\d{1,3}(?:\.\d{3})+|\d+),\d{2})\s*EUR\b", text, re.I)]
    fees = [money(x) for x in re.findall(r"\bSpese\s*:\s*((?:\d{1,3}(?:\.\d{3})+|\d+),\d{2})\s*EUR\b", text, re.I)]
    return {"counterparty": beneficiary, "invoice_details": invoices, "invoice_amounts": invoice_amounts, "fees": fees,
            "cig_codes": all_cigs}


def _money_in_column(text: str) -> Decimal | None:
    vals = []
    for raw in MONEY_RE.findall(text):
        try: vals.append(money(raw))
        except (InvalidOperation, ValueError): pass
    # Le colonne BPER vuote sono spesso rappresentate da spazi o da trattini.
    nonzero = [v for v in vals if v != 0]
    return nonzero[-1] if len(nonzero) == 1 else (Decimal("0.00") if vals and all(v == 0 for v in vals) else None)


def _find_columns(lines: list[str]) -> dict[str, int] | None:
    # Modalità layout: le posizioni orizzontali dei titoli guidano la lettura delle colonne.
    aliases = {
        "booking": re.compile(r"\bDATA\b", re.I), "value": re.compile(r"\bVALUTA\b", re.I),
        "out": re.compile(r"\bUSCITE\b", re.I), "in": re.compile(r"\bINGRESSO\b|\bENTRATE\b", re.I),
        "description": re.compile(r"\bDESCRIZIONE\b|\bCAUSALE\b", re.I),
    }
    for line in lines:
        found = {}
        for key, pattern in aliases.items():
            m = pattern.search(line)
            if m: found[key] = m.start()
        if {"booking", "value", "out", "in", "description"}.issubset(found) and list(found.values()) == sorted(found.values()):
            return found
    return None


def _parse_lines(lines: list[str], column_positions: dict[str, int] | None = None) -> tuple[list[dict[str, Any]], Decimal | None, Decimal | None]:
    transactions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    opening_balance = closing_balance = None
    pending_balance_label: str | None = None
    positions = column_positions

    def finish():
        nonlocal current
        if current is not None:
            if current.get("amount") is not None: transactions.append(current)
            current = None

    for raw in lines:
        if not raw.strip(): continue
        # Conserva spazi per usare le coordinate approssimative delle colonne.
        layout_line = raw.rstrip("\n\r")
        line = re.sub(r"\s+", " ", raw).strip()
        low = line.casefold()
        if any(label in low for label in ("saldo iniziale", "saldo precedente", "saldo al", "saldo finale", "saldo contabile iniziale", "saldo contabile finale")):
            vals = [money(x) for x in MONEY_RE.findall(line)]
            if vals:
                if "iniziale" in low or "precedente" in low: opening_balance = vals[-1]
                elif "saldo al" in low or "saldo finale" in low: closing_balance = vals[-1]
                pending_balance_label = None
            else:
                pending_balance_label = "opening" if ("iniziale" in low or "precedente" in low) else "closing"
            continue
        if pending_balance_label:
            vals = [money(x) for x in MONEY_RE.findall(line)]
            if vals:
                if pending_balance_label == "opening": opening_balance = vals[-1]
                else: closing_balance = vals[-1]
                pending_balance_label = None
                continue
        match = DATE_RE.match(line)
        if match:
            finish()
            first_date, second_date, rest = match.groups()
            try:
                booked = parse_date(first_date)
                value_date = parse_date(second_date) if second_date else booked
            except (ValueError, TypeError): continue

            amount = None; direction = None; description = rest or ""
            if positions and len(layout_line) > positions["description"]:
                # Titoli nell'ordine DATA | VALUTA | USCITE | INGRESSO | DESCRIZIONE.
                # La direzione deriva ESCLUSIVAMENTE dalla colonna: il +/− stampato
                # davanti al valore viene ignorato per stabilire entrata/uscita.
                value_start = positions["value"]
                out_start = positions["out"]
                in_start = positions["in"]
                desc_start = positions["description"]
                # Le intestazioni sono l'inizio delle parole, non il bordo
                # sinistro delle colonne. I numeri sono allineati a destra:
                # usare token_start invertiva/perdeva importi. Calcoliamo quindi
                # i confini a metà fra intestazioni adiacenti e classifichiamo
                # ogni importo usando il centro del token, ignorando il suo segno.
                out_left = (value_start + out_start) // 2
                out_right = (out_start + in_start) // 2
                in_left = out_right
                in_right = (in_start + desc_start) // 2
                out_tokens: list[Decimal] = []
                in_tokens: list[Decimal] = []
                for token_match in MONEY_RE.finditer(layout_line):
                    token_start, token_end = token_match.start(), token_match.end()
                    token_center = (token_start + token_end) / 2
                    try:
                        parsed_value = abs(money(token_match.group(0)))
                    except (InvalidOperation, ValueError):
                        continue
                    # Caso tipico BPER: il valore di USCITE può iniziare a
                    # sinistra dell'intestazione ma termina prima di INGRESSO;
                    # quello di INGRESSO inizia dopo la sua intestazione.
                    if value_start <= token_start and token_end <= in_start:
                        out_tokens.append(parsed_value)
                    elif in_start <= token_start and token_end <= desc_start:
                        in_tokens.append(parsed_value)
                    elif out_left <= token_center < out_right:
                        out_tokens.append(parsed_value)
                    elif in_left <= token_center < in_right:
                        in_tokens.append(parsed_value)
                out_nonzero = [v for v in out_tokens if v != 0]
                in_nonzero = [v for v in in_tokens if v != 0]
                out_value = out_nonzero[-1] if len(out_nonzero) == 1 else (Decimal("0.00") if not out_nonzero and len(out_tokens) <= 1 else None)
                in_value = in_nonzero[-1] if len(in_nonzero) == 1 else (Decimal("0.00") if not in_nonzero and len(in_tokens) <= 1 else None)
                description = layout_line[desc_start:].strip()
                if out_value is not None and in_value is not None:
                    if out_value != 0 and in_value == 0:
                        amount, direction = -abs(out_value), "uscita"
                    elif in_value != 0 and out_value == 0:
                        amount, direction = abs(in_value), "entrata"
                    elif out_value == 0 and in_value == 0:
                        amount, direction = Decimal("0.00"), None
            if amount is None:
                # Fallback prudente: accetta importi soltanto se sono all'inizio
                # del testo dopo le date. Non interpreta numeri nella causale
                # (es. importi fattura, CIG o spese) come importo bancario.
                money_token = r"(?:[-−]\s*)?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?:\s*[-−])?"
                leading_pair = re.match(rf"^\s*({money_token})\s+({money_token})(?=\s|$)(.*)$", rest or "")
                leading_single = re.match(rf"^\s*({money_token})(?=\s|$)(.*)$", rest or "")
                if leading_pair:
                    first, second, tail = leading_pair.groups()
                    out_value, in_value = money(first), money(second)
                    if out_value != 0 and in_value == 0: amount, direction = -abs(out_value), "uscita"
                    elif in_value != 0 and out_value == 0: amount, direction = abs(in_value), "entrata"
                    elif out_value == 0 and in_value == 0: amount = Decimal("0.00")
                    description = tail.strip()
                elif leading_single and not re.search(r"\b(?:CIG|CUP|FATTURA|EUR|SPESE)\b", rest or "", re.I):
                    amount = money(leading_single.group(1))
                    direction = "entrata" if amount > 0 else "uscita" if amount < 0 else None
                    description = leading_single.group(2).strip()
                else:
                    # Compatibilità con estrazioni testuali che mettono la causale
                    # prima delle due colonne, ma solo se non compaiono indicatori
                    # di importi di fattura/codici nella descrizione.
                    values = [money(x) for x in MONEY_RE.findall(rest or "")]
                    has_invoice_tokens = bool(re.search(r"\b(?:CIG|CUP|FATTURA|EUR|SPESE|RIF\.)\b", rest or "", re.I))
                    if len(values) == 2 and not has_invoice_tokens and ((values[0] == 0) != (values[1] == 0)):
                        amount = -abs(values[0]) if values[0] != 0 else abs(values[1])
                        direction = "uscita" if values[0] != 0 else "entrata"
                        description = MONEY_RE.sub("", rest or "")
                    elif len(values) == 1 and not has_invoice_tokens:
                        amount = values[0]
                        direction = "entrata" if amount > 0 else "uscita" if amount < 0 else None
                        description = MONEY_RE.sub("", rest or "")
            details = extract_description_details(description)
            current = {"booking_date": booked, "value_date": value_date, "amount": amount,
                       "direction": direction, "description": re.sub(r"\s+", " ", description).strip(" -|\t"),
                       "counterparty_iban": None, "counterparty": details["counterparty"],
                       "invoice_details": details["invoice_details"], "invoice_amounts": details["invoice_amounts"],
                       "fees": details["fees"], "cig_codes": details["cig_codes"],
                       "balance_after": None, "category": None}
            continue
        if current is not None:
            current["description"] = (current.get("description", "") + " " + line).strip()
            details = extract_description_details(current["description"])
            if not current.get("counterparty"): current["counterparty"] = details["counterparty"]
            current["invoice_details"] = details["invoice_details"]
            current["invoice_amounts"] = details["invoice_amounts"]
            current["fees"] = details["fees"]
            current["cig_codes"] = details["cig_codes"]

    finish()
    for tx in transactions:
        description = tx.get("description", "")
        iban_match = IBAN_RE.search(description.upper())
        if iban_match: tx["counterparty_iban"] = re.sub(r"\s+", "", iban_match.group(0))
        if not tx.get("counterparty"):
            m = re.search(r"(?:ordinante|beneficiario|a favore di|da)\s*[:\-]?\s*(.{3,100}?)(?:\s+IBAN\b|$)", description, re.I)
            if m: tx["counterparty"] = m.group(1).strip(" -:")[:255]
    running = opening_balance
    if running is not None:
        for tx in sorted(transactions, key=lambda t: (t["booking_date"], t["value_date"])):
            running += tx["amount"]
            tx["balance_after"] = running
    return transactions, opening_balance, closing_balance


def parse_bper_pdf(path: str | Path) -> dict[str, Any]:
    """Estrae tutte le pagine, rilevando le intestazioni e mantenendo i saldi separati."""
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0: raise ValueError("Il PDF è protetto da password.")
        except Exception as exc:
            raise ValueError("Il PDF è protetto da password e non può essere letto senza password.") from exc

    all_transactions: list[dict[str, Any]] = []
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    normal_line_count = layout_line_count = normal_chars = 0
    detected_any_columns = False
    page_diagnostics = []
    last_columns = None

    # Parsing pagina per pagina evita che intestazioni/ripetizioni di pagina
    # interferiscano con le righe e permette di ereditare le colonne quando
    # BPER non ristampa l'intestazione sulle pagine successive.
    for page_number, page in enumerate(reader.pages, start=1):
        normal_lines = (page.extract_text() or "").splitlines()
        try:
            layout_lines = (page.extract_text(extraction_mode="layout") or "").splitlines()
        except (TypeError, ValueError):
            layout_lines = []
        normal_line_count += len(normal_lines)
        layout_line_count += len(layout_lines)
        normal_chars += sum(len(x.strip()) for x in normal_lines)

        page_columns = _find_columns(layout_lines)
        if page_columns:
            last_columns = page_columns
            detected_any_columns = True
        elif last_columns and layout_lines:
            page_columns = last_columns

        if page_columns and layout_lines:
            page_transactions, page_opening, page_closing = _parse_lines(layout_lines, page_columns)
            method = "layout"
        else:
            page_transactions, page_opening, page_closing = _parse_lines(normal_lines)
            method = "testo"

        all_transactions.extend(page_transactions)
        if page_opening is not None:
            opening_balance = page_opening
        if page_closing is not None:
            closing_balance = page_closing
        page_diagnostics.append({"page": page_number, "method": method, "transactions": len(page_transactions), "columns_detected": bool(page_columns)})

    # Ordine del documento: evita ordinamenti instabili in presenza di più
    # movimenti con la stessa data e conserva le operazioni trovate su ogni pagina.
    warnings = ["Importazione locale: verificare sempre la riconciliazione prima dell'uso contabile."]
    if not all_transactions:
        warnings.append("Il PDF contiene testo ma non sono state riconosciute righe di movimento." if normal_chars >= 30 else "Il PDF non contiene testo estraibile sufficiente; potrebbe essere una scansione.")
    if not detected_any_columns:
        warnings.append("Intestazioni delle colonne non riconosciute: il parser ha usato il testo lineare; controllare attentamente entrate e uscite.")
    return {
        "transactions": all_transactions,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "pages": len(reader.pages),
        "warnings": warnings,
        "diagnostics": {
            "normal_text_lines": normal_line_count,
            "layout_text_lines": layout_line_count,
            "normal_text_chars": normal_chars,
            "transactions_normal": None,
            "transactions_layout": len(all_transactions) if detected_any_columns else 0,
            "column_headers_detected": detected_any_columns,
            "pages_detail": page_diagnostics,
        },
    }
