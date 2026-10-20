from app.services.email_templates import render_receipt_email


def test_receipt_template_includes_receipt_details_and_escapes_html():
    text, html = render_receipt_email(
        receipt_number="CR-123",
        booking_id="booking-456",
        vehicle="<SUV>",
        vehicle_details="Blue & White, TEST-123",
        rental_start="2030-01-01T10:00:00Z",
        rental_end="2030-01-02T12:00:00Z",
        amount="$125.00",
    )

    assert "Receipt: CR-123" in text
    assert "Pick-up: January 1, 2030 at 10:00 UTC" in text
    assert "Total paid: $125.00 USD" in text
    assert "CR-123" in html
    assert "&lt;SUV&gt;" in html
    assert "Blue &amp; White" in html
    assert "January 2, 2030 at 12:00 UTC" in html
