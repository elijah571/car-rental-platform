# Drivewell frontend

React + TypeScript + Vite customer booking and fleet inventory screens based on the concepts in the repository root `car_rental_ui_design.pdf`. The existing `frontend/public/cars` photos are used throughout the fleet cards, vehicle details, and rental ticket.

## Local run

Start the backend first from the repository root:

```bash
docker compose up --build
```

Then run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Browse to <http://localhost:5173>. Vite proxies `/api/auth`, `/api/cars`, and `/api/bookings` to the local FastAPI services. The repository-root `.env` is loaded by Vite; leave `VITE_AUTH_API_URL`, `VITE_CAR_API_URL`, and `VITE_BOOKING_API_URL` blank to use the development proxy. Set `VITE_STRIPE_PUBLISHABLE_KEY` (or `STRIPE_PUBLISHABLE_KEY`) to a Stripe test publishable key for Payment Element checkout.

Registration, email verification, and login use local auth-service accounts backed by PostgreSQL, Redis, and SMTP. Availability, booking creation, receipt retrieval, and the administrator booking/inspection queue call booking-service; inventory is loaded and managed through car-service. Payment begins with a booking-service request and uses Stripe.js for the card flow. A browser redirect only starts a status refresh; the booking is considered confirmed by the UI after the backend receives and verifies Stripe's webhook. Administrator vehicle and booking routes require the `platform-admin` role on the backend.

## Independent Vercel deployment

Create a Vercel project for this repository and set its **Root Directory** to `frontend`. The checked-in [`vercel.json`](vercel.json) runs `npm ci`, builds with `npm run build`, serves `dist`, and sends SPA deep links to `index.html`.

Set these variables in Vercel Project Settings → Environment Variables for Production (and Preview if preview deployments need API access):

| Variable | Value |
| --- | --- |
| `VITE_AUTH_API_URL` | `https://<render-host>/api/auth` |
| `VITE_CAR_API_URL` | `https://<render-host>/api/cars` |
| `VITE_BOOKING_API_URL` | `https://<render-host>/api/bookings` |
| `VITE_STRIPE_PUBLISHABLE_KEY` | Stripe publishable key (`pk_test_…` or `pk_live_…`) |

All three API URLs use the same combined Render backend host. The production build stops with a clear error if any API URL is missing. Set `CORS_ALLOWED_ORIGINS` on the Render backend to the exact Vercel site origin (no trailing slash); add a comma-separated custom domain if used. Redeploy Vercel after changing environment variables because Vite embeds them at build time.

For a local production build, copy this directory's `.env.example` values into the repository-root `.env.local`; Vite's `envDir` is the repository root. Environment variables prefixed with `VITE_` are included in the browser bundle, so only use them for public API URLs and the Stripe publishable key. Keep database credentials, JWT secrets, Stripe secret/webhook keys, SMTP credentials, and internal service API keys in Render's environment settings.
