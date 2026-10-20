from datetime import UTC, datetime, timedelta

import pytest

from app.services.lifecycle import next_booking_status


def test_paid_booking_lifecycle_keeps_vehicle_blocked_until_inspection():
    pickup = datetime(2030, 1, 1, 10, tzinfo=UTC)
    return_at = pickup + timedelta(hours=2)
    assert next_booking_status(
        "confirmed", "start", now=pickup, pickup_at=pickup, return_at=return_at
    ) == "active"
    assert next_booking_status(
        "active", "return", now=pickup + timedelta(hours=1), pickup_at=pickup, return_at=return_at
    ) == "awaiting_inspection"
    assert next_booking_status(
        "awaiting_inspection", "reject_inspection", now=return_at,
        pickup_at=pickup, return_at=return_at,
    ) == "inspection_failed"
    assert next_booking_status(
        "inspection_failed", "approve_inspection", now=return_at,
        pickup_at=pickup, return_at=return_at,
    ) == "completed"


def test_booking_cannot_start_before_pickup_or_after_return():
    pickup = datetime(2030, 1, 1, 10, tzinfo=UTC)
    return_at = pickup + timedelta(hours=2)
    for now in (pickup - timedelta(seconds=1), return_at):
        with pytest.raises(ValueError, match="Cannot start"):
            next_booking_status(
                "confirmed", "start", now=now, pickup_at=pickup, return_at=return_at
            )


def test_inspection_cannot_release_vehicle_before_scheduled_return():
    pickup = datetime(2030, 1, 1, 10, tzinfo=UTC)
    return_at = pickup + timedelta(hours=2)
    with pytest.raises(ValueError, match="period has not ended"):
        next_booking_status(
            "awaiting_inspection", "approve_inspection", now=return_at - timedelta(seconds=1),
            pickup_at=pickup, return_at=return_at,
        )


def test_only_pending_bookings_can_be_cancelled():
    now = datetime(2030, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="Cannot cancel"):
        next_booking_status(
            "confirmed", "cancel", now=now, pickup_at=now, return_at=now + timedelta(hours=1)
        )
