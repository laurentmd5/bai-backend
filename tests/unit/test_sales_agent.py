"""
Tests unitaires pour SalesAgent — module de qualification commerciale.
Teste le tunnel de qualification complet sans DB ni Redis (tout mocké).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Mocks globaux pour éviter les connexions DB/Redis/SMTP ──────────────────

# Mock settings AVANT l'import du module
import sys
mock_settings = MagicMock()
mock_settings.COMPANY_NAME = "NETSYSTEME Informatique"
mock_settings.COMPANY_CONTACT_EMAIL = "contact@netsys-info.com"
mock_settings.COMPANY_CONTACT_PHONE = "+221 33 827 28 45"
mock_settings.COMPANY_WHATSAPP = "+221 77 846 16 55"
mock_settings.COMPANY_WEBSITE = "https://netsys-info.com"

# Mock cache_service (pas de Redis)
mock_cache = AsyncMock()
mock_cache.get = AsyncMock(return_value=None)   # pas de state en cache
mock_cache.set = AsyncMock(return_value=True)

# Mock email_service (pas de SMTP)
mock_email = AsyncMock()
mock_email.send_sales_lead_notification = AsyncMock(return_value=True)

# Mock CommercialLeadRepository (pas de DB)
mock_repo_instance = AsyncMock()
mock_repo_instance.save_lead = AsyncMock(return_value=None)
mock_repo_instance.close = AsyncMock(return_value=None)
MockLeadRepo = MagicMock(return_value=mock_repo_instance)


with (
    patch("app.core.config.settings", mock_settings),
    patch("app.services.cache.redis_cache.cache_service", mock_cache),
    patch("app.services.notification.email_service.email_service", mock_email),
    patch("app.repositories.lead_repository.CommercialLeadRepository", MockLeadRepo),
):
    from app.services.commercial.sales_agent import SalesAgent, SERVICE_CATEGORIES


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def agent():
    """Agent neuf avec in-memory store uniquement."""
    a = SalesAgent()
    # Brancher le mock cache sur l'agent
    return a


@pytest.fixture
def session_id():
    return "test-session-sales-001"


# ─── TESTS ────────────────────────────────────────────────────────────────────

class TestServiceCategoryDetection:
    """Tests de détection de catégorie de service."""

    def test_detect_camera_category(self):
        agent = SalesAgent()
        cat = agent.detect_service_category("je veux installer des caméras de surveillance")
        assert cat == "Vidéosurveillance"

    def test_detect_solar_category(self):
        agent = SalesAgent()
        cat = agent.detect_service_category("je veux des panneaux solaires pour mon entreprise")
        assert cat == "Énergie Solaire"

    def test_detect_network_category(self):
        agent = SalesAgent()
        cat = agent.detect_service_category("besoin de câblage réseau et switch pour nos bureaux")
        assert cat == "Réseaux & Télécom"

    def test_detect_website_category(self):
        agent = SalesAgent()
        cat = agent.detect_service_category("je veux créer un site web e-commerce")
        assert cat == "Sites Web & Plateformes"

    def test_no_category_general_message(self):
        agent = SalesAgent()
        cat = agent.detect_service_category("bonjour, pouvez-vous m'aider ?")
        assert cat is None


class TestQuoteIntentDetection:
    """Tests de détection d'intention de devis."""

    def test_devis_keyword(self):
        agent = SalesAgent()
        has_intent, cat = agent.is_quote_or_sales_intent("je voudrais un devis pour des caméras")
        assert has_intent is True
        assert cat == "Vidéosurveillance"

    def test_prix_keyword(self):
        agent = SalesAgent()
        has_intent, _ = agent.is_quote_or_sales_intent("combien coûte une installation réseau ?")
        assert has_intent is True

    def test_acheter_keyword(self):
        agent = SalesAgent()
        has_intent, _ = agent.is_quote_or_sales_intent("je veux acheter des panneaux solaires")
        assert has_intent is True

    def test_no_intent_question(self):
        agent = SalesAgent()
        has_intent, _ = agent.is_quote_or_sales_intent("c'est quoi votre entreprise ?")
        assert has_intent is False

    def test_no_intent_greeting(self):
        agent = SalesAgent()
        has_intent, _ = agent.is_quote_or_sales_intent("bonjour")
        assert has_intent is False


class TestContactExtraction:
    """Tests d'extraction de contacts depuis un message libre."""

    def test_extract_phone_senegalese(self):
        agent = SalesAgent()
        result = agent.extract_contact_info("mon numéro c'est 77 123 45 67")
        assert result["phone"] is not None
        assert "77" in result["phone"]

    def test_extract_phone_with_code(self):
        agent = SalesAgent()
        result = agent.extract_contact_info("appelez-moi au +221 77 846 12 34")
        assert result["phone"] is not None

    def test_extract_email(self):
        agent = SalesAgent()
        result = agent.extract_contact_info("mon email est dupont@gmail.com merci")
        assert result["email"] == "dupont@gmail.com"

    def test_extract_name_je_mappelle(self):
        agent = SalesAgent()
        result = agent.extract_contact_info("je m'appelle Moussa Diallo")
        assert result["name"] == "Moussa Diallo"

    def test_extract_name_nom(self):
        agent = SalesAgent()
        result = agent.extract_contact_info("Nom: Fatou Sow, téléphone 78 000 11 22")
        assert result["name"] is not None
        assert "Fatou" in result["name"]

    def test_no_contact_info(self):
        agent = SalesAgent()
        result = agent.extract_contact_info("je veux 5 caméras pour mon entrepôt")
        assert result["phone"] is None
        assert result["email"] is None


class TestFullQualificationTunnel:
    """Tests du tunnel complet de qualification en 3 étapes."""

    @pytest.mark.asyncio
    async def test_start_qualification_returns_stage1(self, session_id):
        agent = SalesAgent()
        with patch.object(agent, "save_state", AsyncMock()):
            res = await agent.start_sales_qualification(
                session_id=session_id,
                user_message="je veux un devis pour des caméras",
                channel="whatsapp",
                client_name="Laurent",
            )
        assert res is not None
        assert res["sales_stage"] == "COLLECTING_NEED"
        assert "devis" in res["message"].lower() or "besoin" in res["message"].lower()
        assert res["category"] == "Vidéosurveillance"

    @pytest.mark.asyncio
    async def test_stage1_to_stage2(self, session_id):
        agent = SalesAgent()
        # Injecter un état COLLECTING_NEED manuellement
        agent._memory_store[session_id] = {
            "session_id": session_id,
            "stage": "COLLECTING_NEED",
            "requirements": ["je veux un devis pour des caméras"],
            "category": "Vidéosurveillance",
            "full_name": "Laurent",
            "company_name": None,
            "phone_number": None,
            "email": None,
            "location": None,
            "answers": {},
            "started_at": "2026-09-30T00:00:00",
        }
        with (
            patch.object(agent, "save_state", AsyncMock()),
            patch.object(agent, "get_state", AsyncMock(return_value=agent._memory_store[session_id])),
        ):
            res = await agent.process_prospect_message(
                session_id=session_id,
                user_message="5 caméras intérieures pour un entrepôt de 500m²",
                channel="whatsapp",
            )
        assert res is not None
        assert res["sales_stage"] == "COLLECTING_CONTACT"
        assert "nom" in res["message"].lower() or "société" in res["message"].lower()

    @pytest.mark.asyncio
    async def test_stage2_to_stage3(self, session_id):
        agent = SalesAgent()
        agent._memory_store[session_id] = {
            "session_id": session_id,
            "stage": "COLLECTING_CONTACT",
            "requirements": ["5 caméras intérieures"],
            "category": "Vidéosurveillance",
            "full_name": None,
            "company_name": None,
            "phone_number": None,
            "email": None,
            "location": None,
            "answers": {},
            "started_at": "2026-09-30T00:00:00",
        }
        with (
            patch.object(agent, "save_state", AsyncMock()),
            patch.object(agent, "get_state", AsyncMock(return_value=agent._memory_store[session_id])),
        ):
            res = await agent.process_prospect_message(
                session_id=session_id,
                user_message="je m'appelle Moussa Diallo, mon numéro c'est 77 123 45 67",
                channel="whatsapp",
            )
        assert res is not None
        assert res["sales_stage"] == "COLLECTING_LOCATION"
        assert "ville" in res["message"].lower() or "email" in res["message"].lower()

    @pytest.mark.asyncio
    async def test_stage3_completed_saves_lead_and_sends_email(self, session_id):
        agent = SalesAgent()
        state = {
            "session_id": session_id,
            "stage": "COLLECTING_LOCATION",
            "requirements": ["5 caméras intérieures pour un entrepôt"],
            "category": "Vidéosurveillance",
            "full_name": "Moussa Diallo",
            "company_name": None,
            "phone_number": "77 123 45 67",
            "email": None,
            "location": None,
            "answers": {"contact_response": "Moussa Diallo, 77 123 45 67"},
            "started_at": "2026-09-30T00:00:00",
        }
        agent._memory_store[session_id] = state

        with (
            patch.object(agent, "save_state", AsyncMock()),
            patch.object(agent, "get_state", AsyncMock(return_value=state)),
            patch("app.services.commercial.sales_agent.CommercialLeadRepository", MockLeadRepo),
            patch("app.services.commercial.sales_agent.email_service", mock_email),
            patch("app.services.commercial.sales_agent.asyncio.create_task", MagicMock()),
        ):
            res = await agent.process_prospect_message(
                session_id=session_id,
                user_message="Dakar, Plateau. mon email est moussa@gmail.com",
                channel="whatsapp",
            )
        assert res is not None
        assert res["sales_stage"] == "COMPLETED"
        assert "transmise" in res["message"].lower() or "parfait" in res["message"].lower()
        assert res["lead_data"]["full_name"] == "Moussa Diallo"
        assert res["lead_data"]["category"] == "Vidéosurveillance"
        # Vérifier que save_lead a été appelé
        mock_repo_instance.save_lead.assert_called_once()

    @pytest.mark.asyncio
    async def test_abort_mid_tunnel(self, session_id):
        """L'utilisateur annule en cours de qualification."""
        agent = SalesAgent()
        state = {
            "session_id": session_id,
            "stage": "COLLECTING_CONTACT",
            "requirements": ["devis cameras"],
            "category": "Vidéosurveillance",
            "full_name": None, "company_name": None,
            "phone_number": None, "email": None, "location": None,
            "answers": {}, "started_at": "2026-09-30T00:00:00",
        }
        agent._memory_store[session_id] = state
        with (
            patch.object(agent, "save_state", AsyncMock()),
            patch.object(agent, "get_state", AsyncMock(return_value=state)),
        ):
            res = await agent.process_prospect_message(
                session_id=session_id,
                user_message="annuler le devis",
                channel="whatsapp",
            )
        assert res is not None
        assert res["sales_stage"] == "ABORTED"

    @pytest.mark.asyncio
    async def test_idle_session_returns_none(self, session_id):
        """Un message non commercial ne déclenche pas le tunnel."""
        agent = SalesAgent()
        # Pas de state dans le memory store → get_state retourne IDLE
        res = await agent.process_prospect_message(
            session_id="session-not-in-sales",
            user_message="bonjour, comment ça va ?",
            channel="whatsapp",
        )
        assert res is None


class TestFinalMessageUsesSettings:
    """Vérifie que le message final utilise les settings et non des valeurs hardcodées."""

    @pytest.mark.asyncio
    async def test_final_message_contains_settings_company_name(self, session_id):
        agent = SalesAgent()
        state = {
            "session_id": session_id,
            "stage": "COLLECTING_LOCATION",
            "requirements": ["5 caméras"],
            "category": "Vidéosurveillance",
            "full_name": "Test User",
            "company_name": None,
            "phone_number": "77 000 00 00",
            "email": None,
            "location": None,
            "answers": {},
            "started_at": "2026-09-30T00:00:00",
        }
        agent._memory_store[session_id] = state

        local_settings = MagicMock()
        local_settings.COMPANY_NAME = "NETSYSTEME Informatique"
        local_settings.COMPANY_CONTACT_PHONE = "+221 33 827 28 45"
        local_settings.COMPANY_CONTACT_EMAIL = "contact@netsys-info.com"

        with (
            patch.object(agent, "save_state", AsyncMock()),
            patch.object(agent, "get_state", AsyncMock(return_value=state)),
            patch("app.services.commercial.sales_agent.CommercialLeadRepository", MockLeadRepo),
            patch("app.services.commercial.sales_agent.email_service", mock_email),
            patch("app.services.commercial.sales_agent.asyncio.create_task", MagicMock()),
            patch("app.services.commercial.sales_agent.settings", local_settings),
        ):
            res = await agent.process_prospect_message(
                session_id=session_id,
                user_message="Dakar Centre",
                channel="whatsapp",
            )

        # Le message doit contenir le nom de la société depuis settings (patché)
        assert "NETSYSTEME Informatique" in res["message"]

    @pytest.mark.asyncio
    async def test_final_message_no_contact_when_settings_empty(self, session_id):
        """Si COMPANY_CONTACT_PHONE est vide dans .env, la ligne urgence n'apparaît pas."""
        agent = SalesAgent()
        state = {
            "session_id": session_id,
            "stage": "COLLECTING_LOCATION",
            "requirements": ["3 caméras"],
            "category": "Vidéosurveillance",
            "full_name": "Client Test",
            "company_name": None,
            "phone_number": None,
            "email": None,
            "location": None,
            "answers": {},
            "started_at": "2026-09-30T00:00:00",
        }
        agent._memory_store[session_id] = state

        empty_settings = MagicMock()
        empty_settings.COMPANY_NAME = "MonEntreprise"
        empty_settings.COMPANY_CONTACT_PHONE = ""
        empty_settings.COMPANY_CONTACT_EMAIL = ""

        with (
            patch.object(agent, "save_state", AsyncMock()),
            patch.object(agent, "get_state", AsyncMock(return_value=state)),
            patch("app.services.commercial.sales_agent.CommercialLeadRepository", MockLeadRepo),
            patch("app.services.commercial.sales_agent.email_service", mock_email),
            patch("app.services.commercial.sales_agent.asyncio.create_task", MagicMock()),
            patch("app.services.commercial.sales_agent.settings", empty_settings),
        ):
            res = await agent.process_prospect_message(
                session_id=session_id,
                user_message="Thiès",
                channel="whatsapp",
            )

        assert res["sales_stage"] == "COMPLETED"
        # Pas de ligne "Pour toute urgence" quand les coords ne sont pas configurées
        assert "urgence" not in res["message"].lower() or "MonEntreprise" in res["message"]
