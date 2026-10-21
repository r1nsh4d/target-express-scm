"""Sanity on a meter reading, before it becomes money.

An invoice went to Godrej for ₹34,28,434.24 on a single one-point run to
Aluva. The line read 180,015 km at ₹17 a kilometre beyond the sixty included.
180,015 is not a distance — it is what the lorry's odometer says, and it was
entered as the closing reading of a leg whose opening reading was near zero.

Nothing anywhere objected. Not the driver's phone, not the office screen, not
the invoice preview. The number was four and a half times round the Earth and
it printed, was signed, and went out.

So three facts are checked here, and they are facts rather than guesses:

  A METER DOES NOT RUN BACKWARDS. An opening reading below the vehicle's last
  closing reading is either a typo or a replaced instrument, and a replaced
  instrument is an office correction with a reason attached, not something a
  driver does from a lorry bay at five in the morning.

  A LORRY DOES NOT DRIVE THREE THOUSAND KILOMETRES ON ONE RUN. Ernakulam to
  Kasaragod and back is about 950. The ceiling is set far above anything this
  business does, because its job is to catch a transposed digit rather than to
  second-guess a long day.

  A SINGLE RUN IS NOT A MONTH'S WORK. If a leg's distance is most of the
  opening reading, what was entered was the meter, not the trip.

Each refusal names BOTH readings and the distance they imply. "That is too
far" sends somebody hunting; "closing 180,015 against opening 60 means 179,955
km" tells them exactly which of the two they fat-fingered.
"""

from __future__ import annotations

# Far beyond anything a Kerala round trip does, deliberately. A guard that
# argues with a real long day gets switched off; one that only ever fires on a
# typo stays on.
MAX_LEG_KM = 3_000


class OdometerRefused(ValueError):
    """A reading that cannot be right, with the arithmetic that shows it."""


def check_opening(reading: int, last_closing: int | None) -> None:
    """The opening reading, against where this vehicle last finished."""
    if last_closing is None:
        return
    if reading < last_closing:
        raise OdometerRefused(
            f"The meter reads {reading:,} but this lorry finished its last run at "
            f"{last_closing:,}. A meter does not go backwards — check the reading, "
            "and if the instrument has been replaced ask the office to correct it."
        )


def check_distance(start: int, end: int) -> None:
    """The pair, and the distance between them."""
    if end < start:
        raise OdometerRefused(
            f"Closing reading {end:,} is below the opening reading {start:,}."
        )

    distance = end - start
    if distance > MAX_LEG_KM:
        raise OdometerRefused(
            f"That is {distance:,} km on one run — closing {end:,} against opening "
            f"{start:,}. The longest run this business does is under a thousand. "
            "Check which of the two readings is wrong."
        )

    # The specific mistake that produced the ₹34 lakh invoice: the opening
    # reading was near zero and the real meter went in as the closing one.
    if start > 0 and distance > start:
        raise OdometerRefused(
            f"Closing {end:,} against opening {start:,} is a run longer than the "
            "whole life of the meter. The opening reading looks wrong."
        )
