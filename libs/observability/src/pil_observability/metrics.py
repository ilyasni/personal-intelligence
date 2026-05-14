from prometheus_client import CollectorRegistry, Counter, Histogram

metrics_registry = CollectorRegistry()

ingest_messages_total = Counter(
    "pil_ingest_messages_total",
    "Total Telegram messages received by ingestor",
    ["kind", "allowed"],
    registry=metrics_registry,
)

ingest_failures_total = Counter(
    "pil_ingest_failures_total",
    "Total ingestion failures by stage",
    ["stage"],
    registry=metrics_registry,
)

pipeline_duration_seconds = Histogram(
    "pil_pipeline_duration_seconds",
    "Event processing duration by service",
    ["service", "stream"],
    registry=metrics_registry,
)
