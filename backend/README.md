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

## Deploying all services as one Render Web Service

The root-level `Dockerfile` builds a single container that runs all six services behind an Nginx reverse proxy. In Render, set **Root Directory** to `backend`, **Dockerfile Path** to `./Dockerfile`, and **Docker Build Context Directory** to `.`. Render will route public traffic to the container's `PORT`; the proxy maps `/api/auth`, `/api/cars`, and `/api/bookings` to their services.

Create or select a Render PostgreSQL database in the same region as the Web Service. In the Web Service's **Environment** page, add `DATABASE_URL` using the database's **Internal Database URL** (not `localhost`, port `5433`, or the external URL). The application runs database migrations during container startup, so the service cannot start without a reachable database. Also configure `REDIS_URL`, JWT/API-key secrets, Stripe settings, and email settings there. Set `CORS_ALLOWED_ORIGINS` to a comma-separated list of allowed frontend origins (scheme and hostname only, no trailing slash). The Vercel production and deployment origins are included in the service defaults. If you created the Web Service manually, the database URL is not added automatically; connect it explicitly in the Environment page.

For Vercel, set `VITE_AUTH_API_URL`, `VITE_CAR_API_URL`, and `VITE_BOOKING_API_URL` to `https://<render-host>/api/auth`, `https://<render-host>/api/cars`, and `https://<render-host>/api/bookings` respectively. This single-container layout is intended for a small deployment; each service runs as a separate process inside the same Render instance.

The shared Cognito token validation code is in `shared/platform-security`. GitHub Actions installs each service from its lockfile, applies migrations, checks Alembic alignment, and runs tests.

For local UI development, the ten supplied sample vehicle records can be added idempotently with `uv run --project . python ../../scripts/seed_demo_vehicles.py` from `services/car-service`.
