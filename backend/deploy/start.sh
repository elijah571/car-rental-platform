#!/bin/sh
set -eu

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
