"""Prometheus metrics for observability."""

from prometheus_client import Counter, Histogram

# HTTP request metrics (handled by instrumentator, but we add custom labels)
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_custom_total",
    "Total HTTP requests by path, method, and status",
    ["path", "method", "status"],
)

# Queue metrics
QUEUE_ENQUEUED_TOTAL = Counter(
    "queue_enqueued_total",
    "Total events enqueued to Redis Streams",
    ["event_type"],
)

QUEUE_DUPLICATE_TOTAL = Counter(
    "queue_duplicate_total",
    "Total duplicate events detected",
    ["event_type"],
)

# Worker metrics
WORKER_PROCESSED_TOTAL = Counter(
    "worker_processed_total",
    "Total events processed by worker",
    ["event_type", "result"],  # result: success, retry, dlq
)

WORKER_RETRY_TOTAL = Counter(
    "worker_retry_total",
    "Total retry attempts",
    ["event_type"],
)

WORKER_DLQ_TOTAL = Counter(
    "worker_dlq_total",
    "Total events moved to DLQ",
    ["event_type", "reason"],
)

# AppsFlyer metrics
APPSFLYER_REQUESTS_TOTAL = Counter(
    "appsflyer_requests_total",
    "Total requests to AppsFlyer API",
    ["event_type", "status_code"],
)

APPSFLYER_LATENCY_SECONDS = Histogram(
    "appsflyer_latency_seconds",
    "AppsFlyer API request latency in seconds",
    ["event_type"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Rate limiting metrics
RATE_LIMIT_BLOCKED_TOTAL = Counter(
    "rate_limit_blocked_total",
    "Total requests blocked by rate limiting",
    ["identifier_type"],  # token, ip
)

# Deduplication metrics
DEDUP_CHECK_TOTAL = Counter(
    "dedup_check_total",
    "Total deduplication checks",
    ["result"],  # new, duplicate
)


def record_enqueue(event_type: str) -> None:
    """Record event enqueue."""
    QUEUE_ENQUEUED_TOTAL.labels(event_type=event_type).inc()


def record_duplicate(event_type: str) -> None:
    """Record duplicate event detected."""
    QUEUE_DUPLICATE_TOTAL.labels(event_type=event_type).inc()


def record_processed(event_type: str, result: str) -> None:
    """Record event processing result."""
    WORKER_PROCESSED_TOTAL.labels(event_type=event_type, result=result).inc()


def record_retry(event_type: str) -> None:
    """Record retry attempt."""
    WORKER_RETRY_TOTAL.labels(event_type=event_type).inc()


def record_dlq(event_type: str, reason: str) -> None:
    """Record event moved to DLQ."""
    WORKER_DLQ_TOTAL.labels(event_type=event_type, reason=reason).inc()


def record_appsflyer_request(event_type: str, status_code: int | str) -> None:
    """Record AppsFlyer API request."""
    APPSFLYER_REQUESTS_TOTAL.labels(
        event_type=event_type,
        status_code=str(status_code),
    ).inc()


def record_appsflyer_latency(event_type: str, latency: float) -> None:
    """Record AppsFlyer API latency."""
    APPSFLYER_LATENCY_SECONDS.labels(event_type=event_type).observe(latency)


def record_rate_limit_blocked(identifier_type: str) -> None:
    """Record rate limit blocked request."""
    RATE_LIMIT_BLOCKED_TOTAL.labels(identifier_type=identifier_type).inc()


def record_dedup_check(result: str) -> None:
    """Record deduplication check result."""
    DEDUP_CHECK_TOTAL.labels(result=result).inc()
