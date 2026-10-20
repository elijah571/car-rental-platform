from datetime import UTC, datetime
from html import escape


def _format_datetime(value: str) -> str:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    return f"{timestamp:%B} {timestamp.day}, {timestamp:%Y at %H:%M} UTC"


def render_receipt_email(
    *,
    receipt_number: str,
    booking_id: str,
    vehicle: str,
    vehicle_details: str,
    rental_start: str,
    rental_end: str,
    amount: str,
) -> tuple[str, str]:
    start = _format_datetime(rental_start)
    end = _format_datetime(rental_end)
    text = (
        "Payment confirmed\n\n"
        f"Thanks for booking with Drivewell. Your payment has been received.\n\n"
        f"Receipt: {receipt_number}\n"
        f"Booking: {booking_id}\n"
        f"Vehicle: {vehicle} ({vehicle_details})\n"
        f"Pick-up: {start}\n"
        f"Return: {end}\n"
        f"Total paid: {amount} USD\n\n"
        "Keep this email for your records.\n\nDrivewell"
    )
    safe = escape
    html = f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>Your Drivewell receipt {safe(receipt_number)}</title>
  </head>
  <body style="margin:0;background:#f3f5f8;color:#172033;font-family:Arial,Helvetica,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">Your payment is confirmed. Receipt {safe(receipt_number)}.</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f5f8;padding:32px 16px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#ffffff;border:1px solid #e4e8ef;border-radius:12px;">
          <tr><td style="padding:28px 32px 16px;border-bottom:1px solid #edf0f4;">
            <div style="font-size:22px;font-weight:700;letter-spacing:-0.4px;color:#173b67;">Drivewell</div>
          </td></tr>
          <tr><td style="padding:32px 32px 24px;">
            <div style="margin-bottom:12px;font-size:13px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#25805b;">Payment confirmed</div>
            <h1 style="margin:0 0 12px;font-size:25px;line-height:1.3;color:#172033;">Thanks for your booking</h1>
            <p style="margin:0;font-size:15px;line-height:1.6;color:#536176;">Your payment has been received. Keep this receipt for your records.</p>
          </td></tr>
          <tr><td style="padding:0 32px 24px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f7fc;border:1px solid #dce7f4;border-radius:8px;">
              <tr><td style="padding:18px 20px;font-size:13px;color:#536176;">Receipt number</td>
                  <td align="right" style="padding:18px 20px;font-size:14px;font-weight:700;color:#173b67;">{safe(receipt_number)}</td></tr>
              <tr><td style="padding:0 20px 18px;font-size:13px;color:#536176;">Total paid</td>
                  <td align="right" style="padding:0 20px 18px;font-size:22px;font-weight:700;color:#172033;">{safe(amount)} USD</td></tr>
            </table>
          </td></tr>
          <tr><td style="padding:0 32px 28px;">
            <h2 style="margin:0 0 14px;font-size:17px;color:#172033;">Your rental</h2>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="font-size:14px;line-height:1.5;">
              <tr><td style="padding:8px 0;color:#7b8798;">Vehicle</td><td align="right" style="padding:8px 0;color:#172033;">{safe(vehicle)}<br><span style="color:#536176;">{safe(vehicle_details)}</span></td></tr>
              <tr><td style="padding:8px 0;color:#7b8798;">Pick-up</td><td align="right" style="padding:8px 0;color:#172033;">{safe(start)}</td></tr>
              <tr><td style="padding:8px 0;color:#7b8798;">Return</td><td align="right" style="padding:8px 0;color:#172033;">{safe(end)}</td></tr>
              <tr><td style="padding:8px 0;color:#7b8798;">Booking reference</td><td align="right" style="padding:8px 0;color:#172033;">{safe(booking_id)}</td></tr>
            </table>
          </td></tr>
          <tr><td style="padding:18px 32px;border-top:1px solid #edf0f4;font-size:12px;line-height:1.5;color:#7b8798;">
            Drivewell &middot; Your journey, made simple.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
"""
    return text, html
