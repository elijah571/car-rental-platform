FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/notification-service/pyproject.toml services/notification-service/uv.lock services/notification-service/README.md ./
COPY services/notification-service/app ./app
COPY services/notification-service/alembic.ini ./alembic.ini
COPY services/notification-service/alembic ./alembic

RUN pip install --no-cache-dir uv \
    && uv sync --locked --no-dev

EXPOSE 8003

CMD ["sh", "-c", "uv run --locked --no-sync alembic upgrade head && exec uv run --locked --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8003"]
