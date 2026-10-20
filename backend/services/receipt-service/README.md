# Car Rental Receipt Service

Stores immutable receipts and rental ticket snapshots for paid bookings.

## Development

Run these commands from this directory:

```bash
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:app --reload --port 8005
```

The service reads `RECEIPT_SERVICE_API_KEY` and the shared PostgreSQL settings (`DATABASE_URL` or `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`) from the repository `.env`. Set a strong random service key and share it only with trusted backend callers.

The API runs at <http://127.0.0.1:8005>; interactive docs are at <http://127.0.0.1:8005/docs>. `/health` reports liveness and `/ready` checks the receipt table.

## API

- `POST /receipts` creates a receipt snapshot. Include `X-Receipt-Service-Key`, `Idempotency-Key`, booking/payment/customer IDs, the Stripe PaymentIntent ID, rental times, amount in USD cents, and the vehicle make, model, color, and license plate as they were at booking time.
- `GET /receipts/{receipt_id}` retrieves a stored receipt using the service key.
- `GET /receipts/internal/by-booking/{booking_id}` retrieves a receipt by booking ID using the service key. Customer access is mediated by the booking service, which verifies Cognito ownership before calling this internal route.

Receipt creation is intended to be called by trusted backend orchestration only after a verified successful Stripe webhook and confirmed booking state. Repeated delivery with the same idempotency key and payload returns the existing receipt; reusing that key with different receipt data returns 409. Booking, payment, and vehicle snapshots remain independent of later service data changes. The API returns receipt data as JSON; PDF generation remains unimplemented.
