from datetime import datetime
from typing import Literal


BookingAction = Literal["cancel", "start", "return", "approve_inspection", "reject_inspection"]


def next_booking_status(
    current: str,
    action: BookingAction,
    *,
    now: datetime,
    pickup_at: datetime,
    return_at: datetime,
) -> str:
    if action == "cancel" and current == "pending":
        return "cancelled"
    if action == "start" and current == "confirmed" and pickup_at <= now < return_at:
        return "active"
    if action == "return" and current == "active":
        return "awaiting_inspection"
    if action == "approve_inspection" and current in {"awaiting_inspection", "inspection_failed"}:
        if return_at <= now:
            return "completed"
        raise ValueError("The scheduled rental period has not ended.")
    if action == "reject_inspection" and current in {"awaiting_inspection", "inspection_failed"}:
        return "inspection_failed"
    raise ValueError(f"Cannot {action.replace('_', ' ')} a booking in {current} status.")
