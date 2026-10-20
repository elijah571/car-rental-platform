FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/receipt-service/pyproject.toml services/receipt-service/uv.lock services/receipt-service/README.md ./
COPY services/receipt-service/app ./app
COPY services/receipt-service/alembic.ini ./alembic.ini
COPY services/receipt-service/alembic ./alembic

RUN pip install --no-cache-dir uv \
    && uv sync --locked --no-dev

EXPOSE 8005

CMD ["sh", "-c", "uv run --locked --no-sync alembic upgrade head && exec uv run --locked --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8005"]
