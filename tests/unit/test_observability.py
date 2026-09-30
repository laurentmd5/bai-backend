"""
Tests unitaires pour le module d'observabilité SRE.
Vérifie la normalisation anti-cardinalité, les métriques Golden Signals et l'export Prometheus.
"""

import pytest
from app.middleware.metrics_middleware import normalize_endpoint_path
from app.core.metrics import (
    record_chat_message,
    record_chat_latency,
    record_chat_error,
    record_llm_tokens,
    record_security_violation,
    record_rag_search_duration,
    record_rag_chunks_retrieved,
    metrics_endpoint,
    http_requests_in_flight,
)


class TestObservabilitySRE:
    """Tests d'observabilité et de fiabilité SRE."""

    def test_normalize_endpoint_path_uuids(self):
        """Vérifie que les UUIDs sont remplacés par {id} pour éviter l'explosion de cardinalité."""
        raw_path = "/api/v1/admin/knowledge/detail/123e4567-e89b-12d3-a456-426614174000"
        normalized = normalize_endpoint_path(raw_path)
        assert normalized == "/api/v1/admin/knowledge/detail/{id}"

    def test_normalize_endpoint_path_multiple_uuids(self):
        """Vérifie la normalisation sur plusieurs segments dynamiques."""
        raw_path = "/api/v1/admin/conversations/123e4567-e89b-12d3-a456-426614174000/messages/987f6543-e21b-65d4-c789-123456789abc"
        normalized = normalize_endpoint_path(raw_path)
        assert normalized == "/api/v1/admin/conversations/{id}/messages/{id}"

    def test_normalize_endpoint_path_numeric_ids(self):
        """Vérifie le remplacement des IDs numériques."""
        raw_path = "/api/v1/admin/users/42"
        normalized = normalize_endpoint_path(raw_path)
        assert normalized == "/api/v1/admin/users/{id}"

    def test_normalize_endpoint_path_query_params(self):
        """Vérifie le nettoyage des paramètres de requête."""
        raw_path = "/api/v1/admin/knowledge?limit=20&offset=40"
        normalized = normalize_endpoint_path(raw_path)
        assert normalized == "/api/v1/admin/knowledge"

    def test_metrics_recording_helpers(self):
        """Vérifie que les helpers d'enregistrement de métriques s'exécutent sans exception."""
        record_chat_message(channel="web", language="fr", cache_hit=False)
        record_chat_latency(channel="web", latency_ms=250.5)
        record_chat_error(error_type="TestException")
        record_llm_tokens(provider="gemini", model="gemini-2.0-flash", prompt_tokens=150, completion_tokens=80)
        record_security_violation(violation_type="prompt_injection")
        record_rag_search_duration(duration_ms=45.2)
        record_rag_chunks_retrieved(chunks_count=5)

    def test_in_flight_gauge_lifecycle(self):
        """Vérifie l'incrémentation et la décrémentation du gauge in-flight."""
        http_requests_in_flight.labels(method="POST").inc()
        http_requests_in_flight.labels(method="POST").dec()

    def test_prometheus_metrics_endpoint_export(self):
        """Vérifie que l'endpoint /metrics génère du texte au format standard Prometheus."""
        response = metrics_endpoint()
        assert response.status_code == 200
        content = response.body.decode("utf-8")
        assert "bot_http_requests_total" in content
        assert "bot_chat_latency_ms" in content
        assert "bot_http_requests_in_flight" in content
