#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ] && {
  [ -z "${POSTGRES_USER:-}" ] ||
  [ -z "${POSTGRES_PASSWORD:-}" ] ||
  [ -z "${POSTGRES_DB:-}" ] ||
  [ -z "${POSTGRES_HOST:-}" ] ||
  [ -z "${POSTGRES_PORT:-}" ];
}; then
  echo >&2 "ERROR: Database configuration is missing. Set DATABASE_URL to the Render PostgreSQL Internal Database URL, or provide all POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, and POSTGRES_PORT variables."
  exit 1
fi

: "${PORT:=10000}"
export PORT
envsubst '${PORT}' < /etc/nginx/templates/backend.conf.template > /etc/nginx/sites-enabled/backend.conf
nginx -t

for service in auth booking car notification payment receipt; do
  service_dir="/app/services/${service}-service"
  echo "Running ${service} database migrations"
  (cd "$service_dir" && uv run --locked --no-sync alembic upgrade head)
done

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
