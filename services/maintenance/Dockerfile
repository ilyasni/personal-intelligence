FROM python:3.12-slim AS builder
WORKDIR /build

COPY libs/contracts/ libs/contracts/
COPY libs/observability/ libs/observability/
COPY libs/storage-clients/ libs/storage-clients/
COPY services/maintenance/ services/maintenance/

RUN pip install --no-cache-dir \
      libs/contracts/ \
      libs/observability/ \
      libs/storage-clients/ \
      services/maintenance/

FROM python:3.12-slim
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

CMD ["python", "-m", "maintenance"]
