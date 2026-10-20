# Car Rental Payment Service

Stripe PaymentIntent and webhook integration for the Car Rental Platform.

## Development

From this directory, install dependencies and start the API:

```bash
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:app --reload --port 8004
```

The service reads `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, and `PAYMENT_SERVICE_API_KEY`, plus the shared PostgreSQL settings (`DATABASE_URL` or `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`) from the repository `.env`. The secret key must be a Stripe test key for local development. Set the webhook secret from Stripe CLI with `stripe listen --forward-to localhost:8004/payments/webhooks/stripe`.

The API runs at <http://127.0.0.1:8004>; interactive documentation is at <http://127.0.0.1:8004/docs>. `/health` reports liveness and `/ready` checks the payment tables.

## API

- Customers create a payment intent through `POST /bookings/{booking_id}/payment-intent` with a local auth-service access token and `Idempotency-Key`. The booking service checks ownership and hold status; the payment service obtains the saved amount and currency directly from the booking service. The client never submits a payment total. The response includes the Stripe PaymentIntent `client_secret` for checkout.
- `POST /payments/intents` is an internal endpoint. It accepts `X-Payment-Service-Key`, `Idempotency-Key`, and a booking ID only, then checks the authoritative booking amount before creating a Stripe PaymentIntent.
- `GET /payments/{payment_id}` retrieves the recorded payment status and amount. Send `X-Payment-Service-Key`; the response does not return the client secret.
- `POST /payments/webhooks/stripe` accepts signed Stripe webhook events. On `payment_intent.succeeded`, it validates the recorded amount/currency and persists a delivery job in the same database transaction as event deduplication before acknowledging Stripe. A background worker confirms the booking, creates an idempotent receipt snapshot, looks up the verified customer email, and queues a receipt email.
- The PostgreSQL outbox uses worker leases, `FOR UPDATE SKIP LOCKED`, and exponential retry delays (30 seconds to one hour). Jobs stop after 20 failed attempts and remain visible for operational recovery. `GET /payments/internal/delivery-outbox/failed` lists terminal failures; `POST /payments/internal/delivery-outbox/{event_id}/retry` requeues one. Both require `X-Payment-Service-Key`.

If Stripe confirms a charge after its booking hold has expired or can no longer be confirmed, the worker records `succeeded_unapplied` and marks the outbox event for reconciliation. A terminal delivery failure is recorded as `succeeded_delivery_failed`; operators can inspect and requeue it through the internal routes. Refund policy and automated reconciliation of unapplied charges remain open.

Generate a strong random `PAYMENT_SERVICE_API_KEY` and share it only with trusted backend callers. The caller must obtain the booking amount from a trusted server-side source. Payment creation and status lookup require this key; the webhook route uses Stripe signature validation. Use Stripe's client SDK with the returned client secret; never send card numbers through this service.
