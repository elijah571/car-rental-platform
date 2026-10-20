# Backend

This directory contains the Python 3.12 / FastAPI microservices and the shared platform security package.

## Services

| Service | Responsibility | Local URL |
| --- | --- | --- |
| `services/auth-service` | Amazon Cognito identity flows and user profiles | `http://127.0.0.1:8000` |
| `services/booking-service` | Availability, booking holds, and lifecycle | `http://127.0.0.1:8001` |
| `services/car-service` | Vehicle inventory | `http://127.0.0.1:8002` |
| `services/notification-service` | Email notification delivery | `http://127.0.0.1:8003` |
| `services/payment-service` | Stripe PaymentIntents and verified webhooks | `http://127.0.0.1:8004` |
| `services/receipt-service` | Historical rental ticket snapshots | `http://127.0.0.1:8005` |

Start the complete backend from the repository root with `docker compose up --build`. For an individual service, change into its `services/<name>` directory and use `uv sync --locked`, then `uv run --locked uvicorn app.main:app --reload --port <port>`. Set database and integration configuration in the root `.env` file.

The shared Cognito token validation code is in `shared/platform-security`. GitHub Actions installs each service from its lockfile, applies migrations, checks Alembic alignment, and runs tests.

For local UI development, the ten supplied sample vehicle records can be added idempotently with `uv run --project . python ../../scripts/seed_demo_vehicles.py` from `services/car-service`.
