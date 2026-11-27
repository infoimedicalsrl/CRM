
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from pypdf import PdfReader


@dataclass
class ParsedDDTLine:
    supplier_product_code: str
    description: str | None
    quantity: Decimal
    unit_code: str = "PZ"
    lot_number: str | None = None
    expiry_date: date | None = None


@dataclass
class ParsedDDT:
    ddt_number: str
    ddt_date: date
    customer_name: str
    customer_vat: str | None
    order_reference: str | None
    lines: list[ParsedDDTLine]


def _decode_legacy_text(text: str) -> str:
    """Decode the common custom PDF encoding used by Italian DDT templates.

    The sample DDT uses a font encoding where ASCII glyphs are shifted by 29
    positions and spaces are represented by control character 0x03. We only
    transform characters in the ranges used by that encoding, leaving normal
    PDF text untouched.
    """
    out = []
    for char in text:
        code = ord(char)
        if code == 3:
            out.append(" ")
        elif 1 <= code < 100:
            decoded = code + 29
            out.append(chr(decoded) if 32 <= decoded <= 126 else char)
        else:
            out.append(char)
    return "".join(out)


def _extract_text(path: Path) -> str:
    """Extract text using both normal and layout-preserving PDF extraction.

    DDT tables are often encoded as positioned text rather than semantic rows.
    ``layout`` keeps the visual column structure and is substantially more
    reliable for code/description/quantity/lot/scadenza extraction.
    """
    reader = PdfReader(str(path))
    plain_pages: list[str] = []
    layout_pages: list[str] = []
    for page in reader.pages:
        plain_pages.append(page.extract_text(extraction_mode="plain") or "")
        layout_pages.append(page.extract_text(extraction_mode="layout") or "")

    candidates: list[str] = []
    for pages in (layout_pages, plain_pages):
        raw = "\n".join(pages)
        decoded = _decode_legacy_text(raw)
        candidates.append(decoded)
        candidates.append(raw)

    def score(value: str) -> int:
        upper = value.upper()
        product_codes = len(_CODE_RE.findall(upper)) if "_CODE_RE" in globals() else 0
        quantities = len(re.findall(r"\b\d+(?:[.,]\d+)?\s*(?:PZ|PCS|PEZZI|PEZZO|KT|UNITÀ|UNITA)\b", upper))
        lots = len(re.findall(r"\bLOTTO\b", upper))
        expiries = len(re.findall(r"\bSCADENZA\b", upper))
        return (100 if "DOCUMENTO DI TRASPORTO" in upper else 0) + product_codes * 8 + quantities * 3 + lots * 2 + expiries * 2

    return max(candidates, key=score) if candidates else ""


def _ocr_text(path: Path) -> str:
    """Local OCR fallback. No document is sent outside the Mac."""
    tesseract = shutil.which("tesseract")
    pdftoppm = shutil.which("pdftoppm")
    if not tesseract or not pdftoppm:
        raise RuntimeError(
            "Il PDF non è estraibile automaticamente con la codifica disponibile. "
            "Per questo documento serve il fallback OCR locale (tesseract + pdftoppm)."
        )
    page_count = len(PdfReader(str(path)).pages)
    with tempfile.TemporaryDirectory() as tmp:
        prefix = str(Path(tmp) / "page")
        subprocess.run(
            [pdftoppm, "-f", "1", "-l", str(page_count), "-r", "300", "-png", str(path), prefix],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pages = sorted(Path(tmp).glob("page-*.png")) or sorted(Path(tmp).glob("page.png"))
        chunks = []
        for image in pages:
            result = subprocess.run(
                [tesseract, str(image), "stdout", "-l", "ita"],
                check=True, capture_output=True, text=True,
            )
            chunks.append(result.stdout)
        return "\n".join(chunks)


def _clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\r", "\n")).strip()


def _first_date(text: str) -> date | None:
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text)
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _parse_date(value: str) -> date | None:
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", value)
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _normalize_code(code: str) -> str:
    return re.sub(r"\s+", "", code).upper()


# Product codes in the user's DDTs are alphanumeric and commonly contain '-'.
_CODE_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z]{1,8}[A-Z0-9]*(?:[-_/][A-Z0-9]+)+|[A-Z]{2,}[0-9][A-Z0-9]*)(?![A-Z0-9])",
    re.I,
)
_GENERIC_TOKEN_RE = re.compile(r"(?<![A-Z0-9])([A-Z0-9][A-Z0-9._/-]{2,63})(?![A-Z0-9])", re.I)


def _looks_like_code(value: str) -> bool:
    x = _normalize_code(value).strip("=,;:()[]")
    if len(x) < 2 or len(x) > 64 or " " in x:
        return False
    if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", x):
        return False
    if re.fullmatch(r"\d{4}", x):
        return False
    if re.fullmatch(r"\d{11}", x):
        return False
    # Product codes in the DDTs are normally alphanumeric. Permit pure numeric
    # codes only when the caller has positively identified the token as the
    # first code-like field of a product row.
    if re.fullmatch(r"\d+", x):
        return len(x) >= 4
    if not re.fullmatch(r"[A-Z0-9]+(?:[-_/.][A-Z0-9]+)*", x):
        return False
    return any(c.isalpha() for c in x) and any(c.isdigit() for c in x)


def _parse_quantity(text: str) -> tuple[Decimal | None, str]:
    unit_pattern = r"(pezzi|pezzo|pz|pcs|unità|unita|units|kt|c62|cf|conf|confezioni|ml|kg|g|l)"
    patterns = [
        rf"(?:q(?:ta|tà)?|quantit(?:à|a)|qty)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*{unit_pattern}\b",
        rf"(\d+(?:[.,]\d+)?)\s*{unit_pattern}\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if not m:
            continue
        value = Decimal(m.group(1).replace(",", "."))
        unit = m.group(2).upper()
        if unit in {"KT", "CF", "CONF", "CONFEZIONI"}:
            unit_code = "KT" if unit == "KT" else "CF"
        elif unit == "C62":
            unit_code = "PZ"
        else:
            unit_code = "PZ"
        return value, unit_code

    stripped = text.strip()
    if re.fullmatch(r"\d+(?:[.,]\d+)?", stripped):
        value = Decimal(stripped.replace(",", "."))
        if value >= 0 and value not in {Decimal("2025"), Decimal("2026")}:
            return value, "PZ"
    return None, "PZ"


def _extract_lot(text: str) -> str | None:
    patterns = [
        # Lots in the DDT template may contain an internal space, e.g.
        # ``TEA 214`` or ``SLA 113``. Stop explicitly at the following
        # ``Scadenza`` label so the date is never absorbed into the lot.
        r"(?:lotto|lot|batch)\s*(?:n(?:r|°)?\.?\s*)?[:=]?\s*([A-Z0-9][A-Z0-9./_-]*(?:\s+[A-Z0-9][A-Z0-9./_-]*)*)(?=\s+(?:scadenza|scad|expiry|exp\.)\b|$)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip(".,;:")
    return None


def _extract_expiry(text: str) -> date | None:
    for pattern in (
        r"(?:scadenza|scad|expiry|exp\.)\s*[:=]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    ):
        m = re.search(pattern, text, re.I)
        if m:
            parsed = _parse_date(m.group(1))
            if parsed:
                return parsed
    return None


def _clean_description_candidate(value: str, code: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    text = re.sub(re.escape(code), " ", text, flags=re.I)
    text = re.sub(r"(?:lotto|lot|batch)\s*(?:n(?:r|°)?\.?)?\s*[:=]?\s*[A-Z0-9./_-]+", " ", text, flags=re.I)
    text = re.sub(r"(?:scadenza|scad|expiry|exp\.)\s*[:=]?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", " ", text, flags=re.I)
    text = re.sub(r"(?:q(?:ta|tà)?|quantit(?:à|a)|qty)\s*[:=]?\s*\d+(?:[.,]\d+)?\s*(?:pezzi|pezzo|pz|pcs|unità|unita|units|kt|c62|cf|conf|confezioni)?", " ", text, flags=re.I)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:pezzi|pezzo|pz|pcs|unità|unita|units|kt|c62|cf|conf|confezioni)\b", " ", text, flags=re.I)
    # Column separators used by the sample template are not meaningful in the description.
    text = re.sub(r"[=|]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -:=|;")
    if not text or not re.search(r"[A-Za-zÀ-ÿ]", text):
        return None
    upper = text.upper()
    forbidden = (
        "DOCUMENTO DI TRASPORTO", "DESTINATARIO", "MITTENTE", "P.IVA", "PARTITA IVA",
        "CODICE FISCALE", "DA IMP.", "DA IMPEG", "ORDINE", "IMPEGNO", "RIFERIMENTO",
        "DATA E FIRMA", "FIRMA", "TOTALE", "TRASPORTO A", "CAUSALE", "ASPETTO",
        "PESO", "COLLI", "ANNOTAZIONI", "NOTE", "VETTORE",
    )
    if any(marker in upper for marker in forbidden):
        return None
    return text


def _table_lines(text: str) -> list[str]:
    """Convert extracted PDF text into stable visual rows.

    We deliberately do not flatten the document. DDT parsing is row-oriented:
    a product starts at a code field and owns only the following fields until
    the next product code. This prevents lot/scadenza values from one product
    being attached to the next one.
    """
    normalized = text.replace("\r", "\n").replace("\f", "\n").replace("'", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]
    return [line for line in lines if line]


def _line_code_candidates(line: str) -> list[str]:
    """Return code candidates that can start a product row.

    Priority is given to the left side of a table separator (=), an explicit
    'cod.' marker, and the first token. A generic scan is used only as a
    fallback, and lot/scadenza labels are explicitly excluded.
    """
    upper = line.upper()
    # Exclude metadata lines that *start* with lot/scadenza labels. A product
    # row may legitimately contain "Lotto" or "Scadenza" later on the same
    # line, so those words alone must never invalidate the product row.
    if re.match(r"^(?:lotto|lot|batch|scadenza|scad|expiry|exp\.)\b", line, re.I):
        return []
    if re.search(r"(?:P\.\s*IVA|PARTITA IVA)\b", upper) and not re.match(r"^\S+\s+", line):
        return []

    candidates: list[str] = []

    def add(value: str, *, allow_numeric: bool = False) -> None:
        value = value.strip(" =,:;|()[]")
        if not _looks_like_code(value):
            return
        normalized = _normalize_code(value)
        if normalized.isdigit() and not allow_numeric:
            return
        if value not in candidates:
            candidates.append(value)

    left = line.split("=", 1)[0].strip()
    if left and " " not in left:
        # A numeric code is safe here because '=' is a strong indication that
        # this is a table code cell rather than an address/date/quantity.
        add(left, allow_numeric=True)

    cod_match = re.search(r"\bcod(?:ice)?\.?\s*[:=]?\s*([A-Z0-9][A-Z0-9._/-]{2,63})", line, re.I)
    if cod_match:
        add(cod_match.group(1), allow_numeric=True)

    # Product rows can have a visual line number/bullet before the code.
    first = re.match(r"^(?:\d{1,4}[.)-]?\s+)?([A-Z0-9][A-Z0-9._/-]{2,63})(?:\s+|=|$)", line, re.I)
    if first:
        # Numeric first tokens are accepted only when the line itself carries
        # a quantity/unit, otherwise postal codes, dates and other numbers can
        # be mistaken for products.
        add(first.group(1), allow_numeric=_parse_quantity(line)[0] is not None)

    # Some PDFs visually split a product code with spaces, e.g.
    # ``BE-HLS 7050``. Try the first two tokens as one code after removing
    # whitespace, but only if the first token by itself was not already a
    # valid code. This preserves the distinction between CODE + DESCRIPTION.
    first_two = re.match(r"^([A-Z0-9][A-Z0-9._/-]{1,31})\s+([A-Z0-9][A-Z0-9._/-]{1,31})(?:\s|=|$)", line, re.I)
    if first_two and not candidates:
        add(first_two.group(1) + first_two.group(2), allow_numeric=_parse_quantity(line)[0] is not None)

    # Do not scan arbitrary text for codes: codes printed inside descriptions,
    # order references or notes are not new product rows. Product anchors must
    # be at the beginning of a row or introduced by an explicit "cod." marker.

    # A numeric code is accepted only when the same line looks like a product
    # row (there is a quantity/unit somewhere after it).
    if not candidates and re.match(r"^\d{4,}(?:\s|=)", line):
        if _parse_quantity(line)[0] is not None:
            add(re.match(r"^\d{4,}", line).group(0))

    return candidates


def _product_anchors(raw_lines: list[str]) -> list[tuple[int, str]]:
    anchors: list[tuple[int, str]] = []
    for idx, line in enumerate(raw_lines):
        candidates = _line_code_candidates(line)
        if not candidates:
            continue

        # A genuine product row normally has its quantity on the same line or
        # on one of the next couple of visual lines. This extra guard prevents
        # a code-like token appearing in a free-text note/description from
        # starting a new product block.
        has_quantity_nearby = _parse_quantity(line)[0] is not None or any(
            _parse_quantity(raw_lines[j])[0] is not None
            for j in range(idx + 1, min(idx + 3, len(raw_lines)))
        )
        if not has_quantity_nearby:
            continue

        # Prefer the first candidate: for a row such as CODE=CODE, both tokens
        # are the same product. If a description contains another code later,
        # it must not become a second row.
        code = _normalize_code(candidates[0])

        # Do not treat a repeated print of the same code in the immediately
        # following description line as a new product row.
        if anchors and anchors[-1][1] == code and idx - anchors[-1][0] <= 2:
            continue
        anchors.append((idx, code))

    return anchors


def _description_for_row(segment: list[str], code: str) -> str | None:
    """Pick the actual product description from one row block only."""
    descriptions: list[tuple[int, str]] = []
    for offset, line in enumerate(segment):
        # Remove the code only when it is present as a standalone token or
        # table cell; never remove unrelated substrings from normal words.
        cleaned = re.sub(rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])", " ", line, flags=re.I)
        candidate = _clean_description_candidate(cleaned, code)
        if not candidate:
            continue
        score = 100 - offset * 4 + min(len(candidate), 100) / 20
        if candidate.casefold().startswith(("kit composto da", "composto da")):
            score -= 30
        # A line containing the quantity is usually the description+quantity
        # line; retain its textual part, but rank a clean description line higher.
        if _parse_quantity(line)[0] is not None:
            score -= 8
        descriptions.append((int(score), candidate))
    return max(descriptions, key=lambda x: x[0])[1] if descriptions else None


def _parse_one_product_segment(segment: list[str], code: str) -> ParsedDDTLine | None:
    """Parse exactly one product block, without looking into another block."""
    if not segment:
        return None
    combined = " ".join(segment)

    quantity: Decimal | None = None
    unit = "PZ"
    # First look line-by-line. This is important because quantity may be in a
    # dedicated column/line and must not be confused with dates or lot numbers.
    for line in segment:
        quantity, unit = _parse_quantity(line)
        if quantity is not None:
            break
    if quantity is None:
        quantity, unit = _parse_quantity(combined)
    if quantity is None:
        return None

    lot = None
    expiry = None
    # Lot and expiry are extracted from the same product block only. Prefer a
    # single line containing both, then fall back to individual lines.
    for line in segment:
        line_lot = _extract_lot(line)
        line_expiry = _extract_expiry(line)
        if line_lot and lot is None:
            lot = line_lot
        if line_expiry and expiry is None:
            expiry = line_expiry
    if lot is None:
        lot = _extract_lot(combined)
    if expiry is None:
        expiry = _extract_expiry(combined)

    description = _description_for_row(segment, code)
    return ParsedDDTLine(code, description, quantity, unit, lot, expiry)


def _parse_lines_from_text(text: str) -> list[ParsedDDTLine]:
    raw_lines = _table_lines(text)
    anchors = _product_anchors(raw_lines)
    rows: list[ParsedDDTLine] = []

    for anchor_pos, (start_idx, code) in enumerate(anchors):
        next_anchor_idx = anchors[anchor_pos + 1][0] if anchor_pos + 1 < len(anchors) else len(raw_lines)
        segment = raw_lines[start_idx:next_anchor_idx]
        parsed = _parse_one_product_segment(segment, code)
        if parsed is not None:
            rows.append(parsed)

    return rows


def _extract_table_rows_by_code_column(path: Path) -> list[ParsedDDTLine]:
    """Parse PDF DDTs using the physical CODE column as the row anchor.

    This is the preferred parser for born-digital PDFs. The same product code
    is often printed once in the CODE column and again inside the DESCRIPTION
    column. We must anchor exclusively on the CODE column, otherwise the second
    occurrence can be mistaken for another product.
    """
    reader = PdfReader(str(path))
    all_rows: list[ParsedDDTLine] = []

    for page in reader.pages:
        fragments: list[tuple[float, float, str]] = []

        def visitor(text, cm, tm, font_dict, font_size):
            value = _decode_legacy_text(text or "").replace("\n", " ").strip()
            if value:
                fragments.append((float(tm[4]), float(tm[5]), value))

        try:
            page.extract_text(visitor_text=visitor)
        except Exception:
            continue

        if not fragments:
            continue

        # Find the table headers by decoded text and use their actual X
        # coordinates. This makes the code-column boundary independent of the
        # document's page width/template.
        code_headers = [f for f in fragments if re.search(r"^CODICE$", f[2], re.I)]
        desc_headers = [f for f in fragments if re.search(r"^DESCRIZIONE$", f[2], re.I)]
        qty_headers = [f for f in fragments if re.search(r"^QUANTIT", f[2], re.I)]
        if not code_headers or not desc_headers:
            continue

        code_header = min(code_headers, key=lambda f: f[1])
        desc_header = min(desc_headers, key=lambda f: abs(f[1] - code_header[1]))
        header_y = code_header[1]
        desc_x = desc_header[0]
        # Everything left of the gap between CODE and DESCRIPTION belongs to
        # the CODE column. Keep a small margin so the description's first
        # characters cannot leak into it.
        code_x_max = (code_header[0] + desc_x) / 2.0
        code_x_min = max(0.0, code_header[0] - 45.0)

        # Determine the bottom of the table from the next obvious footer.
        footer_markers = ("DATA E FIRMA", "NUMERO DI COLLI", "PESO", "TRASPORTO")
        footer_y = min(
            (f[1] for f in fragments if any(marker in f[2].upper() for marker in footer_markers) and f[1] < header_y),
            default=-10**9,
        )

        # Select only text physically inside the CODE column, below the header.
        code_fragments = [
            f for f in fragments
            if f[1] < header_y - 2.0
            and f[1] > footer_y + 2.0
            and code_x_min <= f[0] <= code_x_max
        ]

        # Group close Y coordinates into visual code cells. A code may be
        # emitted by the PDF as multiple fragments on the same baseline.
        code_groups: list[list[tuple[float, float, str]]] = []
        for fragment in sorted(code_fragments, key=lambda f: (-f[1], f[0])):
            if not code_groups or abs(code_groups[-1][0][1] - fragment[1]) > 3.0:
                code_groups.append([fragment])
            else:
                code_groups[-1].append(fragment)

        anchors: list[tuple[float, str]] = []
        for group in code_groups:
            cell = "".join(f[2] for f in sorted(group, key=lambda f: f[0])).strip()
            # Strip row-number prefixes but NEVER search the description column.
            cell = re.sub(r"^\d{1,4}[.)-]?\s*", "", cell)
            candidates = _line_code_candidates(cell)
            if not candidates:
                # Once the physical CODICE column has been identified, its
                # content is authoritative. Do not apply the generic product
                # code heuristic here: legitimate short/alphabetic codes such
                # as ``AT3``, ``AT6`` and ``AT-KIT`` are valid product codes
                # even though they contain no numeric suffix.
                token = cell.strip(" =,:;|()[]")
                if re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]{1,63}", token, re.I):
                    candidates = [token]
            if not candidates:
                continue
            code = _normalize_code(candidates[0])
            y = max(f[1] for f in group)
            if anchors and anchors[-1][1] == code and abs(anchors[-1][0] - y) <= 8.0:
                continue
            anchors.append((y, code))

        if not anchors:
            continue

        # Build each product segment from the current CODE-cell baseline to
        # the next CODE-cell baseline. The code itself is fixed from the CODE
        # column; all other fields are allowed to come only from this segment.
        page_fragments = sorted(fragments, key=lambda f: (-f[1], f[0]))
        for pos, (code_y, code) in enumerate(anchors):
            next_y = anchors[pos + 1][0] if pos + 1 < len(anchors) else footer_y
            segment_fragments = [
                f for f in page_fragments
                if f[1] <= code_y + 2.0 and (next_y < -1e8 or f[1] > next_y + 2.0)
            ]
            # Do not include the duplicate code printed in DESCRIPTION as the
            # authoritative code; it is harmless for description cleaning.
            segment_lines = [f[2] for f in segment_fragments]
            parsed = _parse_one_product_segment(segment_lines, code)
            if parsed is not None:
                all_rows.append(parsed)

    return all_rows

def parse_ddt(path: str | Path) -> ParsedDDT:
    path = Path(path)
    extracted = _extract_text(path)
    # Keep a line-preserving representation for the header/table parser.
    # The old implementation flattened this too early, which caused the
    # DESTINATARIO block to be lost and made table fields easier to mix up.
    decoded_text = extracted
    text = _clean(decoded_text)
    if "DOCUMENTO DI TRASPORTO" not in text.upper():
        try:
            ocr = _clean(_ocr_text(path))
            if ocr:
                text = ocr
        except Exception:
            pass

    number_match = re.search(
        r"(?:DOCUMENTO DI TRASPORTO|documento di trasporto)\s+(?:nr\.?|n\.?|n°)?\s*([A-Z0-9][A-Z0-9./_-]*)\s+(?:del|DEL)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        text,
        flags=re.I,
    )
    if not number_match:
        number_match = re.search(r"\b(?:nr\.?|n\.?)\s*([0-9]+/[0-9]{4})\s+(?:del)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.I)
    if not number_match:
        raise ValueError("Numero/data DDT non riconosciuti nel PDF.")
    ddt_number = number_match.group(1).strip()
    ddt_date = _parse_date(number_match.group(2))
    if not ddt_date:
        raise ValueError("Data DDT non riconosciuta.")

    destination_text = text[text.upper().find("DESTINATARIO"):] if "DESTINATARIO" in text.upper() else text
    vat_match = re.search(r"(?:P\.?I\.?VA(?:/CF)?|P\.?IVA/CF)\s*[: ]*\s*(\d{11})", destination_text, re.I)
    customer_vat = vat_match.group(1) if vat_match else None

    # This DDT template places the customer name on the first line immediately
    # after DESTINATARIO. Read that line before flattening the document text.
    customer_name = ""
    header_lines = _table_lines(decoded_text)
    for i, line in enumerate(header_lines):
        if line.strip().upper() == "DESTINATARIO" and i + 1 < len(header_lines):
            customer_name = header_lines[i + 1].strip()
            break
    if not customer_name:
        dest_match = re.search(
            r"DESTINATARIO\s+(.*?)(?:\s+Contrada|\s+Via|\s+Viale|\s+Corso|\s+Piazza|\s+\d{5}\s+[A-ZÀ-Ý]|P\.?I\.?VA)",
            text,
            re.I | re.S,
        )
        customer_name = re.sub(r"\s+", " ", dest_match.group(1).strip()) if dest_match else "Cliente DDT"

    order_match = re.search(
        r"(?:da\s+impeg\.?|ordine|impegno|rif(?:erimento)?\.?\s*ordine)\s*[:#]?\s*([A-Z0-9][A-Z0-9./_-]*)\s+(?:del|DEL)\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
        text,
        re.I,
    )
    order_reference = order_match.group(1).strip() if order_match else None

    # Prefer the physical CODE column for real PDFs. The text parser remains
    # as a fallback for OCR/plain-text documents where coordinates are unavailable.
    rows = _extract_table_rows_by_code_column(path)
    if not rows:
        rows = _parse_lines_from_text(text)
    if not rows:
        # One last local OCR attempt even when the PDF contained a recognizable header:
        # the header may be extractable while the product table is not.
        try:
            ocr = _clean(_ocr_text(path))
            if ocr and ocr != text:
                ocr_rows = _parse_lines_from_text(ocr)
                if len(ocr_rows) > len(rows):
                    text = ocr
                    rows = ocr_rows
        except Exception:
            pass

    if not rows:
        raise ValueError("Nessuna riga prodotto riconosciuta nel DDT. Il PDF contiene testo non strutturato o una tabella non estraibile.")

    return ParsedDDT(ddt_number, ddt_date, customer_name, customer_vat, order_reference, rows)

