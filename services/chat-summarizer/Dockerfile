FROM python:3.12-slim AS builder
WORKDIR /build

COPY libs/contracts/ libs/contracts/
COPY libs/llm-client/ libs/llm-client/
COPY libs/observability/ libs/observability/
COPY libs/storage-clients/ libs/storage-clients/
COPY services/chat-summarizer/ services/chat-summarizer/

RUN pip install --no-cache-dir \
      libs/contracts/ \
      libs/llm-client/ \
      libs/observability/ \
      libs/storage-clients/ \
      services/chat-summarizer/

FROM python:3.12-slim
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

CMD ["python", "-m", "chat_summarizer"]
