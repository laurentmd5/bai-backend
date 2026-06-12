"""
Input validation service for BARROW.AI.
Validates all incoming user messages for security, length, and content.
"""

import re
import unicodedata
import difflib
from typing import Tuple, Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.core.config import settings
from app.core.logging import get_logger
from app.services.nlp.oolel_corrector import oolel_corrector
from app.core.exceptions import (
    ValidationException,
    HostileContentException,
    PromptInjectionException,
    ErrorCode
)
from app.core.security import (
    detect_sql_injection,
    detect_xss,
    detect_prompt_injection,
    detect_hostile_content,
    sanitize_input,
    html_escape,
    validate_email,
    validate_phone_number,
    validate_uuid,
)

logger = get_logger(__name__)


class InputValidator:
    """
    Comprehensive input validation service.
    
    Validates all user inputs for:
    - Length constraints
    - Character set validation
    - SQL injection detection
    - XSS detection
    - Prompt injection detection
    - Hostile content detection
    - Language detection
    """
    
    # Allowed languages
    ALLOWED_LANGUAGES = {"en", "fr", "mandinka", "wolof"}
    
    # Maximum message length
    MAX_MESSAGE_LENGTH = 2000
    MIN_MESSAGE_LENGTH = 1
    
    # Suspicious Unicode ranges (homoglyph attacks)
    SUSPICIOUS_UNICODE_BLOCKS = [
        (0x0400, 0x04FF),  # Cyrillic (can mimic Latin)
        (0x0500, 0x052F),  # Cyrillic Supplement
        (0x1E00, 0x1EFF),  # Latin Extended Additional
        (0xFF00, 0xFFEF),  # Halfwidth and Fullwidth Forms
    ]
    
    # Encoded content patterns
    ENCODED_PATTERNS = {
        'base64': re.compile(r'(?:[A-Za-z0-9+/]{4}){4,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?'),
        'hex': re.compile(r'(?:[0-9A-Fa-f]{2}\s*){8,}'),
        'url_encode': re.compile(r'%[0-9A-Fa-f]{2}'),
        'unicode_escape': re.compile(r'\\u[0-9A-Fa-f]{4}'),
    }
    
    # Common spam patterns
    SPAM_PATTERNS = [
        re.compile(r'(?i)(viagra|cialis|casino|lottery|winner|prize|million dollar)'),
        re.compile(r'(?i)(cryptocurrency|bitcoin|investment opportunity)'),
        re.compile(r'(?i)(work from home|earn money fast|make \$\d+)'),
    ]
    
    # SMS abbreviations mapping (English & French)
    SMS_ABBREVIATIONS = {
        # English
        "u": "you", "ur": "your", "r": "are", "y": "why",
        "gr8": "great", "lol": "laughing out loud", "thx": "thanks",
        "pls": "please", "plz": "please", "ppl": "people",
        "b4": "before", "2day": "today", "2moro": "tomorrow",
        "4": "for", "2": "to", "4u": "for you", "c": "see",
        "b": "be", "n": "and", "w": "with", "w/o": "without",
        "btw": "by the way", "idk": "i don't know", "lmk": "let me know",
        "tbh": "to be honest", "imo": "in my opinion", "afaik": "as far as i know",
        # French
        "bcp": "beaucoup", "bjr": "bonjour", "bsr": "bonsoir",
        "cad": "c'est-à-dire", "cc": "courriel", "dsl": "désolé",
        "env": "envoyer", "qqch": "quelque chose", "qqn": "quelqu'un",
        "rdv": "rendez-vous", "stp": "s'il te plaît", "svp": "s'il vous plaît",
        "tt": "tout", "ttt": "tout à fait", "vrmt": "vraiment",
    }
    
    # Local acronyms expansion for low-literacy users
    LOCAL_ACRONYMS = {
        "npp": "National People's Party",
        "pace": "Presidential Agency for Community Empowerment",
        "gamtel": "Gambia Telecommunications Company",
        "gamcel": "Gambia Cellular Company",
        "mygov": "My Government platform",
        "it": "information technology",
        "ict": "information and communication technology",
        "ngs": "National Gambia Scholarship",
        "gba": "Greater Banjul Area",
        "nawec": "National Water and Electricity Company",
        "pura": "Public Utilities Regulatory Authority",
        "ecowas": "Economic Community of West African States",
    }
    
    # Common spelling corrections (Gambia-specific)
    SPELL_CORRECTIONS = {
        "intrnet": "internet", "intrenet": "internet", "net": "internet",
        "agrikultur": "agriculture", "agri": "agriculture", "farm": "agriculture",
        "eduka": "education", "skool": "school", "skul": "school",
        "lasante": "health", "sante": "health", "mezin": "medicine",
        "gouv": "governance", "govern": "governance", "gov": "governance",
        "jenes": "youth", "jenn": "youth", "yout": "youth",
        "barow": "barrow", "barrows": "barrow",
        "digita": "digital", "digi": "digital",
        "infrastrukture": "infrastructure", "infra": "infrastructure",
        "ekonomi": "economy", "ekonomie": "economy",
        "sikorite": "security", "sekirite": "security",
    }
    
    # Common words list for difflib
    _COMMON_WORDS = [
        "internet", "agriculture", "education", "health", "governance",
        "youth", "digital", "infrastructure", "economy", "security",
        "npp", "barrow", "gambia", "development", "project", "program",
        "job", "work", "business", "farmer", "school", "hospital",
        "road", "bridge", "water", "electricity", "internet",
    ]
    
    def __init__(self):
        self._blocked_phrases = self._load_blocked_phrases()
    
    def _load_blocked_phrases(self) -> List[str]:
        """
        Load blocked phrases from configuration.
        These are phrases that are absolutely prohibited.
        """
        return [
            "ignore previous instructions",
            "disregard above",
            "system prompt",
            "developer mode",
            "jailbreak",
            "bypass restrictions",
            "act as dan",
            "pretend you are",
            "you are now",
            "new instructions",
        ]
    
    async def normalize_user_input(self, message: str, language: str = "en") -> str:
        """
        Normalize user input for low-literacy users.
        
        Handles:
        - SMS abbreviations (u → you, gr8 → great, etc.)
        - Local acronyms (NPP → National People's Party)
        - Common spelling corrections
        - Multiple punctuation removal
        - Whitespace normalization
        - Oolel Corrector for Wolof informal spelling
        """
        if not message or len(message.strip()) < 2:
            # Very short messages - return a help prompt
            help_prompts = {
                "en": "I'm here to help you learn about President Barrow and NPP achievements. You can ask me about internet, farming, health, schools, or roads.",
                "fr": "Je suis là pour vous informer sur les réalisations du Président Barrow et du NPP. Vous pouvez me poser des questions sur internet, l'agriculture, la santé, l'éducation ou les routes."
            }
            return help_prompts.get(language, help_prompts["en"])
        
        # Apply Oolel-Corrector if language is Wolof (or unknown, acting as a pass-through for English)
        if language in ["wolof", "unknown", ""] and await oolel_corrector.is_available():
            message = await oolel_corrector.normalize_text(message)

        # Convert to lowercase and normalize
        normalized = message.lower().strip()
        
        # Remove multiple spaces
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Expand SMS abbreviations (word boundaries)
        for abbr, expansion in self.SMS_ABBREVIATIONS.items():
            normalized = re.sub(r'\b' + re.escape(abbr) + r'\b', expansion, normalized)
        
        # Expand local acronyms (word boundaries)
        for acro, expansion in self.LOCAL_ACRONYMS.items():
            normalized = re.sub(r'\b' + re.escape(acro) + r'\b', expansion, normalized)
        
        # Apply spelling corrections (word boundaries)
        for wrong, correct in self.SPELL_CORRECTIONS.items():
            normalized = re.sub(r'\b' + re.escape(wrong) + r'\b', correct, normalized)
        
        # Spell correction using difflib for unknown words
        words = normalized.split()
        corrected_words = []
        for word in words:
            if word not in self.SPELL_CORRECTIONS and len(word) > 3:
                matches = difflib.get_close_matches(word, self._COMMON_WORDS, cutoff=0.8)
                if matches and matches[0] != word:
                    corrected_words.append(matches[0])
                    continue
            corrected_words.append(word)
        normalized = ' '.join(corrected_words)
        
        # Map single keywords to full questions
        keyword_map = {
            "internet": "What has NPP done for internet and connectivity?",
            "agriculture": "What are NPP plans for agriculture and food security?",
            "health": "What healthcare reforms does NPP propose?",
            "education": "What is NPP plan for education and skills?",
            "youth": "What are NPP programs for youth empowerment?",
            "governance": "What is NPP plan for good governance?",
            "digital": "What has NPP done for digital transformation?",
            "infrastructure": "What infrastructure projects has NPP completed?",
            "economy": "What has NPP done for the economy and jobs?",
            "security": "What has NPP done for national security?",
        }
        
        # If message is a single word or very short phrase, map to full question
        if len(normalized.split()) <= 3:
            for keyword, question in keyword_map.items():
                if keyword in normalized or normalized == keyword:
                    return question
        
        # Remove multiple punctuation
        normalized = re.sub(r'([!?.]){2,}', r'\1', normalized)
        
        # Ensure message ends with question mark if it looks like a question
        if any(word in normalized for word in ["what", "how", "why", "when", "where", "who", "tell", "explain"]):
            if not normalized.endswith('?'):
                normalized += '?'
        
        return normalized.capitalize()
    
    def _check_unicode_homoglyphs(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Check for suspicious Unicode characters that could be used in homoglyph attacks.
        
        Args:
            text: Input text to check
            
        Returns:
            Tuple of (is_suspicious, reason)
        """
        for char in text:
            code_point = ord(char)
            
            # Check if in suspicious Unicode blocks
            for start, end in self.SUSPICIOUS_UNICODE_BLOCKS:
                if start <= code_point <= end:
                    return True, f"Suspicious Unicode character: U+{code_point:04X}"
            
            # Check for zero-width characters (invisible)
            if code_point in {0x200B, 0x200C, 0x200D, 0xFEFF}:
                return True, f"Zero-width character detected: U+{code_point:04X}"
        
        return False, None
    
    def _detect_encoded_content(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Detect encoded content (Base64, Hex, URL encoding).
        
        Args:
            text: Input text to check
            
        Returns:
            Tuple of (has_encoded, encoding_type)
        """
        for encoding_type, pattern in self.ENCODED_PATTERNS.items():
            if pattern.search(text):
                return True, encoding_type
        
        return False, None
    
    def _check_spam_patterns(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Check for common spam patterns.
        
        Args:
            text: Input text to check
            
        Returns:
            Tuple of (is_spam, matched_pattern)
        """
        for pattern in self.SPAM_PATTERNS:
            match = pattern.search(text)
            if match:
                return True, match.group()
        
        return False, None
    
    def _normalize_unicode(self, text: str) -> str:
        """
        Normalize Unicode text to NFC form.
        This helps prevent homoglyph attacks.
        
        Args:
            text: Input text
            
        Returns:
            Normalized text
        """
        return unicodedata.normalize('NFC', text)
    
    def _analyze_sentiment_context(self, text: str) -> Dict[str, Any]:
        """
        SECURITY FLAIR #1 FIX: Analyze sentiment and context to distinguish 
        legitimate inquiries from actual hostile content.
        
        Replaces aggressive phrase-based blocking with contextual analysis.
        Allows legitimate political/critical questions while blocking actual attacks.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dictionary with:
            - risk_level: "low", "medium", "high"
            - is_legitimate_question: bool (allows critical but constructive questions)
            - action: "allow", "block", "allow_with_logging"
            - reason: Explanation of assessment
        """
        text_lower = text.lower()
        
        # Check for actual hostile markers (violence, threats, abuse)
        hostile_markers = {
            'violence': [
                r'\bkill\b.*\b(you|them|us)',
                r'\bstab\b.*\b(you|them|us)',
                r'\bshoot\b.*\b(you|them|us)',
                r'\bharm\b.*\b(you|them|us)',
            ],
            'threats': [
                r'\bi\'?ll\s+(?:beat|kill|hurt)',
                r'\byou\'?re\s+(?:dead|done)',
                r'\bwill\s+(?:destroy|eliminate)',
            ],
            'profanity': [
                r'\bf[*u]ck',
                r'\bsh[*i]t',
                r'\bd[*a]mn',
            ],
        }
        
        # Check for actual hostile content
        for category, patterns in hostile_markers.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return {
                        "risk_level": "high",
                        "is_legitimate_question": False,
                        "action": "block",
                        "reason": f"Actual {category} detected in message"
                    }
        
        # Check for legitimate question patterns (political, critical, factual inquiries)
        legitimate_patterns = [
            r'\bwhat\s+(?:are|is)\s+.*(?:failures|problems|criticisms)',
            r'\bwhy\s+(?:did|does|do).*(?:fail|struggle|lose)',
            r'\btell\s+(?:me|us)\s+about.*(?:weaknesses|challenges|issues)',
            r'\bhow\s+(?:has|have|do).*(?:failed|struggled)',
            r'\bwhat\s+(?:mistakes|errors|issues)',
            r'\bcritique\s+',
            r'\banalysis\s+(?:of|on)',
        ]
        
        is_likely_question = any(re.search(pattern, text_lower) for pattern in legitimate_patterns)
        
        # If it looks like a legitimate question, allow it
        if is_likely_question:
            return {
                "risk_level": "low",
                "is_legitimate_question": True,
                "action": "allow",
                "reason": "Legitimate critical inquiry detected"
            }
        
        # Neutral/informational queries are fine
        if len(text) < 30 or re.search(r'\?$', text.strip()):
            return {
                "risk_level": "low",
                "is_legitimate_question": True,
                "action": "allow",
                "reason": "Appears to be informational query"
            }
        
        # Default to allowing unless we found actual hostile markers
        return {
            "risk_level": "low",
            "is_legitimate_question": True,
            "action": "allow",
            "reason": "Content appears non-hostile"
        }
    
    def validate_chat_message(
        self,
        message: str,
        language: str = "en",
        channel: str = "web",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Comprehensive validation of chat messages.
        
        Args:
            message: Raw user message
            language: Message language
            channel: Message channel (web/whatsapp)
            
        Returns:
            Tuple of (is_valid, sanitized_message, validation_metadata)
            
        Raises:
            ValidationException: For validation errors
            HostileContentException: For hostile content
            PromptInjectionException: For prompt injection attempts
        """
        validation_metadata = {
            "original_length": len(message),
            "channel": channel,
            "language": language,
            "validations_performed": [],
        }
        
        # Step 1: Check if empty
        if not message or not message.strip():
            validation_metadata["validations_performed"].append("empty_check_failed")
            raise ValidationException(
                "Message cannot be empty",
                details={"reason": "empty_message"}
            )
        
        # Step 2: Check length
        if len(message) > self.MAX_MESSAGE_LENGTH:
            validation_metadata["validations_performed"].append("length_check_failed")
            raise ValidationException(
                f"Message too long: {len(message)} characters (max {self.MAX_MESSAGE_LENGTH})",
                details={"current_length": len(message), "max_length": self.MAX_MESSAGE_LENGTH}
            )
        
        if len(message.strip()) < self.MIN_MESSAGE_LENGTH:
            validation_metadata["validations_performed"].append("length_check_failed")
            raise ValidationException(
                f"Message too short: minimum {self.MIN_MESSAGE_LENGTH} character",
                details={"current_length": len(message.strip()), "min_length": self.MIN_MESSAGE_LENGTH}
            )
        
        validation_metadata["validations_performed"].append("length_check_passed")
        
        # Step 3: Check language
        if language not in self.ALLOWED_LANGUAGES:
            validation_metadata["language"] = "en"  # Fallback to English
            validation_metadata["validations_performed"].append("language_fallback")
        
        # Step 4: Normalize Unicode
        original_message = message
        message = self._normalize_unicode(message)
        if message != original_message:
            validation_metadata["validations_performed"].append("unicode_normalized")
        
        # Step 5: Check for Unicode homoglyphs
        is_suspicious, reason = self._check_unicode_homoglyphs(message)
        if is_suspicious:
            logger.warning(
                "unicode_homoglyph_detected",
                reason=reason,
                message_preview=message[:100]
            )
            validation_metadata["validations_performed"].append("homoglyph_detected")
            # Don't reject, but log for monitoring
        
        # Step 6: Check for encoded content
        has_encoded, encoding_type = self._detect_encoded_content(message)
        if has_encoded:
            logger.warning(
                "encoded_content_detected",
                encoding_type=encoding_type,
                message_preview=message[:100]
            )
            validation_metadata["validations_performed"].append(f"encoded_{encoding_type}_detected")
            # Don't reject immediately, but flag for closer inspection
        
        # Step 7: Check for XSS (CRITICAL - REJECT)
        if detect_xss(message):
            validation_metadata["validations_performed"].append("xss_detected")
            logger.warning(
                "xss_attempt_blocked",
                message_preview=message[:100],
                channel=channel
            )
            raise ValidationException(
                "Invalid message content",
                details={"reason": "xss_pattern_detected"}
            )
        
        validation_metadata["validations_performed"].append("xss_check_passed")
        
        # Step 8: Check for prompt injection (CRITICAL - REJECT)
        if detect_prompt_injection(message):
            validation_metadata["validations_performed"].append("prompt_injection_detected")
            logger.warning(
                "prompt_injection_blocked",
                message_preview=message[:100],
                channel=channel
            )
            raise PromptInjectionException()
        
        # Additional check for blocked phrases
        for phrase in self._blocked_phrases:
            if phrase.lower() in message.lower():
                validation_metadata["validations_performed"].append("blocked_phrase_detected")
                logger.warning(
                    "blocked_phrase_detected",
                    phrase=phrase,
                    message_preview=message[:100]
                )
                raise PromptInjectionException()
        
        validation_metadata["validations_performed"].append("prompt_injection_check_passed")
        
        # Step 9: Check for hostile content with contextual analysis (SECURITY FLAIR #1 FIX)
        sentiment_analysis = self._analyze_sentiment_context(message)
        
        if sentiment_analysis["action"] == "block":
            validation_metadata["validations_performed"].append("hostile_content_detected")
            logger.warning(
                "hostile_content_blocked",
                reason=sentiment_analysis["reason"],
                message_preview=message[:100],
                channel=channel
            )
            raise HostileContentException()
        elif sentiment_analysis["action"] == "allow_with_logging":
            validation_metadata["validations_performed"].append("suspicious_content_logged")
            logger.info(
                "suspicious_content_allowed",
                reason=sentiment_analysis["reason"],
                risk_level=sentiment_analysis["risk_level"],
                message_preview=message[:100],
                channel=channel
            )
        else:
            # Allow
            validation_metadata["validations_performed"].append("hostile_check_passed")
        
        # Step 10: Check for spam (WARNING ONLY)
        is_spam, spam_pattern = self._check_spam_patterns(message)
        if is_spam:
            validation_metadata["validations_performed"].append("spam_pattern_detected")
            logger.info(
                "spam_pattern_detected",
                pattern=spam_pattern,
                message_preview=message[:100]
            )
            # Don't reject, but flag for analytics
        
        # Step 11: Check for SQL injection (WARNING ONLY - could be legitimate question)
        if detect_sql_injection(message):
            validation_metadata["validations_performed"].append("sql_pattern_detected")
            logger.info(
                "sql_pattern_in_message",
                message_preview=message[:100]
            )
            # Don't reject - user might be asking about SQL
        
        # Step 12: Sanitize input
        sanitized = sanitize_input(message)
        sanitized = html_escape(sanitized)
        
        validation_metadata["validations_performed"].append("sanitization_completed")
        validation_metadata["sanitized_length"] = len(sanitized)
        
        logger.debug(
            "message_validation_passed",
            **validation_metadata
        )
        
        return True, sanitized, validation_metadata
    
    def validate_session_id(self, session_id: Optional[str]) -> Optional[str]:
        """
        Validate session ID format.
        
        Args:
            session_id: Session ID to validate
            
        Returns:
            Validated session ID or None
            
        Raises:
            ValidationException: If invalid format
        """
        if session_id is None:
            return None
        
        if not validate_uuid(session_id):
            raise ValidationException(
                "Invalid session_id format - must be UUID v4",
                details={"provided": session_id}
            )
        
        return session_id.lower()
    
    def validate_email(self, email: str) -> str:
        """
        Validate email address.
        
        Args:
            email: Email to validate
            
        Returns:
            Normalized email
            
        Raises:
            ValidationException: If invalid
        """
        if not email or not email.strip():
            raise ValidationException("Email cannot be empty")
        
        email = email.strip().lower()
        
        if not validate_email(email):
            raise ValidationException(
                "Invalid email format",
                details={"provided": email}
            )
        
        return email
    
    def validate_phone_number(self, phone: str) -> str:
        """
        Validate phone number in E.164 format.
        
        Args:
            phone: Phone number to validate
            
        Returns:
            Normalized phone number
            
        Raises:
            ValidationException: If invalid
        """
        if not phone or not phone.strip():
            raise ValidationException("Phone number cannot be empty")
        
        phone = phone.strip()
        
        if not validate_phone_number(phone):
            raise ValidationException(
                "Invalid phone number format - must be E.164 (e.g., +2201234567)",
                details={"provided": phone}
            )
        
        return phone
    
    def validate_password_strength(self, password: str) -> Tuple[bool, List[str]]:
        """
        Validate password strength.
        
        Requirements:
        - At least 12 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        - Not a common password
        
        Args:
            password: Password to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        if len(password) < 12:
            issues.append("Password must be at least 12 characters long")
        
        if not re.search(r"[A-Z]", password):
            issues.append("Password must contain at least one uppercase letter")
        
        if not re.search(r"[a-z]", password):
            issues.append("Password must contain at least one lowercase letter")
        
        if not re.search(r"\d", password):
            issues.append("Password must contain at least one digit")
        
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            issues.append("Password must contain at least one special character")
        
        # Check common passwords
        common_passwords = [
            "password", "password123", "admin123", "barrow2024", "npp2024",
            "12345678", "qwerty123", "gambia2024", "president2024"
        ]
        
        if password.lower() in common_passwords:
            issues.append("Password is too common or easily guessable")
        
        # Check for repeated characters
        if re.search(r"(.)\1{3,}", password):
            issues.append("Password contains too many repeated characters")
        
        # Check for sequential characters
        sequential_patterns = [
            "abcdefgh", "12345678", "qwertyui", "asdfghjk"
        ]
        for pattern in sequential_patterns:
            if pattern in password.lower():
                issues.append("Password contains sequential characters")
                break
        
        return len(issues) == 0, issues
    
    def validate_language(self, language: str) -> str:
        """
        Validate and normalize language code.
        
        Args:
            language: Language code to validate
            
        Returns:
            Normalized language code
        """
        language = language.lower().strip()
        
        if language not in self.ALLOWED_LANGUAGES:
            logger.debug(
                "language_not_allowed_falling_back",
                requested=language,
                fallback="en"
            )
            return "en"
        
        return language
    
    def detect_language(self, text: str) -> str:
        """
        Detect the language of a text.

        Strategy (layered):
        1. Check for Gambian local languages (Mandinka, Wolof) via keyword matching
           — langdetect doesn't know these.
        2. Use langdetect (statistical model, ~200 languages) for fr/en.
        3. Fallback to keyword-based French detection if langdetect unavailable.
        4. Default to "en".

        Args:
            text: Text to analyze

        Returns:
            Language code: "en", "fr", "mandinka", or "wolof"
        """
        if not text or len(text.strip()) < 3:
            return "en"

        text_lower = text.lower()
        words = set(text_lower.split())

        # ── 1. Gambian local languages (keyword priority) ──────────────────
        mandinka_indicators = {
            "salaam", "aleikum", "nna", "tang", "nyaa", "siita",
            "foloo", "koto", "bara", "jula", "mansa", "wuloo",
        }
        wolof_indicators = {
            # Salutations & Politesse
            "jërejëf", "waaw", "déedéet", "nanga", "naka", "salaamalekum", "maangi", "fi", "rekk", "sant",
            # Question words
            "ki", "mo", "kan", "lan", "fan", "lu", "tudd", "ñata", "ñaata", "ndax", "loo", "noo", "nu", "foo", "kuy", "yan", "ban",
            # Pronouns & Possessives
            "man", "yaw", "yow", "mom", "moom", "ñun", "yeen", "ñom", "sama", "sa", "sunu", "seen", "kii", "ñii", "lii", "yii", "koku", "boku", "loku",
            # Verbs
            "xam", "xamam", "am", "baax", "def", "wax", "jox", "jël", "dox", "dem", "ñëw", "toog", "taxaw", "xool", "gis", "dégg", "ladj", "laaj", "mën", "war", "bëgg", "jang", "liggéey", "fey", "fay", "bind", "door", "daw", "nelaw", "dimbali", "jappale", "indi",
            # Nouns
            "dëkk", "nit", "gox", "réew", "kër", "mbir", "jëf", "xale", "mag", "góor", "jigéen", "jamma", "xaalis", "koppar", "ndox", "ceeb", "yapp", "jën", "taalibe", "seriñ", "tubaab", "ndaw", "mbok",
            # Adverbs, Adjectives & Prepositions
            "leggi", "léegi", "tay", "suba", "démb", "at", "weer", "bes", "fii", "fale", "ndeke", "ndaxte", "ngir", "pur", "lepp", "dara", "bu", "su", "ci", "ba", "bi", "mi", "yi", "ñi", "aka", "torop", "tuti", "bu_baax",
            # Numbers
            "benn", "ñaar", "ñett", "ñeent", "juróom", "fukk",
            # Particles
            "la", "na", "da", "di", "dana", "dina", "nga", "ngi", "ko", "ma", "ga", "ñu"
        }
        wolof_phrases = [
            "na nga def", "naka nga def", "naka def", "nuyu naa la", "jamm nga am", 
            "ba beneen", "lu xew", "lu khew", "numu tudd", "naka la tudd", "lo bëgg", 
            "fan la", "kan la", "lan la", "ndax mën nga", "dama bëgg", "dafa am", 
            "mën nga ma", "wax ma", "dimbali ma", "naka sa", "naka mu", "ana sa"
        ]

        mandinka_score = len(mandinka_indicators & words)
        wolof_score    = len(wolof_indicators & words) + sum(1 for p in wolof_phrases if p in text_lower)

        if mandinka_score >= 2:
            return "mandinka"
        if wolof_score >= 1:
            return "wolof"

        # ── 2. langdetect for fr / en ──────────────────────────────────────
        try:
            from langdetect import detect, DetectorFactory  # type: ignore[import]
            DetectorFactory.seed = 42  # deterministic
            detected = detect(text)
            if detected == "fr":
                return "fr"
            # Any other code defaults to "en"
            return "en"
        except Exception:
            pass

        # ── 3. Keyword fallback for French ────────────────────────────────
        french_words = {
            "bonjour", "salut", "merci", "comment", "pourquoi",
            "je", "tu", "nous", "vous", "est", "sont", "avec",
            "pour", "dans", "sur", "que", "qui", "quoi", "quel",
            "quelle", "les", "des", "une", "monsieur", "madame",
            "oui", "non", "aussi", "très", "bien", "mal",
        }
        french_score = len(french_words & words)
        if french_score >= 2:
            return "fr"

        return "en"