"""
Chat Service for BARROW.AI - Main orchestrator for the chatbot engine.
Coordinates all components: validation, RAG, LLM, caching, and persistence.
"""

import asyncio
import re
import uuid
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from app.services.rag_service import RAGService
from app.services.llm.factory import get_llm_provider
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.oolel_provider import OolelProvider
from app.services.llm.query_transformer import QueryTransformer
from app.services.validation.input_validator import InputValidator
from app.services.validation.output_validator import OutputValidator
from app.services.validation.security_validator import SecurityValidator
from app.services.cache.redis_cache import cache_service, CacheNamespace
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.session_repository import SessionRepository
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import llm_generation_duration_ms
from app.core.exceptions import (
    BarrowAIException,
    LowConfidenceException,
    LLMTimeoutException,
    LLMUnavailableException,
    HostileContentException,
    PromptInjectionException,
    ValidationException,
)

logger = get_logger(__name__)


class ChatService:
    """
    Main orchestrator for the BARROW.AI chatbot.
    
    Coordinates the complete conversation flow:
    1. Input validation and security checks
    2. Session management
    3. Intent detection
    4. Cache lookup
    5. RAG retrieval
    6. LLM generation
    7. Output validation
    8. Persistence and analytics
    
    Implements SOLID principles with dependency injection for all components.
    
    NOTE: This service is instantiated once at application startup
    and stored in app.state.chat_service. All endpoints access the same
    singleton instance via FastAPI dependency injection.
    """
    
    # Special intents that bypass RAG+LLM pipeline
    SPECIAL_INTENTS = {
        "greeting": ["hello", "hi", "hey", "bonjour", "salut", "salaam", "salaam aleikum", "nna tang", "nanga def", "nanga dëf", "naga def", "naga dëf"],
        "help": ["help", "aide", "menu", "what can you do", "capabilities"],
        "thanks": ["thank", "merci", "thanks", "thank you", "je vous remercie"],
        "stop": ["stop", "unsubscribe", "désabonner", "opt out", "opt-out"],
        "start": ["start", "subscribe", "réabonner", "opt in", "opt-in"],
        "status": ["status", "health", "ping", "test"],
    }
    
    # Pre-defined responses for special intents
    GREETING_RESPONSES = {
        "en": (
            "Hello! Welcome to AskBarrow.ai — your official source for information about "
            "President Adama Barrow's achievements and NPP programmes.\n\n"
            "You can ask me about:\n"
            "• Development in your area\n"
            "• Government programmes (Digital Transformation, Infrastructure, Youth)\n"
            "• NPP plans for 2027-2031\n"
            "• Digital addressing and connectivity\n\n"
            "How can I help you today?\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "fr": (
            "Bonjour ! Bienvenue sur AskBarrow.ai — votre source officielle d'information "
            "sur les réalisations du Président Adama Barrow et les programmes du NPP.\n\n"
            "Vous pouvez me demander :\n"
            "• Le développement dans votre région\n"
            "• Les programmes gouvernementaux (Transformation Numérique, Infrastructure, Jeunesse)\n"
            "• Les plans du NPP pour 2027-2031\n"
            "• L'adressage numérique et la connectivité\n\n"
            "Comment puis-je vous aider aujourd'hui ?\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "mandinka": (
            "Salaam Aleikum! I ye AskBarrow.ai la. Nte le mu i la kuntaalaa ti "
            "President Adama Barrow ni NPP la waleeroolu la.\n\n"
            "I si n ñininkaa:\n"
            "• I la dulaa yiriwaa\n"
            "• Gobiroomu porogaramoolu\n"
            "• NPP la feeroolu 2027-2031\n"
            "• Adireesu nimberoolu ani konekitiviti\n\n"
            "M be i la jaabiroo la?\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "wolof": (
            "Nanga dëf! Dalal ak jàmm ci AskBarrow.ai — sa barabu xibaar ci mbiri "
            "liggéeyi President Adama Barrow ak programi NPP.\n\n"
            "Mën nga ma laaj ci mbir yii:\n"
            "• Nataal ci sa gox\n"
            "• Programi nguur gi (Digital Transformation, Infrastructure, Ndaw ñi)\n"
            "• Yéeney NPP ngir 2027-2031\n"
            "• Digital addressing ak jokkoo\n\n"
            "Naka laa la mën a jappale tey?\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
    }
    
    HELP_RESPONSES = {
        "en": (
            "I'm AskBarrow.ai, here to inform you about President Barrow's achievements.\n\n"
            "**Topics I can discuss:**\n"
            "• Internet and mobile connectivity (113% penetration, GAMTEL upgrade)\n"
            "• Digital addressing (194,000+ properties mapped)\n"
            "• E-Government services (MYGOV platform)\n"
            "• Youth and ICT programmes\n"
            "• NPP's Way Forward 2027-2031\n\n"
            "**Example questions:**\n"
            "• 'What has NPP done for internet?'\n"
            "• 'Tell me about digital addressing'\n"
            "• 'What are the plans for 5G?'\n\n"
            "What would you like to know?\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "fr": (
            "Je suis AskBarrow.ai, votre assistant d'information sur les réalisations du Président Barrow.\n\n"
            "**Sujets que je peux aborder :**\n"
            "• Connectivité internet et mobile (113% de pénétration, mise à niveau GAMTEL)\n"
            "• Adressage numérique (194 000+ propriétés cartographiées)\n"
            "• Services d'e-Gouvernement (plateforme MYGOV)\n"
            "• Programmes Jeunesse et TIC\n"
            "• La Voie à Suivre du NPP 2027-2031\n\n"
            "**Exemples de questions :**\n"
            "• 'Qu'a fait le NPP pour l'internet ?'\n"
            "• 'Parlez-moi de l'adressage numérique'\n"
            "• 'Quels sont les plans pour la 5G ?'\n\n"
            "Que souhaitez-vous savoir ?\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
    }
    
    STOP_RESPONSE = {
        "en": (
            "You have been unsubscribed from AskBarrow.ai messages. "
            "You can restart the conversation anytime by sending 'START'.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "fr": (
            "Vous avez été désabonné des messages AskBarrow.ai. "
            "Vous pouvez relancer la conversation à tout moment en envoyant 'START'.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
    }
    
    START_RESPONSE = {
        "en": (
            "Welcome back to AskBarrow.ai! You are now resubscribed. "
            "How can I help you today?\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "fr": (
            "Bon retour sur AskBarrow.ai ! Vous êtes maintenant réabonné. "
            "Comment puis-je vous aider aujourd'hui ?\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
    }
    
    FALLBACK_RESPONSES = {
        "en": (
            "I do not have this specific information in my campaign database. "
            "Please visit www.npp.gm or contact your nearest PACE office for more details.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "fr": (
            "Je ne dispose pas de cette information spécifique dans ma base de campagne. "
            "Veuillez visiter www.npp.gm ou contacter le bureau PACE le plus proche.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "wolof": (
            "Dafa amul loolu ci sama xam-xam ci campagne bi. "
            "Jëkkël www.npp.gm walla dem ci birou PACE bi jeex ci sa àll.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "mandinka": (
            "N be fen kang bora i fono la ka ñininka soto. "
            "Teng www.npp.gm walima ye PACE ofisi kelen kelen di.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "fular": (
            "Ngal woodaaki hol ko ndaartaten e ngootaaku am. "
            "Yah www.npp.gm walla PACE to fetel maa.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
    }
    
    TECHNICAL_ERROR_RESPONSE = {
        "en": (
            "I'm experiencing a temporary technical issue. "
            "Please try again in a few moments.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "fr": (
            "Je rencontre une difficulté technique momentanée. "
            "Veuillez réessayer dans quelques instants.\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
    }
    
    HOSTILE_CONTENT_RESPONSE = {
        "en": (
            "I'm AskBarrow.ai, the official assistant for President Adama Barrow and the NPP. "
            "I'm here to provide information about the President's achievements and the party's programs. "
            "How can I help you with that?\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
        "fr": (
            "Je suis AskBarrow.ai, l'assistant officiel du Président Adama Barrow et du NPP. "
            "Je suis là pour fournir des informations sur les réalisations du Président et les programmes du parti. "
            "Comment puis-je vous aider ?\n\n"
            "Ask. Know. Decide. - One Gambia. One People. One Barrow."
        ),
    }
    
    # Relevance keywords for filtering
    RELEVANCE_KEYWORDS = {
        "internet": ["internet", "connectivity", "broadband", "wifi", "4g", "5g", "mobile data", "online", "digital service", "gamcel", "gamtel"],
        "digital": ["digital", "digitization", "e-service", "online platform", "mygov", "portal", "e-government", "digital address", "smart"],
        "infrastructure": ["road", "bridge", "highway", "infrastructure", "construction", "development", "port", "airport"],
        "youth": ["youth", "young", "employment", "job", "entrepreneurship", "startup", "training", "skill", "empowerment"],
        "economy": ["economy", "gdp", "growth", "investment", "business", "trade", "economic", "job creation"],
        "health": ["health", "hospital", "clinic", "healthcare", "medical", "disease", "treatment", "vaccine"],
        "education": ["education", "school", "university", "college", "student", "teacher", "learning", "scholarship"],
        "agriculture": ["agriculture", "farm", "farming", "crop", "food security", "irrigation", "rice", "vegetable"],
    }
    
    def __init__(
        self,
        session_repository: SessionRepository,
        conversation_repository: ConversationRepository,
        rag_service: RAGService,
        llm_provider=None,
    ):
        """
        Initialize ChatService with required dependencies.
        
        All dependencies are provided at initialization time (dependency injection).
        This ensures the service is fully configured and ready to use without
        lazy initialization or lazy loading of components.
        
        Args:
            session_repository: Repository for session management
            conversation_repository: Repository for conversation persistence
            rag_service: RAGService singleton instance
            llm_provider: LLM provider instance (defaults to get_llm_provider())
        """
        self._session_repo = session_repository
        self._conversation_repo = conversation_repository
        
        # Services injected at initialization
        self._rag_service = rag_service
        self._llm_provider = llm_provider or get_llm_provider()
        self._oolel_provider = OolelProvider()
        
        # Initialize query transformer for advanced intelligence
        self._query_transformer = QueryTransformer(self._llm_provider)
        
        # Initialize validators
        self._input_validator = InputValidator()
        self._output_validator = OutputValidator()
        self._security_validator = SecurityValidator()
        
        logger.info(f"📌 ChatService instance created: id={id(self)}")
    
    def _verify_initialized(self) -> None:
        """Verify that all required services are initialized."""
        if not self._rag_service:
            raise RuntimeError(
                "ChatService not properly initialized. "
                "rag_service is missing."
            )
    
    def _detect_intent(self, message: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Detect special intent from user message.
        
        Uses word boundaries to avoid false positives like "hi" in "Lahido".
        
        Returns:
            Tuple of (intent, matched_keyword) or (None, None)
        """
        message_lower = message.lower().strip()
        
        # Greeting: match only if it's the entire message or starts the message
        # (avoids "lahido" -> "hi", "achievements" -> "hi", etc.)
        greeting_patterns = [
            r'^(hello|hi|hey|bonjour|salut|salaam)[\s,!.?]*$',  # single word
            r'^(salaam aleikum|nna tang|nanga def|nanga dëf|naga def|naga dëf)',                       # start of message
        ]
        for pattern in greeting_patterns:
            if re.match(pattern, message_lower):
                return "greeting", "greeting"
        
        # All other intents: word-boundary matching (whole word, not substring)
        for intent, keywords in self.SPECIAL_INTENTS.items():
            if intent == "greeting":
                continue  # already handled above
            for keyword in keywords:
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, message_lower):
                    return intent, keyword
        
        # Ultra-short messages (< 5 chars) trigger help intent (lower priority)
        if len(message_lower) < 5 and message_lower not in ['npp', 'np']:
            return "help", "ultra_short"
        
        return None, None
    
    def _get_intent_response(
        self,
        intent: str,
        language: str,
        matched_keyword: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get pre-defined response for special intent.
        
        Args:
            intent: Detected intent type
            language: User's language
            matched_keyword: Keyword that triggered the intent
            
        Returns:
            Response string or None if not a special intent
        """
        if intent == "greeting":
            # Check if keyword indicates specific language
            if matched_keyword in ["bonjour", "salut"]:
                return self.GREETING_RESPONSES["fr"]
            if matched_keyword in ["salaam", "salaam aleikum", "nna tang"]:
                return self.GREETING_RESPONSES.get("mandinka", self.GREETING_RESPONSES["en"])
            if matched_keyword in ["nanga def", "nanga dëf", "naga def", "naga dëf"]:
                return self.GREETING_RESPONSES.get("wolof", self.GREETING_RESPONSES["en"])
            return self.GREETING_RESPONSES.get(language, self.GREETING_RESPONSES["en"])
        
        if intent == "help":
            return self.HELP_RESPONSES.get(language, self.HELP_RESPONSES["en"])
        
        if intent == "thanks":
            return None  # Let LLM handle naturally, but with positive tone
        
        if intent == "stop":
            return self.STOP_RESPONSE.get(language, self.STOP_RESPONSE["en"])
        
        if intent == "start":
            return self.START_RESPONSE.get(language, self.START_RESPONSE["en"])
        
        if intent == "status":
            return "AskBarrow.ai is operational and ready to assist you."
        
        return None
    
    async def _handle_keyword_query(
        self,
        message: str,
        language: str,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Handle very short keyword-only queries.
        Returns a response directly without RAG if the keyword is recognized.
        """
        keyword_map = {
            "internet": {
                "en": "NPP increased mobile penetration to 113%, upgraded GAMTEL backbone to 800G, launched a $25M submarine cable project, and completed 100% digital addressing in Banjul and Kanifing. Would you like more details?",
                "fr": "Le NPP a augmenté la pénétration mobile à 113%, modernisé le réseau GAMTEL, lancé un projet de câble sous-marin de 25M$, et achevé l'adressage numérique à Banjul et Kanifing. Voulez-vous plus de détails?"
            },
            "agriculture": {
                "en": "NPP plans include rice self-sufficiency by 2031, support for farmers, irrigation projects, training for youth, and making Gambia food secure. Ask me for specific details!",
                "fr": "Les plans du NPP incluent l'autosuffisance en riz d'ici 2031, le soutien aux agriculteurs, des projets d'irrigation, et la formation des jeunes pour une Gambie autosuffisante."
            },
            "health": {
                "en": "NPP is strengthening hospitals, expanding health insurance, building new clinics, and training more doctors and nurses. We want every Gambian to have access to quality healthcare.",
                "fr": "Le NPP renforce les hôpitaux, élargit l'assurance maladie, construit de nouveaux dispensaires et forme plus de médecins. Chaque Gambien mérite des soins de qualité."
            },
            "education": {
                "en": "NPP is building new schools, training more teachers, providing scholarships, and expanding technical training centers so youth can learn skills for jobs.",
                "fr": "Le NPP construit des écoles, forme plus d'enseignants, offre des bourses et étend les centres de formation technique pour que les jeunes apprennent des métiers."
            },
            "youth": {
                "en": "NPP creates jobs for youth through skills training, entrepreneurship programs, and support for young farmers and digital workers. We believe empowered youth build a stronger Gambia.",
                "fr": "Le NPP crée des emplois pour les jeunes par la formation, l'entrepreneuriat et le soutien aux jeunes agriculteurs et travailleurs numériques."
            },
            "governance": {
                "en": "NPP is fighting corruption, strengthening transparency, improving public services, and making government more accountable to citizens. We believe government must serve the people.",
                "fr": "Le NPP lutte contre la corruption, renforce la transparence, améliore les services publics et rend le gouvernement plus responsable devant les citoyens."
            },
            "digital": {
                "en": "NPP is bringing internet to all regions, digitizing government services, training youth in digital skills, and building a modern digital economy for Gambia.",
                "fr": "Le NPP apporte l'internet dans toutes les régions, numérise les services gouvernementaux, forme les jeunes au numérique et construit une économie digitale moderne."
            },
            "npp": {
                "en": "NPP is the National People's Party, led by President Adama Barrow. Our 9-point Lahido plan focuses on jobs, digital transformation, agriculture, health, education, youth empowerment, infrastructure, good governance, and environment.",
                "fr": "Le NPP est le parti dirigé par le Président Adama Barrow. Notre plan Lahido en 9 points couvre l'emploi, le numérique, l'agriculture, la santé, l'éducation, la jeunesse, les infrastructures, la gouvernance et l'environnement."
            },
            "barrow": {
                "en": "President Adama Barrow has led Gambia since 2017, strengthening democracy, building roads, expanding internet, and improving healthcare under the NPP government.",
                "fr": "Le Président Adama Barrow dirige la Gambie depuis 2017, renforçant la démocratie, construisant des routes, développant internet et améliorant la santé."
            },
        }
        
        message_lower = message.lower().strip()
        
        for keyword, responses in keyword_map.items():
            # Exact match or starts with keyword
            if message_lower == keyword or message_lower.startswith(keyword):
                return {
                    "message": responses.get(language, responses["en"]),
                    "session_id": session_id,
                    "sources": [],
                    "confidence": 0.95,
                    "cache_hit": False,
                    "fallback_triggered": False,
                    "timestamp": datetime.utcnow().isoformat(),
                }
        
        return None
    
    def _get_cache_key(self, message: str, language: str) -> str:
        """
        Generate cache key for RAG response.
        
        Args:
            message: User message
            language: Message language
            
        Returns:
            Cache key string
        """
        import hashlib
        normalized = f"{message.lower().strip()}:{language}"
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def _is_response_relevant(
        self, 
        sources: List[Dict], 
        query: str, 
        language: str = "en"
    ) -> bool:
        """
        Check if retrieved sources are actually relevant to the user's question.
        
        This prevents the system from answering with completely irrelevant documents.
        
        Args:
            sources: List of sources returned by Qdrant
            query: User's original question
            language: User's language
            
        Returns:
            True if response is relevant, False otherwise
        """
        # 1. Duplicate detection (same document, same chunk = forced match)
        unique_chunks = set()
        for s in sources:
            doc_name = s.get("document", s.get("doc_id", ""))
            chunk_idx = s.get("chunk_index", s.get("index", 0))
            unique_chunks.add((doc_name, chunk_idx))
        
        if len(unique_chunks) == 1:
            logger.warning("all_sources_identical", chunks=len(sources))
            return False
        
        # 2. Detect the theme of the query
        query_lower = query.lower()
        detected_theme = None
        theme_keywords = []
        
        for theme, keywords in self.RELEVANCE_KEYWORDS.items():
            for kw in keywords:
                if kw in query_lower:
                    detected_theme = theme
                    theme_keywords = keywords
                    break
            if detected_theme:
                break
        
        if not detected_theme:
            return True
        
        # 3. Check if sources contain relevant keywords
        source_text = ""
        for s in sources[:3]:
            text = s.get("text_preview", "") or s.get("content", "") or ""
            section = s.get("section", "")
            source_text += f" {text} {section}"
        
        source_lower = source_text.lower()
        has_relevant_term = any(kw in source_lower for kw in theme_keywords[:5])
        
        if not has_relevant_term:
            logger.warning("no_relevant_terms_in_sources", theme=detected_theme)
            return False
        
        # 4. Check minimum similarity score
        min_score = min((s.get("relevance", s.get("score", 0)) for s in sources), default=0)
        threshold = getattr(settings, 'QDRANT_SIMILARITY_THRESHOLD', 0.70)
        
        if min_score < threshold:
            return False
        
        return True
    
    async def process_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        language: str = "en",
        channel: str = "web",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process a user message and generate a response.
        
        This is the main entry point for the chatbot engine.
        
        Args:
            message: User's message
            session_id: Optional existing session ID
            language: Preferred language (en, fr, mandinka, wolof)
            channel: Message channel (web, whatsapp)
            ip_address: Client IP address
            user_agent: Client user agent
            metadata: Additional metadata
            
        Returns:
            Response dict containing message, session_id, sources, confidence, etc.
        """
        start_time = datetime.utcnow()

        self._verify_initialized()

        # Auto-detect language when the caller passes the default "en"
        # and did not explicitly choose English.  The WhatsApp service
        # already detects language and passes it; this covers the web
        # chat API where the user omits the language field.
        if language == "en":
            try:
                detected = self._input_validator.detect_language(message)
                if detected != "en":
                    language = detected
                    logger.info(
                        "chat_language_auto_detected",
                        detected=language,
                        channel=channel,
                    )
            except Exception:
                pass  # keep default "en" on any detection error

        # Initialize response metadata
        response_metadata = {
            "channel": channel,
            "language": language,
            "cache_hit": False,
            "fallback_triggered": False,
            "intent_detected": None,
        }
        
        try:
            # ===============================================================
            # STEP 1: Security - Rate Limiting
            # ===============================================================
            if ip_address and session_id:
                allowed, remaining, reset_in = await self._security_validator.check_chat_rate_limit(
                    session_id=session_id,
                    ip_address=ip_address,
                )
                
                if not allowed:
                    logger.warning(
                        "rate_limit_exceeded",
                        session_id=session_id,
                        ip=ip_address,
                        channel=channel,
                    )
                    return {
                        "message": "You are sending messages too quickly. Please wait a moment.",
                        "session_id": session_id,
                        "sources": [],
                        "confidence": None,
                        "cache_hit": False,
                        "fallback_triggered": True,
                        "rate_limited": True,
                        "retry_after": reset_in,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
            
            # ===============================================================
            # STEP 2: Input Validation (Security & Content)
            # ===============================================================
            try:
                is_valid, sanitized_message, validation_meta = self._input_validator.validate_chat_message(
                    message=message,
                    language=language,
                    channel=channel,
                )
                response_metadata["validation"] = validation_meta
                
            except HostileContentException:
                logger.info("hostile_content_blocked", session_id=session_id, channel=channel)
                response_metadata["intent_detected"] = "hostile_blocked"
                
                return {
                    "message": self.HOSTILE_CONTENT_RESPONSE.get(language, self.HOSTILE_CONTENT_RESPONSE["en"]),
                    "session_id": session_id or str(uuid.uuid4()),
                    "sources": [],
                    "confidence": None,
                    "cache_hit": False,
                    "fallback_triggered": True,
                    "blocked": True,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                
            except PromptInjectionException:
                logger.warning("prompt_injection_blocked", session_id=session_id, channel=channel)
                response_metadata["intent_detected"] = "injection_blocked"
                
                return {
                    "message": self.HOSTILE_CONTENT_RESPONSE.get(language, self.HOSTILE_CONTENT_RESPONSE["en"]),
                    "session_id": session_id or str(uuid.uuid4()),
                    "sources": [],
                    "confidence": None,
                    "cache_hit": False,
                    "fallback_triggered": True,
                    "blocked": True,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                
            except ValidationException as e:
                logger.warning("validation_failed", error=str(e), session_id=session_id)
                return {
                    "message": self.TECHNICAL_ERROR_RESPONSE.get(language, self.TECHNICAL_ERROR_RESPONSE["en"]),
                    "session_id": session_id or str(uuid.uuid4()),
                    "sources": [],
                    "confidence": None,
                    "cache_hit": False,
                    "fallback_triggered": True,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            
            # ===============================================================
            # STEP 3: Session Management (Create fresh session per request)
            # ===============================================================
            from app.core.database import get_session_context
            from app.repositories.session_repository import SessionRepository
            from app.repositories.conversation_repository import ConversationRepository

            # Create a new database session for this request only.
            # This prevents the "connection closed" error that occurs when a shared
            # session is used concurrently by multiple async requests.
            async with get_session_context() as db_session:
                # Create fresh repositories for this request
                session_repo = SessionRepository(db_session)
                conv_repo = ConversationRepository(db_session)

                session_uuid = None
                if session_id:
                    try:
                        session_uuid = uuid.UUID(session_id)
                    except ValueError:
                        pass
                
                # Get or create session using the fresh repositories
                session = await session_repo.get_or_create_session(
                    session_id=session_uuid,
                    channel=channel,
                    language=language,
                    user_agent=user_agent,
                    ip_address=ip_address,
                )
                
                actual_session_id = str(session.id)
                response_metadata["session_id"] = actual_session_id
                
                # Normalize user input for low-literacy users
                if self._input_validator:
                    sanitized_message = await self._input_validator.normalize_user_input(
                        sanitized_message, language
                    )
                    logger.debug("input_normalized", original=message[:50], normalized=sanitized_message[:50])
                
                # Check WhatsApp opt-out
                if channel == "whatsapp" and session.opted_out:
                    logger.info("whatsapp_user_opted_out", session_id=actual_session_id)
                    return {
                        "message": self.STOP_RESPONSE.get(language, self.STOP_RESPONSE["en"]),
                        "session_id": actual_session_id,
                        "sources": [],
                        "confidence": None,
                        "cache_hit": False,
                        "fallback_triggered": True,
                        "opted_out": True,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                
                # ===============================================================
                # STEP 4: Detect Special Intents
                # ===============================================================
                intent, matched_keyword = self._detect_intent(sanitized_message)
                
                if intent:
                    response_metadata["intent_detected"] = intent
                    
                    # Handle STOP intent (WhatsApp opt-out)
                    if intent == "stop" and channel == "whatsapp":
                        await session_repo.opt_out_session(session.id)
                        logger.info("user_opted_out", session_id=actual_session_id)
                    
                    # Handle START intent (WhatsApp opt-in)
                    if intent == "start" and channel == "whatsapp":
                        await session_repo.opt_in_session(session.id)
                        logger.info("user_opted_in", session_id=actual_session_id)
                    
                    intent_response = self._get_intent_response(intent, language, matched_keyword)
                    
                    if intent_response:
                        # Update session activity
                        await session_repo.touch_session(session.id)
                        
                        # Store conversation
                        await conv_repo.create_conversation(
                            session_id=session.id,
                            user_message=sanitized_message,
                            bot_response=intent_response,
                            channel=channel,
                            confidence=1.0,
                            cache_hit=True,
                            fallback_triggered=False,
                        )
                        
                        return {
                            "message": intent_response,
                            "session_id": actual_session_id,
                            "sources": [],
                            "confidence": 1.0,
                            "cache_hit": True,
                            "fallback_triggered": False,
                            "intent": intent,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                
                # ===============================================================
                # STEP 4.5: Handle Keyword-Only Queries
                # ===============================================================
                keyword_response = await self._handle_keyword_query(
                    sanitized_message, language, actual_session_id
                )
                if keyword_response:
                    # Store conversation
                    await conv_repo.create_conversation(
                        session_id=session.id,
                        user_message=sanitized_message,
                        bot_response=keyword_response["message"],
                        channel=channel,
                        sources=[],
                        confidence=0.95,
                        cache_hit=False,
                        llm_model=self._llm_provider.get_model_name() if self._llm_provider else None,
                        fallback_triggered=False,
                    )
                    return keyword_response
                
                # ===============================================================
                # STEP 5: Check Cache
                # ===============================================================
                cache_key = self._get_cache_key(sanitized_message, language)
                cached_response = await cache_service.get_rag_response(sanitized_message)
                
                if cached_response:
                    logger.debug("cache_hit", session_id=actual_session_id, cache_key=cache_key[:16])
                    response_metadata["cache_hit"] = True
                    
                    # Update session
                    await session_repo.touch_session(session.id)
                    
                    # Store conversation
                    await conv_repo.create_conversation(
                        session_id=session.id,
                        user_message=sanitized_message,
                        bot_response=cached_response["message"],
                        channel=channel,
                        sources=cached_response.get("sources", []),
                        confidence=cached_response.get("confidence"),
                        cache_hit=True,
                        fallback_triggered=False,
                    )
                    
                    cached_response["session_id"] = actual_session_id
                    cached_response["cache_hit"] = True
                    cached_response["timestamp"] = datetime.utcnow().isoformat()
                    
                    return cached_response
                
                # ===============================================================
                # STEP 5.5: Query Transformation & HyDE (Intelligence Layer)
                # ===============================================================
                transformer_result = await self._query_transformer.transform_query(sanitized_message)
                
                # Update language based on the smart LLM detection (better than basic input_validator)
                if transformer_result.get("detected_language") and transformer_result.get("detected_language") != "unknown":
                    language = transformer_result["detected_language"]
                    response_metadata["language"] = language
                
                if transformer_result.get("is_casual_conversation"):
                    logger.info("casual_conversation_detected", session_id=actual_session_id)
                    # Bypass RAG entirely for greetings and chit-chat
                    context = ""
                    sources = []
                    confidence = 1.0
                else:
                    # Construct the enhanced query (Optimized Search Query + Original)
                    search_query = sanitized_message
                    optimized = transformer_result.get("optimized_search_query", "")
                    
                    if optimized and optimized != sanitized_message:
                        # We combine the user's original query and the optimized keywords
                        # This gives Qdrant both lexical matches and translated semantic context.
                        search_query = f"{sanitized_message}\n{optimized}".strip()
                        logger.debug("using_optimized_search_query", optimized_length=len(search_query))
                    
                    # ===============================================================
                    # STEP 6: RAG Retrieval
                    # ===============================================================
                    try:
                        context, sources, confidence = await self._rag_service.retrieve_and_build_context(
                            query=search_query,
                            filters={"language": "en"} if language in ["en", "fr", "wolof", "mandinka", "fular"] else None,
                        )
                        
                        response_metadata["rag_confidence"] = confidence
                        response_metadata["sources_count"] = len(sources)
                    
                    except LowConfidenceException as e:
                        logger.info(
                            "low_confidence_fallback",
                            session_id=actual_session_id,
                            score=e.details.get("score", 0),
                            threshold=e.details.get("threshold", 0.7),
                        )
                        response_metadata["fallback_triggered"] = True
                        
                        fallback_message = self.FALLBACK_RESPONSES.get(language, self.FALLBACK_RESPONSES["en"])
                        
                        # Update session
                        await session_repo.touch_session(session.id)
                        
                        # Store conversation
                        await conv_repo.create_conversation(
                            session_id=session.id,
                            user_message=sanitized_message,
                            bot_response=fallback_message,
                            channel=channel,
                            confidence=e.details.get("score", 0.0),
                            cache_hit=False,
                            fallback_triggered=True,
                        )
                        
                        return {
                            "message": fallback_message,
                            "session_id": actual_session_id,
                            "sources": [],
                            "confidence": e.details.get("score", 0.0),
                            "cache_hit": False,
                            "fallback_triggered": True,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                
                # ===============================================================
                # STEP 6.5: Relevance Filtering
                # ===============================================================
                # Check if sources are actually relevant to the question
                if sources and not self._is_response_relevant(sources, sanitized_message, language):
                    logger.info(
                        "irrelevant_sources_filtered",
                        session_id=actual_session_id,
                        sources_count=len(sources),
                        query=sanitized_message[:100],
                    )
                    response_metadata["fallback_triggered"] = True
                    response_metadata["irrelevant_sources"] = True
                    
                    fallback_message = self.FALLBACK_RESPONSES.get(language, self.FALLBACK_RESPONSES["en"])
                    
                    await session_repo.touch_session(session.id)
                    
                    await conv_repo.create_conversation(
                        session_id=session.id,
                        user_message=sanitized_message,
                        bot_response=fallback_message,
                        channel=channel,
                        confidence=confidence if confidence else 0.0,
                        cache_hit=False,
                        fallback_triggered=True,
                    )
                    
                    return {
                        "message": fallback_message,
                        "session_id": actual_session_id,
                        "sources": [],
                        "confidence": confidence if confidence else 0.0,
                        "cache_hit": False,
                        "fallback_triggered": True,
                        "irrelevant_sources": True,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                
                # ===============================================================
                # STEP 7: LLM Generation
                # ===============================================================
                try:
                    llm_start = datetime.utcnow()
                    
                    if language == "wolof":
                        # For Wolof, we let Gemini do the reasoning in English, then translate with Oolel
                        gemini_lang = "en"
                        prompt_with_instructions = f"{sanitized_message}\n\n[CRITICAL INSTRUCTION: You MUST generate your final response in English based strictly on the provided context.]"
                    else:
                        gemini_lang = language
                        prompt_with_instructions = f"{sanitized_message}\n\n[CRITICAL INSTRUCTION: You MUST generate your final response in the following language: {language}. Ensure it sounds natural and conversational.]"
                    
                    generated_response = await self._llm_provider.generate_with_retry(
                        prompt=prompt_with_instructions,
                        context=context,
                        language=gemini_lang,
                        max_retries=4,
                    )
                    
                    if language == "wolof" and await self._oolel_provider.is_available():
                        # Translate the Gemini output to Wolof using Oolel
                        oolel_sys_prompt = "You are a professional translator. Translate the following text into natural, conversational Wolof as spoken in Gambia and Senegal. Keep it authentic and culturally appropriate."
                        try:
                            translated_response = await self._oolel_provider.generate_with_retry(
                                prompt=generated_response,
                                system_prompt=oolel_sys_prompt,
                                max_retries=2
                            )
                            generated_response = translated_response
                        except Exception as e:
                            logger.warning("oolel_translation_failed_fallback_gemini", error=str(e))
                            # Fallback to Gemini for Wolof translation
                            gemini_wolof_prompt = f"Translate the following text into conversational Wolof as spoken in Gambia:\n\n{generated_response}"
                            generated_response = await self._llm_provider.generate_with_retry(
                                prompt=gemini_wolof_prompt,
                                max_retries=2
                            )
                    
                    llm_latency_ms = (datetime.utcnow() - llm_start).total_seconds() * 1000
                    response_metadata["llm_latency_ms"] = llm_latency_ms
                    
                    # Record LLM metrics
                    llm_generation_duration_ms.labels(
                        provider=self._llm_provider.get_provider_name()
                    ).observe(llm_latency_ms)
                    
                except (LLMTimeoutException, LLMUnavailableException) as e:
                    logger.error("llm_generation_failed", error=str(e), session_id=actual_session_id)
                    response_metadata["fallback_triggered"] = True
                    
                    fallback_message = self.TECHNICAL_ERROR_RESPONSE.get(language, self.TECHNICAL_ERROR_RESPONSE["en"])
                    
                    await session_repo.touch_session(session.id)
                    
                    await conv_repo.create_conversation(
                        session_id=session.id,
                        user_message=sanitized_message,
                        bot_response=fallback_message,
                        channel=channel,
                        confidence=confidence if confidence else 0.0,
                        cache_hit=False,
                        fallback_triggered=True,
                        llm_model=self._llm_provider.get_model_name(),
                    )
                    
                    return {
                        "message": fallback_message,
                        "session_id": actual_session_id,
                        "sources": sources,
                        "confidence": confidence if confidence else 0.0,
                        "cache_hit": False,
                        "fallback_triggered": True,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                
                # ===============================================================
                # STEP 8: Output Validation
                # ===============================================================
                is_valid, final_response, output_meta = self._output_validator.validate_response(
                    response=generated_response,
                    sources=sources,
                    channel=channel,
                    strict_mode=False,  # Attempt to fix issues rather than reject
                )
                
                response_metadata["output_validation"] = output_meta
                
                if not is_valid:
                    logger.warning(
                        "output_validation_failed",
                        session_id=actual_session_id,
                        fixes=output_meta.get("fixes_applied", []),
                    )
                    response_metadata["fallback_triggered"] = True
                
                # ===============================================================
                # STEP 9: Cache and Persist
                # ===============================================================
                
                # Cache the response if it's a valid answer
                is_fallback = response_metadata.get("fallback_triggered", False)
                is_no_info = (
                    final_response.startswith("I do not have") or 
                    final_response.startswith("Je ne dispose pas") or
                    "I do not have this specific information" in final_response
                )
                
                if not is_fallback and not is_no_info:
                    response_to_cache = {
                        "message": final_response,
                        "sources": sources,
                        "confidence": confidence if confidence else 0.0,
                    }
                    await cache_service.set_rag_response(
                        question=sanitized_message,
                        response=response_to_cache,
                        ttl=settings.CACHE_RAG_TTL_SECONDS,
                    )
                
                # Update session
                await session_repo.touch_session(session.id)
                
                # Calculate total latency
                total_latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Store conversation
                await conv_repo.create_conversation(
                    session_id=session.id,
                    user_message=sanitized_message,
                    bot_response=final_response,
                    channel=channel,
                    sources=sources,
                    confidence=confidence if confidence else 0.0,
                    latency_ms=int(total_latency_ms),
                    cache_hit=False,
                    llm_model=self._llm_provider.get_model_name(),
                    fallback_triggered=response_metadata.get("fallback_triggered", False),
                )
                
                # ===============================================================
                # STEP 10: Return Response
                # ===============================================================
                
                logger.info(
                    "message_processed",
                    session_id=actual_session_id,
                    channel=channel,
                    confidence=confidence if confidence else 0.0,
                    latency_ms=total_latency_ms,
                    cache_hit=False,
                )
                
                return {
                    "message": final_response,
                    "session_id": actual_session_id,
                    "conversation_id": None,
                    "sources": sources,
                    "confidence": confidence if confidence else 0.0,
                    "cache_hit": False,
                    "fallback_triggered": response_metadata.get("fallback_triggered", False),
                    "latency_ms": int(total_latency_ms),
                    "model_used": self._llm_provider.get_model_name(),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            
        except Exception as e:
            logger.error(
                "chat_service_unexpected_error",
                error=str(e),
                session_id=session_id,
                channel=channel,
                exc_info=True,
            )
            
            # Ultimate fallback
            fallback_message = self.TECHNICAL_ERROR_RESPONSE.get(language, self.TECHNICAL_ERROR_RESPONSE["en"])
            
            return {
                "message": fallback_message,
                "session_id": session_id or str(uuid.uuid4()),
                "sources": [],
                "confidence": None,
                "cache_hit": False,
                "fallback_triggered": True,
                "error": "internal_error",
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    async def process_feedback(
        self,
        conversation_id: str,
        feedback: int,
        session_id: str,
    ) -> bool:
        """
        Process user feedback on a conversation.
        
        Args:
            conversation_id: Conversation ID
            feedback: 1 for positive, -1 for negative
            session_id: Session ID for validation
            
        Returns:
            True if feedback was recorded
        """
        try:
            conversation_uuid = uuid.UUID(conversation_id)
            session_uuid = uuid.UUID(session_id)
            
            updated = await self._conversation_repo.update_feedback(
                conversation_id=conversation_uuid,
                feedback=feedback,
                session_id=session_uuid,
            )
            
            if updated:
                logger.info(
                    "feedback_recorded",
                    conversation_id=conversation_id,
                    feedback=feedback,
                )
            
            return updated
            
        except ValueError:
            logger.warning("invalid_uuid_for_feedback", conversation_id=conversation_id)
            return False
        except Exception as e:
            logger.error("feedback_processing_failed", error=str(e))
            return False
    
    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a session.
        
        Args:
            session_id: Session ID
            limit: Maximum number of conversations to return
            
        Returns:
            List of conversation dicts
        """
        try:
            session_uuid = uuid.UUID(session_id)
            
            conversations = await self._conversation_repo.get_by_session(
                session_id=session_uuid,
                limit=limit,
            )
            
            return [conv.to_dict() for conv in conversations]
            
        except ValueError:
            logger.warning("invalid_session_id_for_history", session_id=session_id)
            return []
        except Exception as e:
            logger.error("history_retrieval_failed", error=str(e))
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of chat service and all dependencies.
        
        Returns:
            Health status dict
        """
        health = {
            "status": "healthy",
            "service": "chat_service",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {},
        }
        
        try:
            self._verify_initialized()
            
            # Check LLM provider
            llm_available = await self._llm_provider.is_available()
            health["components"]["llm"] = {
                "status": "healthy" if llm_available else "unhealthy",
                "provider": self._llm_provider.get_provider_name(),
                "model": self._llm_provider.get_model_name(),
            }
            
            if not llm_available:
                health["status"] = "degraded"
            
            # Check RAG service
            rag_health = await self._rag_service.health_check()
            health["components"]["rag"] = rag_health
            
            if rag_health.get("status") == "unhealthy":
                health["status"] = "degraded"
            
            # Check cache
            cache_stats = await cache_service.get_cache_stats()
            health["components"]["cache"] = {
                "status": "healthy" if cache_stats.get("hit_rate", 0) >= 0 else "degraded",
                "stats": cache_stats,
            }
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["error"] = str(e)
        
        return health