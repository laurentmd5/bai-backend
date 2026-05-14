# app/core/metrics.py
"""
Prometheus metrics module for BARROW.AI.
Comprehensive observability with structured metrics for all components.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
from typing import Dict, Any
import time


# =========================================================================
# Existing chat metrics (preserved for compatibility)
# =========================================================================
chat_messages_total = Counter(
    'barrow_chat_messages_total',
    'Total number of chat messages',
    ['channel', 'language', 'cache_hit']
)

chat_errors_total = Counter(
    'barrow_chat_errors_total',
    'Total number of chat errors',
    ['error_type']
)

chat_latency_ms = Histogram(
    'barrow_chat_latency_ms',
    'Chat response latency in milliseconds',
    ['channel'],
    buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)
)

# RAG metrics
rag_fallbacks_total = Counter(
    'barrow_rag_fallbacks_total',
    'Total number of RAG fallbacks'
)

rag_search_duration_ms = Histogram(
    'barrow_rag_search_duration_ms',
    'Qdrant search duration',
    buckets=(1, 5, 10, 25, 50, 100, 250, 500)
)

# LLM metrics
llm_generation_duration_ms = Histogram(
    'barrow_llm_generation_duration_ms',
    'LLM generation duration',
    ['provider'],
    buckets=(100, 250, 500, 1000, 2500, 5000, 10000, 15000)
)

# Session metrics
active_sessions_total = Gauge(
    'barrow_active_sessions_total',
    'Number of active sessions',
    ['channel']
)

# Cache metrics
cache_hit_ratio = Gauge(
    'barrow_cache_hit_ratio',
    'Cache hit ratio (0-100)'
)

# WhatsApp metrics
whatsapp_messages_total = Counter(
    'barrow_whatsapp_messages_total',
    'Total WhatsApp messages',
    ['direction']
)

whatsapp_optouts_total = Counter(
    'barrow_whatsapp_optouts_total',
    'Total WhatsApp opt-outs'
)

# Admin metrics
admin_logins_total = Counter(
    'barrow_admin_logins_total',
    'Total admin login attempts',
    ['result']
)

# =========================================================================
# New HTTP metrics for comprehensive observability
# =========================================================================
http_requests_total = Counter(
    'barrow_http_requests_total',
    'Total HTTP requests by method, endpoint, and status',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'barrow_http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
)

# =========================================================================
# New WhatsApp audio/voice metrics
# =========================================================================
whatsapp_messages_received_total = Counter(
    'barrow_whatsapp_messages_received_total',
    'Total WhatsApp messages received by type',
    ['type']  # text, voice, image, etc.
)

voice_message_processed_total = Counter(
    'barrow_voice_message_processed_total',
    'Voice message processing outcome',
    ['status']  # success, transcription_failed, tts_failed, upload_failed
)

# =========================================================================
# New audio processing metrics
# =========================================================================
whisper_transcription_duration_seconds = Histogram(
    'barrow_whisper_transcription_duration_seconds',
    'Whisper transcription latency in seconds',
    buckets=(0.5, 1, 2, 3, 5, 8, 10, 15, 20)
)

tts_synthesis_duration_seconds = Histogram(
    'barrow_tts_synthesis_duration_seconds',
    'Edge TTS synthesis latency in seconds',
    buckets=(0.5, 1, 2, 3, 5, 8, 10)
)

rag_retrieval_duration_seconds = Histogram(
    'barrow_rag_retrieval_duration_seconds',
    'RAG retrieval latency in seconds (Qdrant search)',
    buckets=(0.1, 0.25, 0.5, 1, 2, 5)
)

# =========================================================================
# Error tracking
# =========================================================================
error_total = Counter(
    'barrow_error_total',
    'Total errors by type and endpoint',
    ['error_type', 'endpoint']
)


def get_metrics() -> Dict[str, Any]:
    """Get current metrics in Prometheus format."""
    return {
        'status': 'ok',
        'metrics_available': True,
    }


def record_chat_message(channel: str, language: str, cache_hit: bool):
    """Record a chat message."""
    chat_messages_total.labels(
        channel=channel,
        language=language,
        cache_hit=str(cache_hit).lower()
    ).inc()


def record_chat_latency(channel: str, latency_ms: float):
    """Record chat latency."""
    chat_latency_ms.labels(channel=channel).observe(latency_ms)


def record_chat_error(error_type: str):
    """Record a chat error."""
    chat_errors_total.labels(error_type=error_type).inc()


def record_rag_fallback():
    """Record a RAG fallback."""
    rag_fallbacks_total.inc()


def record_rag_search_duration(duration_ms: float):
    """Record RAG search duration."""
    rag_search_duration_ms.observe(duration_ms)


def record_llm_duration(provider: str, duration_ms: float):
    """Record LLM generation duration."""
    llm_generation_duration_ms.labels(provider=provider).observe(duration_ms)


def update_active_sessions(channel: str, count: int):
    """Update active sessions gauge."""
    active_sessions_total.labels(channel=channel).set(count)


def update_cache_hit_ratio(ratio: float):
    """Update cache hit ratio."""
    cache_hit_ratio.set(ratio)


def record_whatsapp_message(direction: str):
    """Record WhatsApp message."""
    whatsapp_messages_total.labels(direction=direction).inc()


def record_whatsapp_optout():
    """Record WhatsApp opt-out."""
    whatsapp_optouts_total.inc()


def record_admin_login(result: str):
    """Record admin login attempt."""
    admin_logins_total.labels(result=result).inc()


# =========================================================================
# Metrics endpoint for Prometheus scraping
# =========================================================================
def metrics_endpoint():
    """FastAPI endpoint to expose Prometheus metrics."""
    from fastapi import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


class MetricsContext:
    """Context manager for timing operations."""
    
    def __init__(self, metric_name: str):
        self.metric_name = metric_name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        # Record to appropriate metric based on name
        if self.metric_name == 'rag_search':
            rag_search_duration_ms.observe(duration_ms)
        elif self.metric_name == 'chat':
            chat_latency_ms.labels(channel='unknown').observe(duration_ms)