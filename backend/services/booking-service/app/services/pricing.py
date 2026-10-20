from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP


SECONDS_PER_HOUR = Decimal("3600")
MAX_RENTAL_DURATION = timedelta(days=7)


def calculate_rental_price(start: datetime, end: datetime, hourly_rate: Decimal | str | int) -> int:
    """Return the USD rental total in cents, prorated from the vehicle's hourly rate.

    Times are compared as instants in UTC. There is no minimum billable
    duration; a positive interval that rounds below one cent is rejected.
    """
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("start must include a timezone")
    if end.tzinfo is None or end.utcoffset() is None:
        raise ValueError("end must include a timezone")
    duration = end.astimezone(UTC) - start.astimezone(UTC)
    if duration <= timedelta(0):
        raise ValueError("end must be later than start")
    if duration > MAX_RENTAL_DURATION:
        raise ValueError("Rental duration cannot exceed 7 days")
    rate = Decimal(str(hourly_rate))
    if rate <= 0:
        raise ValueError("hourly_rate must be greater than zero")
    seconds = (
        Decimal(duration.days * 86400 + duration.seconds)
        + Decimal(duration.microseconds) / Decimal(1_000_000)
    )
    amount_cents = (seconds * rate * Decimal(100) / SECONDS_PER_HOUR).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    if amount_cents < 1:
        raise ValueError("The rental price must be at least USD 0.01")
    return int(amount_cents)
