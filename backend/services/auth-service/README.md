# Auth service

Local email and password authentication for the Car Rental Platform. PostgreSQL stores account records and PBKDF2 password hashes. Redis stores expiring email verification codes and rotating refresh tokens. Signed HS256 access tokens are validated by the car and booking services using the shared `JWT_SECRET`.

## Configuration

Set `POSTGRES_*`, `JWT_SECRET`, `JWT_REFRESH_SECRET`, `SMTP_HOST`, `SMTP_PORT`, `EMAIL_USER`, and `EMAIL_PASS` in the repository `.env`. Use randomly generated JWT secrets of at least 32 characters. Local Compose points the service at its local Redis container. For a production Compose deployment, set `AUTH_REDIS_URL` to the managed Redis TLS URL; for direct local service runs, `REDIS_URL` selects Redis. `PLATFORM_ADMIN_EMAILS` is a comma separated allowlist. Matching accounts receive the `platform-admin` role after they verify their email.

Local verification codes are returned by the API only when SMTP is not configured, `AUTH_ALLOW_DEV_VERIFICATION_CODE=true`, and `NODE_ENV` is not `production`.

Start PostgreSQL and Redis with `docker compose up -d postgres redis`, then start auth-service with `docker compose up --build auth-service`. The container runs Alembic migrations before starting FastAPI. API docs are at <http://127.0.0.1:8000/docs>.

## Endpoints

- `POST /auth/register` — create an account and send a six digit verification code.
- `POST /auth/confirm` — verify an email using the code; codes expire after ten minutes and allow five attempts.
- `POST /auth/resend-code` — resend a code, limited to one request per minute.
- `POST /auth/login` — verify credentials and return an access token and refresh token.
- `POST /auth/refresh` — rotate a refresh token and return a new token pair.
- `POST /auth/logout` — revoke the supplied refresh token.
- `GET /auth/internal/users/{auth_subject}/contact` — service-key-protected lookup for verified customer email addresses.
- `GET /health` and `GET /ready` — process liveness and PostgreSQL/Redis readiness.

For local admin bootstrap, run `uv run --project backend/services/auth-service python -m app.seed_admin`. The command accepts only addresses in `PLATFORM_ADMIN_EMAILS` and prompts for the password without echoing it.

The previous Cognito implementation remains in `app/services/cognito.py` for a future provider migration; it is not imported by the active API.
