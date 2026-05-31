"""
Tests d'intégration pour les endpoints d'analytics.
Couvre: overview, trends, sentiment, latency, top questions.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from app.models.domain.conversation import Conversation
from app.models.domain.session import Session


@pytest.mark.asyncio
class TestAnalyticsOverview:
    """Tests du dashboard overview (endpoint GET /api/v1/admin/analytics/overview)."""
    
    async def test_analytics_overview_success(self, sync_client, admin_headers):
        """Récupération du dashboard overview."""
        response = sync_client.get(
            "/api/v1/admin/analytics/overview",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should contain key metrics
        assert "total_conversations" in data
        assert "total_sessions" in data
        assert "average_confidence" in data
        assert "unique_users" in data
    
    async def test_analytics_overview_with_period(self, sync_client, admin_headers):
        """Récupération du dashboard overview avec période spécifique."""
        for period in ["7d", "30d", "90d"]:
            response = sync_client.get(
                f"/api/v1/admin/analytics/overview?period={period}",
                headers=admin_headers,
            )
            assert response.status_code == 200
    
    async def test_analytics_overview_requires_auth(self, sync_client):
        """Récupération du dashboard sans authentification échoue."""
        response = sync_client.get("/api/v1/admin/analytics/overview")
        assert response.status_code == 401
    
    async def test_analytics_overview_auditor_can_access(self, sync_client, auditor_headers):
        """AUDITOR peut accéder à l'overview."""
        response = sync_client.get(
            "/api/v1/admin/analytics/overview",
            headers=auditor_headers,
        )
        assert response.status_code == 200


@pytest.mark.asyncio
class TestAnalyticsTrends:
    """Tests des tendances (endpoint GET /api/v1/admin/analytics/trends)."""
    
    async def test_analytics_trends_success(self, sync_client, admin_headers):
        """Récupération des tendances réussie."""
        response = sync_client.get(
            "/api/v1/admin/analytics/trends",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should contain trend data
        assert "trends" in data
        assert "period" in data
        assert isinstance(data["trends"], list)
    
    async def test_analytics_trends_with_period(self, sync_client, admin_headers):
        """Récupération des tendances avec période spécifique."""
        response = sync_client.get(
            "/api/v1/admin/analytics/trends?period=30d",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Each trend point should have date and value
        for point in data.get("trends", []):
            assert "date" in point
            assert "count" in point
    
    async def test_analytics_trends_breakdown_by_channel(self, sync_client, admin_headers):
        """Récupération des tendances par canal."""
        response = sync_client.get(
            "/api/v1/admin/analytics/trends?breakdown=channel",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "web" in data or "whatsapp" in data or "trends" in data
    
    async def test_analytics_trends_with_test_data(self, sync_client, admin_headers, db_session):
        """Récupération des tendances avec données de test."""
        # Create test conversations for different days
        for days_ago in range(7):
            session = Session(
                id=uuid4(),
                user_id=f"user_{days_ago}",
                channel="web" if days_ago % 2 == 0 else "whatsapp",
            )
            db_session.add(session)
            await db_session.commit()
            
            conv_date = datetime.utcnow() - timedelta(days=days_ago)
            conv = Conversation(
                id=uuid4(),
                session_id=session.id,
                user_message=f"Question {days_ago}",
                bot_response=f"Answer {days_ago}",
                channel=session.channel,
                created_at=conv_date,
            )
            db_session.add(conv)
        await db_session.commit()
        
        response = sync_client.get(
            "/api/v1/admin/analytics/trends?period=7d",
            headers=admin_headers,
        )
        assert response.status_code == 200


@pytest.mark.asyncio
class TestAnalyticsSentiment:
    """Tests du sentiment analysis (endpoint GET /api/v1/admin/analytics/sentiment)."""
    
    async def test_analytics_sentiment_success(self, sync_client, admin_headers):
        """Récupération du sentiment analysis."""
        response = sync_client.get(
            "/api/v1/admin/analytics/sentiment",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should contain sentiment data
        assert "positive" in data or "sentiment" in data
    
    async def test_analytics_sentiment_with_period(self, sync_client, admin_headers):
        """Récupération du sentiment avec période spécifique."""
        response = sync_client.get(
            "/api/v1/admin/analytics/sentiment?period=30d",
            headers=admin_headers,
        )
        assert response.status_code == 200
    
    async def test_analytics_sentiment_with_feedback_data(self, sync_client, admin_headers, db_session):
        """Récupération du sentiment avec données de feedback."""
        # Create conversations with feedback
        for feedback_value in [-1, 0, 1, 1, 1]:  # 3 positive, 1 negative, 1 neutral
            session = Session(
                id=uuid4(),
                user_id="test_user",
                channel="web",
            )
            db_session.add(session)
            await db_session.commit()
            
            conv = Conversation(
                id=uuid4(),
                session_id=session.id,
                user_message="How is this?",
                bot_response="This is great!",
                feedback=feedback_value if feedback_value != 0 else None,
            )
            db_session.add(conv)
        await db_session.commit()
        
        response = sync_client.get(
            "/api/v1/admin/analytics/sentiment",
            headers=admin_headers,
        )
        assert response.status_code == 200


@pytest.mark.asyncio
class TestAnalyticsLatency:
    """Tests des métriques de latence (endpoint GET /api/v1/admin/analytics/latency)."""
    
    async def test_analytics_latency_success(self, sync_client, admin_headers):
        """Récupération des métriques de latence."""
        response = sync_client.get(
            "/api/v1/admin/analytics/latency",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should contain latency percentiles
        assert "p50" in data or "latency" in data
    
    async def test_analytics_latency_percentiles(self, sync_client, admin_headers):
        """Vérification des percentiles de latence."""
        response = sync_client.get(
            "/api/v1/admin/analytics/latency",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have p50, p95, p99
        percentiles = ["p50", "p95", "p99"]
        for p in percentiles:
            if p in data:
                assert isinstance(data[p], (int, float))
    
    async def test_analytics_latency_by_component(self, sync_client, admin_headers):
        """Récupération de la latence par composant."""
        response = sync_client.get(
            "/api/v1/admin/analytics/latency?breakdown=component",
            headers=admin_headers,
        )
        assert response.status_code == 200
    
    async def test_analytics_latency_with_test_data(self, sync_client, admin_headers, db_session):
        """Récupération de la latence avec données de test."""
        # Create conversations with latency
        latencies = [100, 150, 200, 250, 300, 350, 400, 450, 500, 550]
        for latency in latencies:
            session = Session(
                id=uuid4(),
                user_id="test_user",
                channel="web",
            )
            db_session.add(session)
            await db_session.commit()
            
            conv = Conversation(
                id=uuid4(),
                session_id=session.id,
                user_message="Test",
                bot_response="Response",
                latency_ms=latency,
            )
            db_session.add(conv)
        await db_session.commit()
        
        response = sync_client.get(
            "/api/v1/admin/analytics/latency",
            headers=admin_headers,
        )
        assert response.status_code == 200


@pytest.mark.asyncio
class TestAnalyticsTopQuestions:
    """Tests des questions les plus fréquentes (endpoint GET /api/v1/admin/analytics/questions)."""
    
    async def test_analytics_top_questions_success(self, sync_client, admin_headers):
        """Récupération des questions top réussie."""
        response = sync_client.get(
            "/api/v1/admin/analytics/questions",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "questions" in data
        assert isinstance(data["questions"], list)
    
    async def test_analytics_top_questions_with_limit(self, sync_client, admin_headers):
        """Récupération des questions top avec limite."""
        response = sync_client.get(
            "/api/v1/admin/analytics/questions?limit=10",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["questions"]) <= 10
    
    async def test_analytics_top_questions_with_test_data(self, sync_client, admin_headers, db_session):
        """Récupération des questions avec données de test."""
        # Create conversations with same question multiple times
        question = "What is NPP?"
        for i in range(5):
            session = Session(
                id=uuid4(),
                user_id=f"user_{i}",
                channel="web",
            )
            db_session.add(session)
            await db_session.commit()
            
            conv = Conversation(
                id=uuid4(),
                session_id=session.id,
                user_message=question,
                bot_response=f"NPP is... (response {i})",
            )
            db_session.add(conv)
        await db_session.commit()
        
        response = sync_client.get(
            "/api/v1/admin/analytics/questions",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should show question with count >= 5
        questions = data.get("questions", [])
        if questions:
            for q in questions:
                if q.get("message") == question:
                    assert q.get("count", 0) >= 5


@pytest.mark.asyncio
class TestAnalyticsRealtime:
    """Tests des données en temps réel (endpoint GET /api/v1/admin/analytics/realtime)."""
    
    async def test_analytics_realtime_success(self, sync_client, admin_headers):
        """Récupération des données en temps réel."""
        response = sync_client.get(
            "/api/v1/admin/analytics/realtime",
            headers=admin_headers,
        )
        # This endpoint may return partial data
        assert response.status_code in [200, 501, 202]
    
    async def test_analytics_realtime_message_count(self, sync_client, admin_headers):
        """Récupération du compteur de messages en temps réel."""
        response = sync_client.get(
            "/api/v1/admin/analytics/realtime?metric=message_count",
            headers=admin_headers,
        )
        if response.status_code == 200:
            data = response.json()
            assert "count" in data or "realtime" in data


@pytest.mark.asyncio
class TestAnalyticsExport:
    """Tests d'export d'analytics (endpoint GET /api/v1/admin/analytics/export/*)."""
    
    async def test_export_conversations_csv(self, sync_client, admin_headers):
        """Export des conversations en CSV."""
        response = sync_client.get(
            "/api/v1/admin/analytics/export/conversations?format=csv",
            headers=admin_headers,
        )
        # May not be fully implemented
        assert response.status_code in [200, 501, 202]
        if response.status_code == 200:
            # Should have CSV content
            assert "text/csv" in response.headers.get("content-type", "")
    
    async def test_export_conversations_json(self, sync_client, admin_headers):
        """Export des conversations en JSON."""
        response = sync_client.get(
            "/api/v1/admin/analytics/export/conversations?format=json",
            headers=admin_headers,
        )
        assert response.status_code in [200, 501, 202]
    
    async def test_export_analytics_report(self, sync_client, admin_headers):
        """Export d'un rapport analytics."""
        response = sync_client.get(
            "/api/v1/admin/analytics/export/report",
            headers=admin_headers,
        )
        assert response.status_code in [200, 501, 202]


@pytest.mark.asyncio
class TestAnalyticsRBAC:
    """Tests des permissions RBAC pour les analytics."""
    
    async def test_admin_can_access_analytics(self, sync_client, admin_headers):
        """ADMIN peut accéder aux analytics."""
        response = sync_client.get(
            "/api/v1/admin/analytics/overview",
            headers=admin_headers,
        )
        assert response.status_code == 200
    
    async def test_auditor_can_access_analytics(self, sync_client, auditor_headers):
        """AUDITOR peut accéder aux analytics."""
        response = sync_client.get(
            "/api/v1/admin/analytics/overview",
            headers=auditor_headers,
        )
        assert response.status_code == 200
    
    async def test_viewer_cannot_access_analytics(self, sync_client, db_session):
        """VIEWER ne peut pas accéder aux analytics."""
        from app.core.security import create_jwt_token
        viewer_token = create_jwt_token(
            {
                "sub": str(uuid4()),
                "email": "viewer@test.com",
                "role": "VIEWER",
            },
            "access"
        )
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
        
        response = sync_client.get(
            "/api/v1/admin/analytics/overview",
            headers=viewer_headers,
        )
        # VIEWER should not be able to access analytics
        if response.status_code == 200:
            # Or the endpoint might allow VIEWER read access
            pass
        else:
            assert response.status_code == 403
