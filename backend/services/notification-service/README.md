# Car Rental Notification Service

Email notification delivery for the Car Rental Platform, using the configured SMTP server. An optional SES sender is retained for a future deployment migration but is not used by the active worker.

## Development

Run these commands from this directory:

```bash
uv sync --locked
uv run --locked uvicorn app.main:app --reload --port 8003
```

Configure `DATABASE_URL` or `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` in the repository environment. Apply the notification service migration:

```bash
uv run --locked alembic upgrade head
```

Set `SMTP_HOST`, `SMTP_PORT`, `EMAIL_USER`, `EMAIL_PASS`, and optionally `EMAIL_FROM` for delivery. Port 465 uses implicit TLS; other configured ports use STARTTLS.

The API runs at <http://127.0.0.1:8003>; interactive docs are at <http://127.0.0.1:8003/docs>. `/health` reports liveness and `/ready` checks the notification table.

## API

- `POST /notifications/email` queues an email and returns its delivery status. Include `X-Notification-Service-Key`, a unique `Idempotency-Key` header (1–128 characters), and JSON with `recipient`, `subject`, and at least one of `text_body` or `html_body`. Include both bodies for multipart emails so recipients who cannot display HTML still receive a readable message; the platform sends branded HTML and text versions for verification, password reset, and receipts.
- `GET /notifications/{notification_id}` retrieves delivery status using the service key.

Repeated requests with the same idempotency key and content return the original notification record; reusing the key with different content returns 409. Message bodies are retained in the database with the delivery record. A worker claims queued emails with PostgreSQL row locks and leases and retries failures with exponential backoff from 30 seconds to one hour. Delivery is at least once: a process crash after SMTP accepts a message but before the database records success can result in a duplicate email. SMTP failures leave messages queued for retry.
