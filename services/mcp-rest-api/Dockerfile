FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY libs/contracts /app/libs/contracts
COPY libs/llm-client /app/libs/llm-client
COPY libs/observability /app/libs/observability
COPY libs/storage-clients /app/libs/storage-clients
COPY services/mcp-rest-api /app/services/mcp-rest-api

RUN pip install --upgrade pip && \
    pip install -e /app/libs/contracts -e /app/libs/llm-client -e /app/libs/observability -e /app/libs/storage-clients && \
    pip install -e /app/services/mcp-rest-api

CMD ["python", "-m", "mcp_rest_api"]
