"""Reading a day's bills off a typed or pasted sheet.

The thing being replaced is thirty trips through a dialog box. The thing that
must not happen is a carton delivered to the wrong town because a name was
guessed at — so these tests care about two different properties, and the second
one matters more:

  * The obvious input is read correctly and without fuss.
  * Anything doubtful is FLAGGED rather than quietly resolved. A line that is
    read wrongly and confidently is worse than one that asks.

The customer names here are the ones actually in use, because a matcher tuned
on invented names proves nothing about the names it will meet.
"""

import pytest

from app.services.daysheet import (
    CONFIDENT,
    match_customer,
    normalise,
    parse_line,
    parse_sheet,
    similarity,
)

# The real list, as the demo data has it.
CUSTOMERS = [
    {"id": "c1", "name": "Kannur Distribution Centre", "city": "Kannur"},
    {"id": "c2", "name": "Kasaragod Service Centre", "city": "Kasaragod"},
    {"id": "c3", "name": "Kozhikode Service Point", "city": "Kozhikode"},
    {"id": "c4", "name": "TVM Distribution Centre", "city": "Trivandrum"},
    {"id": "c5", "name": "Kattappana Dealer", "city": "Kattappana"},
    {"id": "c6", "name": "Palakkad Service Centre", "city": "Palakkad"},
    {"id": "c7", "name": "Thrissur Dealer Outlet", "city": "Thrissur"},
    {"id": "c8", "name": "Rinshad Km", "city": "Aluva"},
]


def read(line: str):
    return parse_line(line, 1, CUSTOMERS)


# ---------------------------------------------------------------------------
# The ordinary line
# ---------------------------------------------------------------------------


def test_the_shape_people_actually_type():
    parsed = read("GDJ/8870 Rinshad Km 6")

    assert parsed.vendor_bill_no == "GDJ/8870"
    assert parsed.match.name == "Rinshad Km"
    assert parsed.box_count == 6
    assert parsed.problems == []


def test_a_bill_number_without_the_slash():
    for text in ("GDJ8870", "gdj 8870", "GDJ-8870", "gdj/8870"):
        parsed = read(f"{text} Rinshad Km 6")
        assert parsed.vendor_bill_no == "GDJ/8870", text


def test_the_count_can_say_boxes():
    assert read("GDJ/8870 Rinshad Km 6 boxes").box_count == 6
    assert read("GDJ/8870 Rinshad Km 6 nos").box_count == 6
    assert read("GDJ/8870 Rinshad Km 6 cartons").box_count == 6


def test_an_article_is_picked_off():
    parsed = read("GDJ/8871 Kannur DC 4 chairs")
    assert parsed.box_count == 4
    assert parsed.item_name == "Chairs"
    assert parsed.match.name == "Kannur Distribution Centre"


def test_a_paste_out_of_a_spreadsheet():
    """Tabs and commas are just separators; the order is what is read."""
    parsed = read("GDJ/8870\tRinshad Km\t6")
    assert parsed.vendor_bill_no == "GDJ/8870"
    assert parsed.box_count == 6
    assert parsed.problems == []

    parsed = read("GDJ/8870, Rinshad Km, 6")
    assert parsed.box_count == 6
    assert parsed.problems == []


# ---------------------------------------------------------------------------
# Names typed the way people type them
# ---------------------------------------------------------------------------


def test_an_abbreviated_branch():
    """"Kannur DC" is how it is said out loud, and it is not what is on file."""
    assert read("GDJ/8871 Kannur DC 4").match.name == "Kannur Distribution Centre"


def test_a_misspelt_branch():
    """The input this was tuned on."""
    parsed = read("gdj 8872 kozikode srvce 2 chair")

    assert parsed.vendor_bill_no == "GDJ/8872"
    assert parsed.match.name == "Kozhikode Service Point"
    assert parsed.match.score >= CONFIDENT
    assert parsed.box_count == 2
    assert parsed.item_name == "Chair"


def test_the_town_on_its_own():
    """People write the town and mean that branch."""
    assert read("GDJ/8872 kozhikode 2").match.name == "Kozhikode Service Point"


def test_case_and_spacing_do_not_matter():
    a = read("GDJ/8870   RINSHAD    KM   6")
    b = read("gdj/8870 rinshad km 6")
    assert a.match.consignee_id == b.match.consignee_id == "c8"


def test_an_american_spelling_still_matches():
    assert read("GDJ/8871 Kannur Distribution Center 4").match.name == (
        "Kannur Distribution Centre"
    )


# ---------------------------------------------------------------------------
# What it refuses to guess
# ---------------------------------------------------------------------------


def test_an_unknown_customer_is_not_forced_onto_the_nearest_name():
    """The failure that matters. A carton sent to the wrong town because a new
    dealer's name was 60% like an existing one."""
    parsed = read("GDJ/8880 Vadakara Furniture House 3")
    assert parsed.match.consignee_id is None
    assert parsed.needs_attention
    assert "No customer on file matches" in parsed.problems[0]


def test_a_doubtful_match_is_flagged_not_used():
    parsed = read("GDJ/8880 Kann 3")
    if parsed.match and parsed.match.consignee_id:
        assert parsed.match.score < CONFIDENT
        assert parsed.needs_attention


def test_a_missing_bill_number_is_reported():
    parsed = read("Rinshad Km 6")
    assert parsed.vendor_bill_no is None
    assert "No bill number found" in parsed.problems


def test_a_missing_count_is_reported():
    """Never defaulted to 1. The box count is what the driver counts against at
    the door, so a wrong one is a short delivery nobody can explain."""
    parsed = read("GDJ/8870 Rinshad Km")
    assert parsed.box_count is None
    assert "No box count found" in parsed.problems


def test_the_bill_number_is_not_mistaken_for_the_count():
    parsed = read("GDJ/8870 Rinshad Km 6")
    assert parsed.box_count == 6, "took digits out of the bill number"


def test_doubtful_matches_offer_the_runners_up():
    """"Did you mean" is only useful with the alternatives."""
    match = match_customer("Service Centre", CUSTOMERS)
    assert match is not None
    assert match.alternatives, "no alternatives offered for an ambiguous name"


# ---------------------------------------------------------------------------
# A whole sheet
# ---------------------------------------------------------------------------


SHEET = """
GDJ/8870 Rinshad Km 6
GDJ/8871 Kannur DC 4 chairs

gdj 8872 kozikode srvce 2 chair
GDJ/8873 Vadakara Furniture House 3
"""


def test_a_sheet_reads_every_line_and_skips_the_blanks():
    rows = parse_sheet(SHEET, CUSTOMERS)
    assert len(rows) == 4


def test_the_good_lines_come_through_clean():
    rows = parse_sheet(SHEET, CUSTOMERS)
    clean = [r for r in rows if not r.needs_attention]
    assert len(clean) == 3
    assert [r.vendor_bill_no for r in clean] == ["GDJ/8870", "GDJ/8871", "GDJ/8872"]


def test_only_the_unknown_customer_needs_attention():
    rows = parse_sheet(SHEET, CUSTOMERS)
    flagged = [r for r in rows if r.needs_attention]
    assert len(flagged) == 1
    assert flagged[0].vendor_bill_no == "GDJ/8873"


def test_the_total_boxes_are_right():
    rows = parse_sheet(SHEET, CUSTOMERS)
    assert sum(r.box_count for r in rows if r.box_count) == 15


def test_the_same_bill_twice_is_caught_on_screen():
    """An ordinary slip when working off a paper stack. Far cheaper to say so
    than to create half the sheet and have the database refuse the rest."""
    rows = parse_sheet(
        "GDJ/8870 Rinshad Km 6\nGDJ/8871 Kannur DC 2\nGDJ/8870 Kozhikode 3",
        CUSTOMERS,
    )
    assert not rows[0].needs_attention
    assert any("already on line 1" in p for p in rows[2].problems)


def test_line_numbers_are_the_typed_ones():
    """So the message points at the line the person is looking at."""
    rows = parse_sheet(SHEET, CUSTOMERS)
    assert rows[0].line_no == 2, "blank first line was not counted"


# ---------------------------------------------------------------------------
# The pieces underneath
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Kannur DC", "kannur distribution centre"),
        ("TVM D.C.", "trivandrum distribution centre"),
        ("Kozhikode  Service   Point", "kozhikode service point"),
        ("Center", "centre"),
    ],
)
def test_normalising(text, expected):
    assert normalise(text) == expected


def test_an_exact_name_scores_one():
    assert similarity("Kannur Distribution Centre", "Kannur Distribution Centre") == 1.0


def test_a_close_name_beats_a_different_one():
    close = similarity("kozikode srvce", "Kozhikode Service Point")
    other = similarity("kozikode srvce", "Kannur Distribution Centre")
    assert close > other
    assert close >= CONFIDENT
