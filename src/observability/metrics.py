"""Prometheus metrics definitions for the Art agent.

Defines all application-level counters, histograms, and gauges that are
scraped by Prometheus at the /metrics endpoint.

Metrics:
  - art_http_requests_total            — Counter: HTTP requests by method, endpoint, status
  - art_http_request_duration_seconds  — Histogram: HTTP request latency
  - art_http_active_connections        — Gauge: currently in-flight HTTP requests
  - art_messages_received_total        — Counter: WeChat messages received
  - art_tasks_created_total            — Counter: tasks created
  - art_push_results_total             — Counter: WeChat push successes/failures
  - art_intent_parse_duration_seconds  — Histogram: intent parsing latency
  - art_llm_call_duration_seconds      — Histogram: LLM API call latency
  - art_mcp_call_duration_seconds      — Histogram: MCP tool call latency
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── HTTP request metrics ──────────────────────────────────────────────────────

http_requests_total = Counter(
    "art_http_requests_total",
    "Total number of HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "art_http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

http_active_connections = Gauge(
    "art_http_active_connections",
    "Number of currently in-flight HTTP requests",
)

# ── Business counters ────────────────────────────────────────────────────────

messages_received_total = Counter(
    "art_messages_received_total",
    "Total number of WeChat messages received",
    labelnames=["msg_type"],
)

tasks_created_total = Counter(
    "art_tasks_created_total",
    "Total number of tasks created",
    labelnames=["priority"],
)

push_results_total = Counter(
    "art_push_results_total",
    "Total number of WeChat push results",
    labelnames=["push_type", "result"],  # result: "success" | "failure"
)

# ── Histograms ───────────────────────────────────────────────────────────────

intent_parse_duration_seconds = Histogram(
    "art_intent_parse_duration_seconds",
    "Intent parsing latency in seconds",
    labelnames=["status"],  # "success" | "error" | "timeout"
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

llm_call_duration_seconds = Histogram(
    "art_llm_call_duration_seconds",
    "LLM API call latency in seconds",
    labelnames=["provider", "model", "status"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

mcp_call_duration_seconds = Histogram(
    "art_mcp_call_duration_seconds",
    "MCP tool call latency in seconds",
    labelnames=["tool_name", "status"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
