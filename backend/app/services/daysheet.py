"""Reading a day's bills the way somebody would actually type them.

The morning's work arrives as a stack of vendor bills and goes into the system
one form at a time: pick a division, pick a warehouse, pick a customer from a
list of two hundred, type the bill number, type the box count, save, repeat.
For thirty bills that is thirty round trips through a dialog, and it is the
part of the day everyone complains about.

This reads them instead. One bill per line, in whatever order the numbers and
the name happen to come out:

    GDJ/8870 Rinshad Km 6
    gdj 8872 kozikode srvce 2 chair
    GDJ/8871  Kannur DC  4 chairs

There is no language model behind it and it needs no internet. It is three
things that are each individually dull: a pattern for the bill number, a rule
for which number is the box count, and a fuzzy match for what is left over
against the customers already on file. Dull is the point — it runs on the
client's own server, costs nothing per line, cannot be down, and never sends a
customer's name anywhere.

What it will NOT do is guess silently. Every line comes back with what it
understood and how sure it is, and anything under the confident threshold is
handed to a person with the alternatives listed. A wrong customer on a bill is
a carton delivered to the wrong town; it is worth a confirming click.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# How sure the match has to be before it is used without asking. Set from the
# real names in use: "kozikode srvce" against "Kozhikode Service Point" scores
# around 0.89, and that is the worst input anyone should have to confirm. Below
# this the line is still read, it just waits for a person.
CONFIDENT = 0.86

# Below this, calling it a match at all is a stretch, and the line is treated as
# a customer nobody has entered yet.
PLAUSIBLE = 0.58

# What people type instead of what is on file. Expanded on both sides before
# matching, so "Kannur DC" and "Kannur Distribution Centre" are the same string
# by the time they are compared rather than a 0.4 similarity.
ABBREVIATIONS = {
    "dc": "distribution centre",
    "sc": "service centre",
    "sp": "service point",
    "svc": "service",
    "srv": "service",
    "srvce": "service",
    "servc": "service",
    "center": "centre",
    "ctr": "centre",
    "cntr": "centre",
    "pt": "point",
    "dlr": "dealer",
    "agencies": "agency",
    "agncy": "agency",
    "ent": "enterprises",
    "entp": "enterprises",
    "tvm": "trivandrum",
    "tcr": "thrissur",
    "ekm": "ernakulam",
    "clt": "kozhikode",
    "knr": "kannur",
    "ksd": "kasaragod",
    "plkd": "palakkad",
}

# Words that are about the carton rather than the customer, so they are not
# allowed to drag a name match around.
QUANTITY_WORDS = {
    "box",
    "boxes",
    "bx",
    "btl",
    "carton",
    "cartons",
    "case",
    "cases",
    "nos",
    "no",
    "pcs",
    "pieces",
    "qty",
}

# A vendor bill number: two to five letters, then a separator people type or
# leave out, then the digits. GDJ/8870, GDJ-8870, gdj 8870, GDJ8870.
BILL_PATTERN = re.compile(r"\b([A-Za-z]{2,5})\s*[/\-]?\s*(\d{2,8})\b")


@dataclass
class CustomerMatch:
    consignee_id: str | None
    name: str
    score: float
    # Everything else that came close, best first. Shown when the top match is
    # not confident, because "did you mean" is only useful with the runners-up.
    alternatives: list[dict] = field(default_factory=list)


@dataclass
class ParsedLine:
    line_no: int
    raw: str
    vendor_bill_no: str | None
    customer_text: str
    match: CustomerMatch | None
    box_count: int | None
    item_name: str | None
    # What a person has to look at before this can be created.
    problems: list[str] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        return bool(self.problems)


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, expand the abbreviations people type."""
    text = text.lower()
    # "D.C." is one abbreviation, not two letters. Stripping punctuation first
    # would leave "d c", which matches nothing — so initialisms are closed up
    # before anything else touches them. Two or more single letters each
    # followed by a dot, which is what an initialism is and what "St. Mary" is
    # not.
    text = re.sub(r"\b((?:[a-z]\.){2,})", lambda m: m.group(1).replace(".", ""), text)
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    words = [ABBREVIATIONS.get(w, w) for w in text.split()]
    # An expansion can itself be several words ("dc" -> "distribution centre"),
    # so flatten before returning.
    return " ".join(" ".join(words).split())


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def similarity(query: str, candidate: str) -> float:
    """How close two customer names are, 0 to 1.

    Two measures, and the better of them wins, because they fail on opposite
    inputs. Whole-string similarity handles a name typed almost right but
    catastrophically mis-scores a short query against a long official name —
    "Kannur DC" against "Kannur Distribution Centre" is only 0.55 by that
    measure even though it is obviously the same place. Token similarity
    handles that, by asking whether every word the person typed has a close
    partner in the candidate, and ignoring the words they did not bother with.
    """
    a, b = normalise(query), normalise(candidate)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    whole = _ratio(a, b)

    a_tokens = [t for t in a.split() if t not in QUANTITY_WORDS]
    b_tokens = b.split()
    if not a_tokens or not b_tokens:
        return whole

    # Every word the person typed should find a partner. Weighted by length, so
    # getting "kozhikode" right counts for more than getting "the" right.
    total_weight = 0.0
    earned = 0.0
    for token in a_tokens:
        best = max(_ratio(token, other) for other in b_tokens)
        weight = float(len(token))
        total_weight += weight
        earned += best * weight
    token_score = earned / total_weight if total_weight else 0.0

    # A query that names only part of the customer is still a good match, but
    # not a perfect one — "Kannur" alone should not beat "Kannur DC" when both
    # Kannur branches exist. A small penalty for how much was left unsaid.
    coverage = min(1.0, len(a_tokens) / len(b_tokens))
    token_score *= 0.88 + 0.12 * coverage

    return max(whole, token_score)


def match_customer(text: str, customers: list[dict]) -> CustomerMatch | None:
    """Best customer for this text, with the runners-up.

    `customers` is a list of {"id", "name", "city"} so the service stays free of
    the database and can be tested on plain data.
    """
    if not text.strip() or not customers:
        return None

    scored: list[tuple[float, dict]] = []
    for customer in customers:
        name = customer["name"]
        score = similarity(text, name)

        # The city is worth trying too: people write "kozhikode 2" and mean the
        # Kozhikode branch without typing the rest of its name.
        if customer.get("city"):
            with_city = similarity(text, f"{name} {customer['city']}")
            score = max(score, with_city, similarity(text, customer["city"]) * 0.82)

        scored.append((score, customer))

    scored.sort(key=lambda row: (-row[0], row[1]["name"]))
    best_score, best = scored[0]

    if best_score < PLAUSIBLE:
        return CustomerMatch(consignee_id=None, name=text.strip(), score=best_score)

    return CustomerMatch(
        consignee_id=best["id"],
        name=best["name"],
        score=round(best_score, 3),
        alternatives=[
            {"id": c["id"], "name": c["name"], "city": c.get("city"), "score": round(s, 3)}
            for s, c in scored[1:4]
            if s >= PLAUSIBLE
        ],
    )


def _extract_bill_no(text: str) -> tuple[str | None, str]:
    """Pull the bill number out, and give back what is left.

    Only a letters-then-digits form counts. A bare number is far more likely to
    be the box count, and guessing wrong there puts the wrong figure on the
    sticker that the driver counts against at the door.
    """
    match = BILL_PATTERN.search(text)
    if match is None:
        return None, text

    series, digits = match.group(1).upper(), match.group(2)
    rest = text[: match.start()] + " " + text[match.end() :]
    return f"{series}/{digits}", rest


def _extract_box_count(text: str) -> tuple[int | None, str]:
    """Which number is the carton count.

    Preference order, because a line can hold several numbers:
      1. a number attached to a quantity word  — "6 boxes", "6 nos"
      2. a bare number on its own
    A number stuck to letters is left alone: it is part of a name or a code.
    """
    with_word = re.search(
        r"\b(\d{1,4})\s*(" + "|".join(QUANTITY_WORDS) + r")\b", text, re.IGNORECASE
    )
    if with_word:
        rest = text[: with_word.start()] + " " + text[with_word.end() :]
        return int(with_word.group(1)), rest

    bare = list(re.finditer(r"(?<![A-Za-z0-9])(\d{1,4})(?![A-Za-z0-9])", text))
    if bare:
        # The last one. People write the name first and the count last far more
        # often than the other way round.
        chosen = bare[-1]
        rest = text[: chosen.start()] + " " + text[chosen.end() :]
        return int(chosen.group(1)), rest

    return None, text


# Words that describe the goods rather than the customer. Only used to pull an
# article name off the end of a line; anything not listed is left as part of the
# customer text rather than guessed at.
ARTICLE_WORDS = {
    "chair",
    "chairs",
    "table",
    "tables",
    "sofa",
    "sofas",
    "almirah",
    "almirahs",
    "wardrobe",
    "wardrobes",
    "bed",
    "beds",
    "mattress",
    "desk",
    "desks",
    "cabinet",
    "cabinets",
    "panel",
    "panels",
    "fridge",
    "washing",
    "machine",
    "ac",
    "tv",
    "spare",
    "spares",
    "parts",
}


def _extract_article(text: str) -> tuple[str | None, str]:
    words = text.split()
    article = [w for w in words if w.lower().strip(".,") in ARTICLE_WORDS]
    if not article:
        return None, text

    kept = [w for w in words if w.lower().strip(".,") not in ARTICLE_WORDS]
    return " ".join(article).title(), " ".join(kept)


def parse_line(line: str, line_no: int, customers: list[dict]) -> ParsedLine | None:
    """One line of the day sheet. None for a blank one."""
    raw = line.strip()
    if not raw:
        return None

    # A paste out of a spreadsheet arrives tab- or comma-separated. Treated as
    # spaces: the order of the fields is what is read, not the separator, so one
    # code path covers typing and pasting.
    working = re.sub(r"[\t;,|]+", " ", raw)

    bill_no, working = _extract_bill_no(working)
    box_count, working = _extract_box_count(working)
    item_name, working = _extract_article(working)

    customer_text = " ".join(working.split())
    match = match_customer(customer_text, customers)

    problems: list[str] = []
    if not bill_no:
        problems.append("No bill number found")
    if box_count is None:
        problems.append("No box count found")
    elif box_count < 1:
        problems.append("Box count has to be at least 1")
    if not customer_text:
        problems.append("No customer named")
    elif match is None or match.consignee_id is None:
        problems.append(f"No customer on file matches “{customer_text}”")
    elif match.score < CONFIDENT:
        problems.append(f"Not sure this is {match.name}")

    return ParsedLine(
        line_no=line_no,
        raw=raw,
        vendor_bill_no=bill_no,
        customer_text=customer_text,
        match=match,
        box_count=box_count,
        item_name=item_name,
        problems=problems,
    )


def parse_sheet(text: str, customers: list[dict]) -> list[ParsedLine]:
    """Every non-blank line, in order.

    Duplicate bill numbers within the sheet are flagged here rather than left to
    the database: typing the same bill twice is an ordinary slip when working
    off a paper stack, and it is far cheaper to say so on screen than to have
    half the sheet created and half refused.
    """
    lines = [
        parsed
        for n, line in enumerate(text.splitlines(), start=1)
        if (parsed := parse_line(line, n, customers)) is not None
    ]

    seen: dict[str, int] = {}
    for parsed in lines:
        if not parsed.vendor_bill_no:
            continue
        first = seen.get(parsed.vendor_bill_no)
        if first is not None:
            parsed.problems.append(
                f"Bill {parsed.vendor_bill_no} is already on line {first}"
            )
        else:
            seen[parsed.vendor_bill_no] = parsed.line_no

    return lines
