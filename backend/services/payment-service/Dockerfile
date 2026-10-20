FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/payment-service/pyproject.toml services/payment-service/uv.lock services/payment-service/README.md ./
COPY services/payment-service/app ./app
COPY services/payment-service/alembic.ini ./alembic.ini
COPY services/payment-service/alembic ./alembic

RUN pip install --no-cache-dir uv \
    && uv sync --locked --no-dev

EXPOSE 8004

CMD ["sh", "-c", "uv run --locked --no-sync alembic upgrade head && exec uv run --locked --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8004}"]
