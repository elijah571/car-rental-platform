# Car Rental Booking Service

Booking lifecycle API for the Car Rental Platform. Local auth-service access tokens identify customers, the vehicle catalog supplies the booked vehicle snapshot, and PostgreSQL protects each car's time window.

## Development

Install dependencies and start the service from this directory:

```bash
uv sync --locked
uv run --locked uvicorn app.main:app --reload --port 8001
```

Configure `DATABASE_URL` or `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` in the repository environment. Apply this service's migrations with:

```bash
uv run --locked alembic upgrade head
```

Set the shared `JWT_SECRET` in `.env` to enable authenticated booking routes. The API runs at <http://127.0.0.1:8001>, with OpenAPI docs at <http://127.0.0.1:8001/docs>. `/health` reports process liveness and `/ready` checks the database and bookings schema.

## Endpoints

- `GET /bookings/availability?pickup_at=...&return_at=...` lists active vehicles without a blocking booking for the timezone-aware rental window and includes the server-calculated USD total.
- `POST /bookings` creates a pending payment hold for the authenticated customer. The caller supplies only the vehicle and rental window; price and vehicle details are loaded and snapshotted server-side.
- `GET /bookings` lists only the authenticated customer's bookings with `limit` and `offset` pagination.
- `GET /bookings/{booking_id}` gets one booking.
- `GET /bookings/{booking_id}/receipt` returns the stored receipt for the authenticated booking owner (or a platform administrator). The booking service checks access first, then retrieves the receipt from the receipt service using its internal service key.
- `POST /bookings/{booking_id}/cancel` is restricted to the local `platform-admin` role and only cancels unpaid holds while refund policy remains undecided.
- `POST /bookings/{booking_id}/payment-intent` starts checkout for the authenticated owner. Send an `Idempotency-Key` header. The booking service checks ownership and hold expiration; the payment service reads the saved amount directly from the booking service. A client cannot choose the amount.
- `POST /bookings/{booking_id}/start`, `POST /bookings/{booking_id}/return`, and `POST /bookings/{booking_id}/inspection` manage the rental lifecycle. They currently require the local `platform-admin` role; that is a provisional role choice pending the product permission matrix. A car remains blocked through failed inspection and becomes available only after an approved inspection and the scheduled rental end.

Rental prices use each vehicle's USD daily rate, prorated to the selected duration and rounded to cents with `ROUND_HALF_UP`. Rentals must be longer than zero and cannot exceed seven days. Holds expire after 15 minutes. A worker expires holds every 15 seconds, and the database uses a PostgreSQL GiST exclusion constraint to prevent overlapping blocking bookings under concurrency. Set `CAR_SERVICE_URL` when running outside local development.
