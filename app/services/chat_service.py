"""
Chat Service — Main orchestrator for the chatbot engine.
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
from app.services.llm.groq_provider import GroqProvider
from app.services.llm.query_transformer import QueryTransformer
from app.services.validation.input_validator import InputValidator
from app.services.validation.output_validator import OutputValidator
from app.services.validation.security_validator import SecurityValidator
from app.services.cache.redis_cache import cache_service, CacheNamespace
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.session_repository import SessionRepository
from app.core.config import settings
from app.core.company_config import company
from app.core.logging import get_logger
from app.services.recruitment.recruiter_agent import recruiter_agent
from app.core.metrics import (
    llm_generation_duration_ms,
    record_chat_message,
    record_chat_latency,
    record_chat_error,
    record_rag_fallback,
    record_llm_duration,
    record_llm_tokens,
    record_security_violation,
)


from app.core.exceptions import (
    BotException,
    LowConfidenceException,
    LLMTimeoutException,
    LLMUnavailableException,
    LLMException,
    HostileContentException,
    PromptInjectionException,
    ValidationException,
)

logger = get_logger(__name__)


class ChatService:
    """
    Main orchestrator for the company chatbot.
    
    Coordinates the complete conversation flow:
    1. Input validation and security checks
    2. Session management
    3. Intent detection
    4. Cache lookup
    5. RAG retrieval
    6. LLM generation
    7. Output validation
    8. Persistence and analytics
    """

    SPECIAL_INTENTS = {
        "greeting": ["hello", "hi", "hey", "bonjour", "salut", "bonsoir"],
        "help": ["help", "aide", "menu", "what can you do", "capabilities", "que peux-tu faire"],
        "thanks": ["thank", "merci", "thanks", "thank you", "je vous remercie"],
        "stop": ["stop", "unsubscribe", "désabonner", "opt out", "opt-out"],
        "start": ["start", "subscribe", "réabonner", "opt in", "opt-in"],
        "status": ["status", "health", "ping", "test"],
    }

    RELEVANCE_KEYWORDS = {
        "network": ["network", "réseau", "lan", "wan", "wifi", "vpn", "firewall"],
        "security": ["security", "sécurité", "cybersecurity", "antivirus", "threat"],
        "support": ["support", "aide", "ticket", "incident", "troubleshoot", "depannage"],
        "infrastructure": ["server", "serveur", "cloud", "datacenter", "storage", "backup"],
        "services": ["service", "solution", "contrat", "maintenance", "sla", "devis"],
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

        self._groq_provider = GroqProvider()
        
        # Initialize query transformer for advanced intelligence
        self._query_transformer = QueryTransformer(self._llm_provider, self._groq_provider)
        
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
        # Exclude conversational short answers
        conversational_short_words = ['yes', 'no', 'why', 'who', 'how', 'what', 'more', 'oui', 'non']
        if len(message_lower) < 5 and message_lower not in conversational_short_words:
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
            return company.get_response("greeting", language)
        
        if intent == "help":
            return company.get_response("help", language)
        
        if intent == "thanks":
            return None  # Let LLM handle naturally, but with positive tone
        
        if intent == "stop":
            return company.get_response("stop", language)
        
        if intent == "start":
            return company.get_response("start", language)
        
        if intent == "status":
            return f"{company.bot_name} is operational and ready to assist you."
        
        return None
    
    async def _handle_keyword_query(
        self,
        message: str,
        language: str,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Keyword shortcutting removed: all queries go through RAG for accuracy."""
        return None

    def _get_cache_key(self, message: str, language: str, session_id: str = "global") -> str:
        """
        Generate cache key for RAG response.
        
        Args:
            message: User message
            language: Detected language
            session_id: The session ID to make cache contextual
            
        Returns:
            Cache key
        """
        import hashlib
        hashed_message = hashlib.sha256(message.lower().strip().encode()).hexdigest()
        return f"rag:response:{session_id}:{hashed_message}:{language}"
    
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
        
        if len(sources) > 1 and len(unique_chunks) == 1:
            logger.warning("all_sources_identical", chunks=len(sources))
            return False
            
        if len(unique_chunks) == 1:
            # We accept the unique chunk even if the score is low, because the RAG is not well-fed yet
            pass
        
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
        
        # 3. Accept all themes based on Qdrant semantic score
        return True
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
            language: Preferred language (en, fr)
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
                
                external_id = None
                if metadata:
                    external_id = metadata.get("phone_number") or metadata.get("cookie_id")
                
                # NOUVEAU LOG POUR GARANTIR LE DEBUG
                logger.info(
                    "attempting_session_retrieval", 
                    passed_session_id=str(session_uuid) if session_uuid else None, 
                    passed_external_id=external_id, 
                    channel=channel
                )
                
                # Get or create session using the fresh repositories
                session = await session_repo.get_or_create_session(
                    session_id=session_uuid,
                    channel=channel,
                    external_id=external_id,
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
                # STEP 4.2: Recruiter Agent Screening Interview
                # ===============================================================
                recruiter_res = await recruiter_agent.process_candidate_message(
                    session_id=actual_session_id,
                    user_message=sanitized_message,
                    channel=channel
                )
                if not recruiter_res:
                    # Check if candidate expresses job/stage intent via text
                    is_recruitment, detected_role = recruiter_agent.is_recruitment_intent(sanitized_message)
                    if is_recruitment:
                        recruiter_res = await recruiter_agent.start_text_interview(
                            session_id=actual_session_id,
                            role=detected_role,
                            user_message=sanitized_message,
                            channel=channel
                        )

                if recruiter_res:
                    await session_repo.touch_session(session.id)
                    await conv_repo.create_conversation(
                        session_id=session.id,
                        user_message=sanitized_message,
                        bot_response=recruiter_res["message"],
                        channel=channel,
                        sources=[],
                        confidence=1.0,
                        cache_hit=False,
                        llm_model="RecruiterAgent",
                        fallback_triggered=False,
                    )
                    recruiter_res["timestamp"] = datetime.utcnow().isoformat()
                    return recruiter_res

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
                cache_key = self._get_cache_key(sanitized_message, language, actual_session_id)
                cached_response = await cache_service.get_rag_response(sanitized_message, actual_session_id)
                
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
                    
                    total_latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    record_chat_message(channel=channel, language=language, cache_hit=True)
                    record_chat_latency(channel=channel, latency_ms=total_latency_ms)
                    
                    return cached_response
                
                # ===============================================================
                # STEP 5.5: Query Transformation & HyDE (Intelligence Layer)
                # ===============================================================
                # Fetch conversation history early for context using the current request's conv_repo
                history_text = ""
                try:
                    recent_convs = await conv_repo.get_recent_by_session(session.id, limit=6)
                    if recent_convs:
                        history_lines = []
                        for conv in recent_convs:
                            history_lines.append(f"Utilisateur: {conv.user_message}")
                            history_lines.append(f"Assistant: {conv.bot_response}")
                        history_text = "\n".join(history_lines)
                except Exception as e:
                    logger.error("failed_to_fetch_history", error=str(e))
                
                transformer_result = await self._query_transformer.transform_query(sanitized_message, history=history_text)
                
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
                            filters=None,
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
                    
                    # Use previously fetched conversation history
                    
                    gemini_lang = language
                    prompt_with_instructions = sanitized_message
                    
                    generated_response = await self._llm_provider.generate_with_retry(
                        prompt=prompt_with_instructions,
                        context=context,
                        language=gemini_lang,
                        history=history_text,
                        max_retries=settings.GEMINI_MAX_RETRIES,
                    )
                    
                    llm_latency_ms = (datetime.utcnow() - llm_start).total_seconds() * 1000
                    response_metadata["llm_latency_ms"] = llm_latency_ms
                    
                    # Record LLM metrics
                    llm_generation_duration_ms.labels(
                        provider=self._llm_provider.get_provider_name()
                    ).observe(llm_latency_ms)
                    
                    if generated_response:
                        prompt_toks = int(len(prompt_with_instructions.split()) * 1.5 + len(context.split()) * 1.5)
                        comp_toks = int(len(generated_response.split()) * 1.5)
                        record_llm_tokens(
                            provider=self._llm_provider.get_provider_name(),
                            model=self._llm_provider.get_model_name(),
                            prompt_tokens=prompt_toks,
                            completion_tokens=comp_toks
                        )

                    
                except LLMException as e:
                    logger.error("llm_generation_failed", error=str(e), session_id=actual_session_id)
                    
                    # Try to use Groq as a fallback for answer generation
                    generated_response = None
                    if await self._groq_provider.is_available():
                        try:
                            logger.info("using_groq_as_fallback_for_llm_generation", session_id=actual_session_id)
                            generated_response = await self._groq_provider.generate_with_retry(
                                prompt=prompt_with_instructions,
                                context=context,
                                language=gemini_lang,
                                history=history_text,
                                max_retries=2
                            )
                            # Record LLM latency
                            llm_latency_ms = (datetime.utcnow() - llm_start).total_seconds() * 1000
                            response_metadata["llm_latency_ms"] = llm_latency_ms
                            response_metadata["fallback_llm"] = "groq"
                            
                        except Exception as groq_e:
                            logger.error("groq_fallback_generation_failed", error=str(groq_e))
                            
                    if not generated_response:
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
                        session_id=actual_session_id,
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
                record_chat_message(channel=channel, language=language, cache_hit=False)
                record_chat_latency(channel=channel, latency_ms=total_latency_ms)
                if response_metadata.get("fallback_triggered", False):
                    record_rag_fallback()
                
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
            record_chat_error(error_type=type(e).__name__)
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
            # Handle asyncpg UUID objects that don't have .replace()
            session_uuid = uuid.UUID(str(session_id))
            
            conversations = await self._conversation_repo.get_recent_by_session(
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



