# Drivewell Car Rental Platform

The repository is split into a browser frontend and a Python microservice backend:

- [`frontend/`](frontend/README.md) — React, TypeScript, and Vite customer and operations UI based on [`car_rental_ui_design.pdf`](car_rental_ui_design.pdf).
- [`backend/`](backend/README.md) — FastAPI services for identity, cars, bookings, payments, receipts, and notifications.
- `compose.yaml` — local PostgreSQL, Redis, and all six backend APIs.

## Run locally

Copy `.env.example` to `.env`, set PostgreSQL credentials and integration credentials, then start the backend:

```bash
docker compose up --build
```

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite development server proxies browser API calls to auth-service on port 8000, car-service on port 8002, and booking-service on port 8001. Registration and sign-in use the local auth service, PostgreSQL, Redis, and configured SMTP credentials. `PLATFORM_ADMIN_EMAILS` grants the platform-admin role after verification. Set `STRIPE_PUBLISHABLE_KEY` and `STRIPE_SECRET_KEY` in `.env` and `STRIPE_WEBHOOK_SECRET` from Stripe CLI to test checkout and payment confirmation.

To load the ten supplied car photos as local development inventory, run `uv run --project . python ../../scripts/seed_demo_vehicles.py` from `backend/services/car-service` after the backend is up.

The customer UI lists vehicles from car-service, checks the selected time window through booking-service, creates a server-priced 15-minute booking hold, requests a Stripe payment intent, and retrieves the issued ticket through the authenticated booking API. Vehicle inventory management is in the Operations workspace and requires a local auth token with the `platform-admin` role.

Customer accounts can create support tickets and continue threaded conversations from **Help & support**. Administrators can manage ticket status, priority, assignment, replies, and removal in the Operations workspace. The same workspace lists customer accounts and manages account roles and access. Account settings include password changes; the sign-in dialog provides email-code password recovery.

To run the Chrome browser smoke check against a running local stack and Vite server, set credentials for a local administrator and run:

```bash
cd frontend
E2E_ADMIN_EMAIL=admin@example.com E2E_ADMIN_PASSWORD='your local admin password' npm run test:e2e
```

The smoke check creates a temporary vehicle and ticket; the vehicle is retired after the check to preserve inventory history, and the ticket is deleted.

## API documentation

| Service | URL | Documentation |
| --- | --- | --- |
| Auth | <http://127.0.0.1:8000> | <http://127.0.0.1:8000/docs> |
| Booking | <http://127.0.0.1:8001> | <http://127.0.0.1:8001/docs> |
| Car inventory | <http://127.0.0.1:8002> | <http://127.0.0.1:8002/docs> |
| Notification | <http://127.0.0.1:8003> | <http://127.0.0.1:8003/docs> |
| Payment | <http://127.0.0.1:8004> | <http://127.0.0.1:8004/docs> |
| Receipt | <http://127.0.0.1:8005> | <http://127.0.0.1:8005/docs> |

Each API exposes `/health` and `/ready`. See [`PROJECT_SPECIFICATION.md`](PROJECT_SPECIFICATION.md) for requirements, status, and open deployment and policy decisions.
# Deploy to Render and Vercel

The backend can run as one Render Web Service using [`backend/Dockerfile`](backend/Dockerfile). In the Render dashboard set **Root Directory** to `backend`, **Dockerfile Path** to `Dockerfile`, and **Docker Build Context Directory** to `.`. Configure a Render PostgreSQL database and Redis-compatible Key Value service, then add the runtime variables described in [`backend/README.md`](backend/README.md). Set `CORS_ALLOWED_ORIGINS` to the exact Vercel site origin, without a trailing slash.

Create a Vercel project for this repository with **Root Directory** `frontend`. [`frontend/vercel.json`](frontend/vercel.json) sets `npm ci`, `npm run build`, and `dist`, and routes app deep links to the SPA. Add the following variables for Production in Vercel Project Settings → Environment Variables (and Preview only when needed):

| Variable | Value |
| --- | --- |
| `VITE_AUTH_API_URL` | `https://<render-host>/api/auth` |
| `VITE_CAR_API_URL` | `https://<render-host>/api/cars` |
| `VITE_BOOKING_API_URL` | `https://<render-host>/api/bookings` |
| `VITE_STRIPE_PUBLISHABLE_KEY` | Stripe publishable key (`pk_test_…` or `pk_live_…`) |

All API URLs use the same Render host. Redeploy Vercel after changing them because Vite embeds the values at build time. Only public API URLs and the Stripe publishable key belong in Vercel. Keep database credentials, JWT secrets, Stripe secret and webhook keys, SMTP credentials, and internal service API keys in Render's environment settings. A frontend environment template is in [`frontend/.env.example`](frontend/.env.example); for local Vite production builds, copy its values into the repository-root `.env.local`. Never commit `.env.local` or `prod.env`.
