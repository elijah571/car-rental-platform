FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace/services/booking-service

COPY shared/platform-security /workspace/shared/platform-security
COPY services/booking-service/pyproject.toml services/booking-service/uv.lock services/booking-service/README.md ./
COPY services/booking-service/app ./app
COPY services/booking-service/alembic.ini ./alembic.ini
COPY services/booking-service/alembic ./alembic

RUN pip install --no-cache-dir uv \
    && uv sync --locked --no-dev

EXPOSE 8001

CMD ["sh", "-c", "uv run --locked --no-sync alembic upgrade head && exec uv run --locked --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
