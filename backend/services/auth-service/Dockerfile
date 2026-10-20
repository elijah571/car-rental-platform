FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/auth-service/pyproject.toml services/auth-service/uv.lock services/auth-service/README.md ./
COPY services/auth-service/app ./app
COPY services/auth-service/alembic.ini ./alembic.ini
COPY services/auth-service/alembic ./alembic

RUN pip install --no-cache-dir uv \
    && uv sync --locked --no-dev

EXPOSE 8000

CMD ["sh", "-c", "uv run --locked --no-sync alembic upgrade head && exec uv run --locked --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
