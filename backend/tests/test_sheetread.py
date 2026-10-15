"""Reading the vendor's own spreadsheet.

Every vendor's file is laid out differently. The bill number is in column B
for one and column A for another, the header is rarely the first row because
there is a logo and an address above it, and half the time what arrives with
an .xls name is really a CSV.

So the thing these tests hold is that nothing is decided silently. The columns
are GUESSED and reported; being quietly wrong about which one is the box count
puts the wrong number on a sticker a driver counts against at the door, and a
file whose header cannot be read must say so rather than mapping column A to
whatever happens to be first.
"""

import io

import pytest
from openpyxl import Workbook

from app.services.sheetread import read_sheet, to_lines


def xlsx(rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Day sheet"
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


# How a real vendor sheet arrives: a letterhead, a blank line, then the data.
GODREJ = [
    ["GODREJ INTERIO", "", "", ""],
    ["Dispatch summary 13-10-2026", "", "", ""],
    [],
    ["Bill No", "Consignee", "No of Boxes", "Article"],
    ["GDJ/8870", "Kannur Distribution Centre", 6, "Chair"],
    ["GDJ/8871", "Kozhikode Service Point", 4, "Table"],
    ["GDJ/8872", "Kasaragod Service Centre", 2, "Wardrobe"],
]


# ---------------------------------------------------------------------------
# Finding the header
# ---------------------------------------------------------------------------


def test_the_header_is_found_below_the_letterhead(client=None):
    """The first row of a vendor's sheet is a logo, not a header."""
    read = read_sheet(xlsx(GODREJ), "godrej.xlsx")
    assert read.header_row == 2, "counted after blank rows were dropped"
    assert read.columns[:4] == ["Bill No", "Consignee", "No of Boxes", "Article"]


def test_the_columns_are_recognised():
    read = read_sheet(xlsx(GODREJ), "godrej.xlsx")
    assert read.mapping == {
        0: "vendor_bill_no",
        1: "customer",
        2: "box_count",
        3: "item_name",
    }


def test_only_the_data_rows_come_back():
    read = read_sheet(xlsx(GODREJ), "godrej.xlsx")
    assert len(read.rows) == 3
    assert read.rows[0][0] == "GDJ/8870"


@pytest.mark.parametrize(
    "heading,expected",
    [
        ("Bill No.", "vendor_bill_no"),
        ("BILL_NUMBER", "vendor_bill_no"),
        ("Challan No", "vendor_bill_no"),
        ("Party Name", "customer"),
        ("Ship To", "customer"),
        ("Dealer", "customer"),
        ("Qty", "box_count"),
        ("No of Boxes", "box_count"),
        ("CARTONS", "box_count"),
        ("Description", "item_name"),
    ],
)
def test_the_names_vendors_actually_use(heading, expected):
    """Matched on letters only, so punctuation, case and underscores do not
    each need their own entry."""
    read = read_sheet(xlsx([[heading, "Consignee", "Qty"], ["X/1", "Someone", 1]]), "f.xlsx")
    assert read.mapping.get(0) == expected or expected in read.mapping.values()


def test_a_sheet_with_no_recognisable_header_says_so():
    """Rather than mapping column A to whatever happens to be first."""
    read = read_sheet(xlsx([["x", "y", "z"], ["1", "2", "3"]]), "mystery.xlsx")
    assert read.header_row is None
    assert read.mapping == {}
    assert any("header" in n.lower() for n in read.notes)


def test_a_missing_column_is_reported():
    """A sheet with no box count is readable and not usable, and the screen
    has to be able to say which."""
    read = read_sheet(
        xlsx([["Bill No", "Consignee"], ["GDJ/1", "Anand Agencies"]]), "f.xlsx"
    )
    assert any("box count" in n for n in read.notes)


# ---------------------------------------------------------------------------
# What arrives in practice
# ---------------------------------------------------------------------------


def test_a_csv_is_read_the_same_way():
    data = b"Bill No,Consignee,Boxes\nGDJ/8870,Kannur Distribution Centre,6\n"
    read = read_sheet(data, "day.csv")
    assert read.mapping[0] == "vendor_bill_no"
    assert read.rows[0][2] == "6"


def test_a_csv_wearing_an_xls_name_is_still_read():
    """Half of what a vendor's system exports is a CSV called .xls. Refusing
    it on the extension helps nobody."""
    data = b"Bill No,Consignee,Boxes\nGDJ/8870,Kannur,6\n"
    read = read_sheet(data, "export.xls")
    assert read.rows, read.notes
    assert any("text file" in n for n in read.notes)


def test_a_semicolon_separated_file():
    data = b"Bill No;Consignee;Boxes\nGDJ/8870;Kannur;6\n"
    read = read_sheet(data, "day.csv")
    assert read.rows[0][2] == "6"


def test_blank_rows_in_the_middle_are_dropped():
    rows = GODREJ + [[], ["GDJ/8873", "Kattappana Dealer", 3, "Bed"]]
    read = read_sheet(xlsx(rows), "f.xlsx")
    assert len(read.rows) == 4
    assert read.rows[-1][0] == "GDJ/8873"


def test_an_empty_file_is_reported_not_crashed():
    read = read_sheet(xlsx([]), "empty.xlsx")
    assert read.rows == []
    assert read.notes


# ---------------------------------------------------------------------------
# Turning it into bills
# ---------------------------------------------------------------------------


def test_the_rows_become_lines_the_day_sheet_already_reads():
    """Deliberately reusing that parser. It already matches misspelt customer
    names, catches duplicate bills and handles a missing count, and two code
    paths that both turn a row into a bill is two places for them to disagree
    about what a bill is."""
    read = read_sheet(xlsx(GODREJ), "godrej.xlsx")
    lines = to_lines(read, read.mapping)

    assert lines == [
        "GDJ/8870 Kannur Distribution Centre 6 Chair",
        "GDJ/8871 Kozhikode Service Point 4 Table",
        "GDJ/8872 Kasaragod Service Centre 2 Wardrobe",
    ]


def test_a_spreadsheet_number_does_not_become_a_decimal():
    """6.0 out of a spreadsheet is six boxes. Left alone, the parser reads it
    as two numbers and takes the wrong one."""
    read = read_sheet(xlsx([["Bill No", "Consignee", "Boxes"], ["GDJ/1", "Anand", 6.0]]), "f.xlsx")
    assert to_lines(read, read.mapping) == ["GDJ/1 Anand 6"]


def test_a_corrected_mapping_is_what_is_used():
    """The person overrides the guess, and the override wins — that is the
    whole reason the guess is shown rather than acted on."""
    read = read_sheet(xlsx(GODREJ), "godrej.xlsx")
    swapped = {0: "vendor_bill_no", 1: "customer", 3: "box_count"}
    assert to_lines(read, swapped)[0] == "GDJ/8870 Kannur Distribution Centre Chair"


def test_the_fields_come_out_in_the_order_the_parser_expects():
    """Bill, customer, count, article — whatever order the columns were in."""
    rows = [["Boxes", "Consignee", "Bill No"], [6, "Kannur", "GDJ/8870"]]
    read = read_sheet(xlsx(rows), "f.xlsx")
    assert to_lines(read, read.mapping) == ["GDJ/8870 Kannur 6"]


def test_a_row_with_nothing_mapped_is_skipped():
    read = read_sheet(xlsx(GODREJ), "godrej.xlsx")
    assert to_lines(read, {}) == []
