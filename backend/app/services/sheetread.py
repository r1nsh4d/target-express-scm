"""Reading the vendor's own spreadsheet.

The day's bills arrive as a file from the vendor long before anybody types
them, and every vendor's file is laid out differently: Godrej's bill number is
in column B, somebody else's is in A, and the header row is rarely the first
row because there is a logo and an address above it.

So this does not assume a layout. It finds the header row by looking for words
it recognises, maps the columns it can, and hands back what it found along
with what it guessed — the person confirms the mapping on screen before a
single bill is created. Guessing silently and being wrong about which column
is the box count puts the wrong number on a sticker a driver counts against.

CSV is handled by the same path, because half the time what arrives is a CSV
with an .xls name, and refusing it on the extension helps nobody.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

# What a column of each kind tends to be called. Matched against the header
# text with everything but letters stripped, so "Bill No." and "BILL_NO" and
# "billno" are the same thing.
HEADER_WORDS: dict[str, tuple[str, ...]] = {
    "vendor_bill_no": (
        "billno", "bill", "invoiceno", "docno", "documentno", "billnumber",
        "vendorbillno", "dcno", "challanno",
    ),
    "customer": (
        "customer", "consignee", "partyname", "party", "dealer", "shipto",
        "deliverto", "consigneename", "customername", "name",
    ),
    "box_count": (
        "boxes", "box", "qty", "quantity", "cartons", "carton", "nos", "pkgs",
        "packages", "noofboxes", "boxqty", "cases",
    ),
    "item_name": ("article", "item", "description", "product", "goods", "itemname"),
    "city": ("city", "town", "place", "destination", "location", "district"),
    "phone": ("phone", "mobile", "contact", "contactno", "mobileno", "phoneno"),
}

# A header row has to look like one. Two recognised words is the threshold:
# one is a coincidence — a cell reading "Customer" in an address block — and
# three would miss a sparse sheet with only a bill number and a count.
MIN_HEADER_HITS = 2

# How far down to look. A letterhead, an address and a title take a few rows;
# twenty is generous and stops a 5,000-row file being scanned for a header
# that is not there.
MAX_HEADER_SCAN = 20


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


@dataclass
class SheetRead:
    """What was found in the file, before anybody has agreed to it."""

    columns: list[str]
    rows: list[list[str]]
    # column index -> field name, as far as the headers could be read. The
    # screen shows this as a guess to confirm, never as a decision taken.
    mapping: dict[int, str] = field(default_factory=dict)
    header_row: int | None = None
    sheet_name: str | None = None
    # Said plainly rather than raised: a file that cannot be read at all is
    # rare, and a file that is readable but odd is common.
    notes: list[str] = field(default_factory=list)


def _cells_from_xlsx(data: bytes) -> tuple[list[list[str]], str | None]:
    from openpyxl import load_workbook

    # data_only: a cell holding =B2*C2 should give the number, not the formula.
    # read_only: a day sheet can be long and nothing here needs the styling.
    book = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    sheet = book.active
    rows = [
        ["" if cell is None else str(cell).strip() for cell in row]
        for row in sheet.iter_rows(values_only=True)
    ]
    name = sheet.title
    book.close()
    return rows, name


def _cells_from_csv(data: bytes) -> tuple[list[list[str]], str | None]:
    text = data.decode("utf-8-sig", errors="replace")
    # Tab, semicolon and comma all turn up. Sniffing beats assuming.
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), dialect)], None


def _find_header(rows: list[list[str]]) -> tuple[int | None, dict[int, str]]:
    """The first row that reads like a header, and what its columns are.

    Searched rather than assumed, because the first row of a vendor's sheet is
    usually a logo, an address or a title. A sheet with no recognisable header
    returns None and the screen asks the person to map the columns itself.
    """
    best: tuple[int, dict[int, str]] | None = None

    for index, row in enumerate(rows[:MAX_HEADER_SCAN]):
        mapping: dict[int, str] = {}
        taken: set[str] = set()
        for column, cell in enumerate(row):
            text = _norm(cell)
            if not text:
                continue
            for field_name, words in HEADER_WORDS.items():
                if field_name in taken:
                    continue
                # Exact first, then contained — "No of Boxes" contains
                # "boxes", and "Customer Name" contains "customer".
                if text == field_name.replace("_", "") or text in words or any(
                    w in text for w in words if len(w) > 3
                ):
                    mapping[column] = field_name
                    taken.add(field_name)
                    break

        if len(mapping) >= MIN_HEADER_HITS and (best is None or len(mapping) > len(best[1])):
            best = (index, mapping)

    return best if best else (None, {})


def read_sheet(data: bytes, filename: str) -> SheetRead:
    """Read a spreadsheet into rows, and guess what the columns are.

    Nothing is created here and nothing is decided. The caller shows the guess,
    the person corrects it, and only then are bills made — because being wrong
    about which column is the box count puts the wrong number on a sticker a
    driver counts against at the door.
    """
    name = (filename or "").lower()
    notes: list[str] = []

    if name.endswith(".csv") or name.endswith(".txt"):
        rows, sheet_name = _cells_from_csv(data)
    else:
        try:
            rows, sheet_name = _cells_from_xlsx(data)
        except Exception:
            # Half the time an "xls" from a vendor's system is a CSV with the
            # wrong name. Refusing it on the extension helps nobody.
            rows, sheet_name = _cells_from_csv(data)
            notes.append("Read as a text file — it is not really a spreadsheet.")

    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return SheetRead(columns=[], rows=[], notes=["The file has no rows in it."])

    header_row, mapping = _find_header(rows)

    if header_row is None:
        notes.append(
            "No header row was recognised, so the columns need naming by hand."
        )
        columns = [f"Column {chr(65 + i)}" for i in range(max(len(r) for r in rows))]
        body = rows
    else:
        columns = [
            str(c).strip() or f"Column {chr(65 + i)}"
            for i, c in enumerate(rows[header_row])
        ]
        body = rows[header_row + 1 :]

    width = max([len(columns)] + [len(r) for r in body]) if body else len(columns)
    columns = columns + [f"Column {chr(65 + i)}" for i in range(len(columns), width)]
    body = [list(r) + [""] * (width - len(r)) for r in body]

    missing = {"vendor_bill_no", "customer", "box_count"} - set(mapping.values())
    if header_row is not None and missing:
        notes.append(
            "Could not find a column for: "
            + ", ".join(sorted(m.replace("_", " ") for m in missing))
        )

    return SheetRead(
        columns=columns,
        rows=body,
        mapping=mapping,
        header_row=header_row,
        sheet_name=sheet_name,
        notes=notes,
    )


def to_lines(read: SheetRead, mapping: dict[int, str]) -> list[str]:
    """Turn the mapped columns back into the one-line-per-bill text the day
    sheet parser already understands.

    Deliberately reusing that parser rather than writing a second one. It
    already matches misspelt customer names, catches duplicate bills and
    handles a missing box count, and two code paths that both turn a row into
    a bill is two places for them to disagree about what a bill is.
    """
    order = ["vendor_bill_no", "customer", "box_count", "item_name"]
    by_field = {field_name: column for column, field_name in mapping.items()}

    lines: list[str] = []
    for row in read.rows:
        parts: list[str] = []
        for field_name in order:
            column = by_field.get(field_name)
            if column is None or column >= len(row):
                continue
            value = str(row[column]).strip()
            if not value:
                continue
            # 6.0 out of a spreadsheet is six boxes, not "6.0" — which the
            # parser would read as two numbers.
            if field_name == "box_count":
                try:
                    value = str(int(float(value)))
                except ValueError:
                    pass
            parts.append(value)

        if parts:
            lines.append(" ".join(parts))

    return lines
