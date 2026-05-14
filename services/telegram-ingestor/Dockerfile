FROM python:3.12-slim AS builder

WORKDIR /build

# Копируем локальные lib-пакеты
COPY libs/contracts/           libs/contracts/
COPY libs/observability/       libs/observability/
COPY libs/storage-clients/     libs/storage-clients/

# Копируем сервис
COPY services/telegram-ingestor/ services/telegram-ingestor/

# Устанавливаем всё одним слоем (libs → service)
RUN pip install --no-cache-dir \
      libs/contracts/ \
      libs/observability/ \
      libs/storage-clients/ \
      services/telegram-ingestor/

FROM python:3.12-slim

# Копируем site-packages из builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

CMD ["python", "-m", "telegram_ingestor"]
