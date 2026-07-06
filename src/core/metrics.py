"""Métricas Prometheus para monitoramento."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
import time
from functools import wraps

# Métricas
MESSAGES_TOTAL = Counter(
    "chatbot_messages_total",
    "Total de mensagens processadas",
    ["role"],
)

TOKENS_TOTAL = Counter(
    "chatbot_tokens_total",
    "Total de tokens consumidos",
    ["model"],
)

LLM_LATENCY = Histogram(
    "chatbot_llm_latency_seconds",
    "Latência das chamadas LLM",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

ACTIVE_SESSIONS = Gauge(
    "chatbot_active_sessions",
    "Número de sessões ativas",
)

FEEDBACK_COUNTER = Counter(
    "chatbot_feedback_total",
    "Total de feedbacks recebidos",
    ["score"],
)

ERRORS_TOTAL = Counter(
    "chatbot_errors_total",
    "Total de erros",
    ["type"],
)

DOCUMENTS_INGESTED = Counter(
    "chatbot_documents_ingested_total",
    "Total de documentos ingeridos",
)

LATENCY_HISTOGRAM = Histogram(
    "chatbot_latency_seconds",
    "Latência total por rota",
    ["route"],
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

TTFT_HISTOGRAM = Histogram(
    "chatbot_ttft_seconds",
    "Time to first token por rota",
    ["route"],
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)


def track_latency(func):
    """Decorator para medir latência de chamadas LLM."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            LLM_LATENCY.observe(time.time() - start)
    return wrapper


def get_metrics():
    """Retorna métricas no formato Prometheus."""
    return generate_latest(REGISTRY)
