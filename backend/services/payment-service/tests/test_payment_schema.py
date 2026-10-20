from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.payment import PaymentCreate


def test_payment_request_contains_only_a_booking_id():
    booking_id = uuid4()
    assert PaymentCreate.model_validate({"booking_id": str(booking_id)}).booking_id == booking_id


@pytest.mark.parametrize("untrusted_value", [1, 10_000, -1])
def test_client_cannot_supply_payment_amount(untrusted_value: int):
    with pytest.raises(ValidationError, match="amount_minor"):
        PaymentCreate.model_validate(
            {"booking_id": str(uuid4()), "amount_minor": untrusted_value, "currency": "USD"}
        )
