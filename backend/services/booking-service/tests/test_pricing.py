from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.services.pricing import calculate_rental_price


def test_one_hour_costs_ten_thousand_cents():
    start = datetime(2030, 1, 1, tzinfo=UTC)
    assert calculate_rental_price(start, start + timedelta(hours=1), "10.00") == 1_000


def test_half_hour_costs_fifty_dollars():
    start = datetime(2030, 1, 1, tzinfo=UTC)
    assert calculate_rental_price(start, start + timedelta(minutes=30), "100.00") == 5_000


def test_duration_is_calculated_as_an_instant_across_timezones():
    start = datetime(2030, 1, 1, 12, tzinfo=timezone(timedelta(hours=2)))
    end = datetime(2030, 1, 1, 11, tzinfo=UTC)
    assert calculate_rental_price(start, end, "10.00") == 1_000


def test_half_cent_rounds_up_to_nearest_cent():
    start = datetime(2030, 1, 1, tzinfo=UTC)
    duration = timedelta(microseconds=180_000)
    assert calculate_rental_price(start, start + duration, "200.00") == 1


def test_naive_or_reversed_times_are_rejected():
    start = datetime(2030, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="timezone"):
        calculate_rental_price(datetime(2030, 1, 1), start, "10.00")
    with pytest.raises(ValueError, match="later"):
        calculate_rental_price(start, start, "10.00")


def test_interval_that_rounds_to_zero_cents_is_rejected():
    start = datetime(2030, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="at least USD 0.01"):
        calculate_rental_price(start, start + timedelta(milliseconds=100), "0.01")


def test_rental_cannot_exceed_one_week():
    start = datetime(2030, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="7 days"):
        calculate_rental_price(start, start + timedelta(days=7, seconds=1), "10.00")


def test_price_uses_vehicle_hourly_rate():
    start = datetime(2030, 1, 1, tzinfo=UTC)
    assert calculate_rental_price(start, start + timedelta(hours=1), "150.00") == 15_000
