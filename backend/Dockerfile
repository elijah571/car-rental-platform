FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    CAR_SERVICE_URL=http://127.0.0.1:8002 \
    PAYMENT_SERVICE_URL=http://127.0.0.1:8004 \
    RECEIPT_SERVICE_URL=http://127.0.0.1:8005 \
    AUTH_SERVICE_URL=http://127.0.0.1:8000 \
    NOTIFICATION_SERVICE_URL=http://127.0.0.1:8003 \
    BOOKING_SERVICE_URL=http://127.0.0.1:8001

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx supervisor gettext-base \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app
COPY . /app

RUN for service in auth booking car notification payment receipt; do \
      uv sync --project "/app/services/${service}-service" --locked --no-dev; \
    done \
    && rm -f /etc/nginx/sites-enabled/default

COPY deploy/nginx.conf.template /etc/nginx/templates/backend.conf.template
COPY deploy/supervisord.conf /etc/supervisor/conf.d/backend.conf
COPY deploy/start.sh /usr/local/bin/start-backend
RUN chmod +x /usr/local/bin/start-backend

EXPOSE 10000
CMD ["/usr/local/bin/start-backend"]
