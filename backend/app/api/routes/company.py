"""Target Express's own details, for the top of a tax invoice.

Configuration rather than a database table: a GSTIN is a legal fact about one
company that changes almost never, and putting it behind a CRUD screen invites
somebody to edit it on a Tuesday. It lives in .env.prod beside the other things
only the server knows.

The endpoint reports what is MISSING as well as what is set. An invoice printed
without a GSTIN is not a cosmetic problem — it is a document the vendor cannot
claim input credit against, so it comes straight back. Better that the gap is
named on the screen than discovered by the person receiving it.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import BACK_OFFICE_ROLES, require_roles
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["company"])


class CompanyOut(BaseModel):
    name: str
    address: str
    gstin: str
    pan: str
    phone: str
    email: str
    state: str
    state_code: str
    bank_name: str
    bank_account: str
    bank_ifsc: str
    sac_code: str
    # Field names an invoice needs and does not have. The screen prints these
    # against the gap rather than leaving a blank line nobody notices.
    missing: list[str]


@router.get("/company", response_model=CompanyOut)
def company(_=Depends(require_roles(*BACK_OFFICE_ROLES))) -> CompanyOut:
    required = {
        "Company name": settings.company_name,
        "Address": settings.company_address,
        "GSTIN": settings.company_gstin,
    }
    return CompanyOut(
        name=settings.company_name,
        address=settings.company_address,
        gstin=settings.company_gstin,
        pan=settings.company_pan,
        phone=settings.company_phone,
        email=settings.company_email,
        state=settings.company_state,
        state_code=settings.company_state_code,
        bank_name=settings.company_bank_name,
        bank_account=settings.company_bank_account,
        bank_ifsc=settings.company_bank_ifsc,
        sac_code=settings.company_sac_code,
        missing=[label for label, value in required.items() if not value.strip()],
    )


# ---------------------------------------------------------------------------
# Amount in words
# ---------------------------------------------------------------------------

ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _under_hundred(n: int) -> str:
    if n < 20:
        return ONES[n]
    return (TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")).strip()


def _under_thousand(n: int) -> str:
    if n < 100:
        return _under_hundred(n)
    rest = n % 100
    return (ONES[n // 100] + " Hundred" + (" " + _under_hundred(rest) if rest else "")).strip()


def amount_in_words(amount: Decimal) -> str:
    """Rupees and paise, grouped the Indian way.

    A tax invoice carries the total in words as well as figures, and the
    grouping is lakh and crore rather than million — "One Lakh Twenty Thousand",
    not "One Hundred Twenty Thousand". A vendor's accounts team reads this line
    to check the figure above it, so the two have to agree.
    """
    whole = int(amount)
    paise = int(round((amount - whole) * 100))

    # Rounding can push paise to a full rupee — 99.999 gives 100 paise, which is
    # not a quantity of paise, it is one more rupee. Left uncarried it reads as
    # "Ninety Nine and One Hundred Paise", which is both wrong and a rupee short
    # of the figure printed above it on the same invoice.
    if paise >= 100:
        whole += paise // 100
        paise = paise % 100

    if whole == 0:
        words = "Zero"
    else:
        parts: list[str] = []
        crore, whole_rest = divmod(whole, 10_000_000)
        lakh, whole_rest = divmod(whole_rest, 100_000)
        thousand, hundreds = divmod(whole_rest, 1_000)

        if crore:
            parts.append(f"{_under_thousand(crore)} Crore")
        if lakh:
            parts.append(f"{_under_thousand(lakh)} Lakh")
        if thousand:
            parts.append(f"{_under_thousand(thousand)} Thousand")
        if hundreds:
            parts.append(_under_thousand(hundreds))
        words = " ".join(parts)

    out = f"Rupees {words}"
    if paise:
        out += f" and {_under_hundred(paise)} Paise"
    return out + " Only"
