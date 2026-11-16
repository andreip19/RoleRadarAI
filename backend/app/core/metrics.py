from prometheus_client import Counter, Gauge, Histogram


# Total HTTP requests grouped by method, route and status.
HTTP_REQUESTS = Counter(
    "roleradar_http_requests",
    "Total number of HTTP requests.",
    ["method", "route", "status"],
)


# HTTP request duration.
HTTP_REQUEST_DURATION = Histogram(
    "roleradar_http_request_duration_seconds",
    "HTTP request processing duration in seconds.",
    ["method", "route"],
    buckets=(
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)


# Successful and failed ingestion executions.
INGESTION_RUNS = Counter(
    "roleradar_ingestion_runs",
    "Total ingestion executions.",
    ["source", "status"],
)


# Number of jobs processed by ingestion actions.
INGESTION_JOBS = Counter(
    "roleradar_ingestion_jobs",
    "Total jobs processed by ingestion.",
    ["source", "action"],
)


# Duration of each source synchronization.
INGESTION_DURATION = Histogram(
    "roleradar_ingestion_duration_seconds",
    "Ingestion duration per source in seconds.",
    ["source"],
)


# Timestamp of the latest successful ingestion.
INGESTION_LAST_SUCCESS = Gauge(
    "roleradar_ingestion_last_success_timestamp",
    "Unix timestamp of the last successful ingestion.",
    ["source", "board_token"],
)
