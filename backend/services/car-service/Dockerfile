FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace/services/car-service

COPY shared/platform-security /workspace/shared/platform-security
COPY services/car-service/pyproject.toml services/car-service/uv.lock services/car-service/README.md ./
COPY services/car-service/app ./app
COPY services/car-service/alembic.ini ./alembic.ini
COPY services/car-service/alembic ./alembic

RUN pip install --no-cache-dir uv \
    && uv sync --locked --no-dev

EXPOSE 8002

CMD ["sh", "-c", "uv run --locked --no-sync alembic upgrade head && exec uv run --locked --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8002"]
