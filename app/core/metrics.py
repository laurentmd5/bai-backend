# app/core/metrics.py
"""
Prometheus metrics module for Company Bot.
Comprehensive observability with structured metrics for all components.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
from typing import Dict, Any
import time


# =========================================================================
# Existing chat metrics (preserved for compatibility)
# =========================================================================
chat_messages_total = Counter(
    'bot_chat_messages_total',
    'Total number of chat messages',
    ['channel', 'language', 'cache_hit']
)

chat_errors_total = Counter(
    'bot_chat_errors_total',
    'Total number of chat errors',
    ['error_type']
)

chat_latency_ms = Histogram(
    'bot_chat_latency_ms',
    'Chat response latency in milliseconds',
    ['channel'],
    buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)
)

# RAG metrics
rag_fallbacks_total = Counter(
    'bot_rag_fallbacks_total',
    'Total number of RAG fallbacks'
)

rag_search_duration_ms = Histogram(
    'bot_rag_search_duration_ms',
    'Qdrant search duration',
    buckets=(1, 5, 10, 25, 50, 100, 250, 500)
)

# LLM metrics
llm_generation_duration_ms = Histogram(
    'bot_llm_generation_duration_ms',
    'LLM generation duration',
    ['provider'],
    buckets=(100, 250, 500, 1000, 2500, 5000, 10000, 15000)
)

# Session metrics
active_sessions_total = Gauge(
    'bot_active_sessions_total',
    'Number of active sessions',
    ['channel']
)

# Cache metrics
cache_hit_ratio = Gauge(
    'bot_cache_hit_ratio',
    'Cache hit ratio (0-100)'
)

# WhatsApp metrics
whatsapp_messages_total = Counter(
    'bot_whatsapp_messages_total',
    'Total WhatsApp messages',
    ['direction']
)

whatsapp_optouts_total = Counter(
    'bot_whatsapp_optouts_total',
    'Total WhatsApp opt-outs'
)

# Admin metrics
admin_logins_total = Counter(
    'bot_admin_logins_total',
    'Total admin login attempts',
    ['result']
)

# =========================================================================
# New HTTP metrics for comprehensive observability
# =========================================================================
http_requests_total = Counter(
    'bot_http_requests_total',
    'Total HTTP requests by method, endpoint, and status',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'bot_http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
)

# =========================================================================
# New WhatsApp audio/voice metrics
# =========================================================================
whatsapp_messages_received_total = Counter(
    'bot_whatsapp_messages_received_total',
    'Total WhatsApp messages received by type',
    ['type']  # text, voice, image, etc.
)

voice_message_processed_total = Counter(
    'bot_voice_message_processed_total',
    'Voice message processing outcome',
    ['status']  # success, transcription_failed, tts_failed, upload_failed
)

# =========================================================================
# New audio processing metrics
# =========================================================================
whisper_transcription_duration_seconds = Histogram(
    'bot_whisper_transcription_duration_seconds',
    'Whisper transcription latency in seconds',
    buckets=(0.5, 1, 2, 3, 5, 8, 10, 15, 20)
)

tts_synthesis_duration_seconds = Histogram(
    'bot_tts_synthesis_duration_seconds',
    'Edge TTS synthesis latency in seconds',
    buckets=(0.5, 1, 2, 3, 5, 8, 10)
)

rag_retrieval_duration_seconds = Histogram(
    'bot_rag_retrieval_duration_seconds',
    'RAG retrieval latency in seconds (Qdrant search)',
    buckets=(0.1, 0.25, 0.5, 1, 2, 5)
)

# =========================================================================
# Error tracking
# =========================================================================
error_total = Counter(
    'bot_error_total',
    'Total errors by type and endpoint',
    ['error_type', 'endpoint']
)


# =========================================================================
# SRE Golden Signals & Capacity Metrics
# =========================================================================
http_requests_in_flight = Gauge(
    'bot_http_requests_in_flight',
    'Current in-flight HTTP requests being processed',
    ['method']
)

llm_tokens_total = Counter(
    'bot_llm_tokens_total',
    'Total LLM tokens consumed by provider, model and type (prompt/completion)',
    ['provider', 'model', 'type']
)

rag_chunks_retrieved = Histogram(
    'bot_rag_chunks_retrieved',
    'Number of chunks retrieved per RAG vector search query',
    buckets=(0, 1, 2, 3, 5, 8, 10, 15, 20)
)

security_violations_total = Counter(
    'bot_security_violations_total',
    'Total security guardrail violations detected by type',
    ['violation_type']
)

db_pool_connections = Gauge(
    'bot_db_pool_connections',
    'Database connection pool status',
    ['state']
)

recruitment_applications_total = Counter(
    'bot_recruitment_applications_total',
    'Total candidate applications processed by channel and status',
    ['channel', 'status']
)

recruitment_cv_parsed_total = Counter(
    'bot_recruitment_cv_parsed_total',
    'Total candidate CV documents parsed by status',
    ['status']
)


def record_recruitment_application(channel: str = "whatsapp", status: str = "completed"):
    """Record a recruitment application submission."""
    try:
        recruitment_applications_total.labels(channel=channel, status=status).inc()
    except Exception:
        pass


def record_cv_parsed(status: str = "success"):
    """Record a CV document parsing event."""
    try:
        recruitment_cv_parsed_total.labels(status=status).inc()
    except Exception:
        pass



def get_metrics() -> Dict[str, Any]:
    """Get current metrics in Prometheus format."""
    return {
        'status': 'ok',
        'metrics_available': True,
    }


def record_chat_message(channel: str, language: str, cache_hit: bool):
    """Record a chat message."""
    try:
        chat_messages_total.labels(
            channel=channel,
            language=language,
            cache_hit=str(cache_hit).lower()
        ).inc()
    except Exception:
        pass


def record_chat_latency(channel: str, latency_ms: float):
    """Record chat latency."""
    try:
        chat_latency_ms.labels(channel=channel).observe(latency_ms)
    except Exception:
        pass


def record_chat_error(error_type: str):
    """Record a chat error."""
    try:
        chat_errors_total.labels(error_type=error_type).inc()
    except Exception:
        pass


def record_rag_fallback():
    """Record a RAG fallback."""
    try:
        rag_fallbacks_total.inc()
    except Exception:
        pass


def record_rag_search_duration(duration_ms: float):
    """Record RAG search duration."""
    try:
        rag_search_duration_ms.observe(duration_ms)
        rag_retrieval_duration_seconds.observe(duration_ms / 1000.0)
    except Exception:
        pass


def record_rag_chunks_retrieved(chunks_count: int):
    """Record number of chunks retrieved."""
    try:
        rag_chunks_retrieved.observe(chunks_count)
    except Exception:
        pass


def record_llm_duration(provider: str, duration_ms: float):
    """Record LLM generation duration."""
    try:
        llm_generation_duration_ms.labels(provider=provider).observe(duration_ms)
    except Exception:
        pass


def record_llm_tokens(provider: str, model: str, prompt_tokens: int, completion_tokens: int):
    """Record prompt and completion tokens for LLM usage tracking."""
    try:
        if prompt_tokens > 0:
            llm_tokens_total.labels(provider=provider, model=model, type='prompt').inc(prompt_tokens)
        if completion_tokens > 0:
            llm_tokens_total.labels(provider=provider, model=model, type='completion').inc(completion_tokens)
    except Exception:
        pass


def record_security_violation(violation_type: str):
    """Record security violation in guardrails."""
    try:
        security_violations_total.labels(violation_type=violation_type).inc()
    except Exception:
        pass


def update_active_sessions(channel: str, count: int):
    """Update active sessions gauge."""
    try:
        active_sessions_total.labels(channel=channel).set(count)
    except Exception:
        pass


def update_cache_hit_ratio(ratio: float):
    """Update cache hit ratio."""
    try:
        cache_hit_ratio.set(ratio)
    except Exception:
        pass


def record_whatsapp_message(direction: str):
    """Record WhatsApp message."""
    try:
        whatsapp_messages_total.labels(direction=direction).inc()
    except Exception:
        pass


def record_whatsapp_optout():
    """Record WhatsApp opt-out."""
    try:
        whatsapp_optouts_total.inc()
    except Exception:
        pass


def record_admin_login(result: str):
    """Record admin login attempt."""
    try:
        admin_logins_total.labels(result=result).inc()
    except Exception:
        pass


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
            record_rag_search_duration(duration_ms)
        elif self.metric_name == 'chat':
            record_chat_latency('unknown', duration_ms)


