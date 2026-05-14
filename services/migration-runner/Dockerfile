FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY libs/storage-clients /app/libs/storage-clients
COPY migrations /app/migrations

RUN pip install --upgrade pip && \
    pip install -e /app/libs/storage-clients psycopg2-binary

ENTRYPOINT ["alembic", "-c", "migrations/alembic.ini"]
