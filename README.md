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

The backend is configured as a Render Blueprint in [`render.yaml`](render.yaml). It creates six services, a managed PostgreSQL database, and Redis-compatible Key Value storage. Auth, car, booking, and payment are public HTTP services; notification and receipt remain private and are called over Render's private network. Each service runs its own migrations at startup. Review the plan and region choices in Render before creating the Blueprint.

1. Push this repository to a Git provider and create a new Render Blueprint from it. Render will prompt for values marked `sync: false`.
2. Set `PLATFORM_ADMIN_EMAILS` to the administrator email and `CORS_ALLOWED_ORIGINS` to the exact deployed Vercel origin (for example, `https://your-project.vercel.app`) for auth, car, and booking. No trailing slash; add a comma-separated custom domain if you use one too.
3. Enter production SMTP credentials for auth and notification. Set live Stripe values on `drivewell-payment`; use the same live publishable key in Vercel and register `https://<drivewell-payment-host>/payments/webhooks/stripe` as the Stripe webhook endpoint. Subscribe to `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled`, `payment_intent.processing`, and `payment_intent.requires_action`.
4. Deploy the services and copy the external URLs for auth, car, booking, and payment from Render. The first three URLs are used by the browser; payment receives Stripe webhooks directly.
5. Create a Vercel project for this repository and set its **Root Directory** to `frontend`. Use `npm install` (or `npm ci`) as the install command, `npm run build` as the build command, and `dist` as the output directory. [`frontend/vercel.json`](frontend/vercel.json) routes deep links such as `/cars` and `/account` to the SPA.
6. Add these Vercel environment variables for Production (and Preview only if you also configure preview API origins):

   | Variable | Value |
   | --- | --- |
   | `VITE_AUTH_API_URL` | `https://<drivewell-auth-host>` |
   | `VITE_CAR_API_URL` | `https://<drivewell-car-host>/vehicles` |
   | `VITE_BOOKING_API_URL` | `https://<drivewell-booking-host>/bookings` |
   | `VITE_STRIPE_PUBLISHABLE_KEY` | Your Stripe live publishable key (`pk_live_…`) |

   Redeploy Vercel after setting or changing these values; Vite embeds them during the build. Only the Stripe publishable key belongs in Vercel. Keep Stripe secret/webhook keys, database credentials, JWT keys, and internal service keys in Render's environment settings.

`prod.env` remains a local, Git-ignored configuration file; do not upload it to either provider. Render generates the shared JWT and internal service secrets from the Blueprint. Keep those Render values backed up securely: rotating `JWT_SECRET` also affects encryption of stored KYC documents. The checked-in `.env.example` is for local development only, and its Stripe credentials are placeholders/test mode.
