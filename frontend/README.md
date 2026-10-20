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

Browse to <http://localhost:5173>. Vite proxies `/api/auth`, `/api/cars`, and `/api/bookings` to the local FastAPI services. Root `.env` is loaded by Vite; leave `VITE_AUTH_API_URL`, `VITE_CAR_API_URL`, and `VITE_BOOKING_API_URL` blank to use the proxy. Set `VITE_STRIPE_PUBLISHABLE_KEY` (or `STRIPE_PUBLISHABLE_KEY`) to a Stripe test publishable key for Payment Element checkout.

Registration, email verification, and login use local auth-service accounts backed by PostgreSQL, Redis, and SMTP. Availability, booking creation, receipt retrieval, and the administrator booking/inspection queue call booking-service; inventory is loaded and managed through car-service. Payment begins with a booking-service request and uses Stripe.js for the card flow. A browser redirect only starts a status refresh; the booking is considered confirmed by the UI after the backend receives and verifies Stripe's webhook. Administrator vehicle and booking routes require the `platform-admin` role on the backend.

## Production API URLs

For a deployed frontend, set `VITE_AUTH_API_URL`, `VITE_CAR_API_URL`, and `VITE_BOOKING_API_URL` to the browser-reachable API base URLs ending in `/auth`, `/vehicles`, and `/bookings`. Configure `CORS_ALLOWED_ORIGINS` on auth, car, and booking services with the deployed frontend origin. Never put service-to-service API keys or Stripe secret keys in Vite variables.
