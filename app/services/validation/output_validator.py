"""
Output validation service for Company Bot.
Validates LLM-generated responses before sending to users.
"""

import re
from typing import Tuple, List, Dict, Any, Optional
from datetime import datetime

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class OutputValidator:
    """
    Comprehensive output validation service.
    
    Validates LLM responses for:
    - Minimum/maximum length
    - Forbidden terms
    - Hallucination indicators
    - Response coherence
    - Source attribution
    """
    
    # Generic forbidden terms (offensive language only)
    FORBIDDEN_TERMS = [
        "stupid",
        "idiot",
        "fool",
        "dumb",
    ]
    
    # Minimum response length
    MIN_RESPONSE_LENGTH = 50
    
    # Maximum response length for WhatsApp
    MAX_WHATSAPP_LENGTH = 4000
    
    # Hallucination indicators (phrases that suggest the LLM is making things up)
    HALLUCINATION_INDICATORS = [
        "I think",
        "I believe",
        "probably",
        "maybe",
        "perhaps",
        "I'm not sure but",
        "I guess",
        "it might be",
        "could be",
    ]
    
    # Patterns for detecting invented numbers
    NUMBER_PATTERN = re.compile(r'\b(\d+(?:\.\d+)?%?)\b')
    
    def __init__(self):
        self._forbidden_patterns = [
            re.compile(rf'\b{re.escape(term)}\b', re.IGNORECASE)
            for term in self.FORBIDDEN_TERMS
        ]
    
    def validate_response(
        self,
        response: str,
        sources: List[Dict[str, Any]],
        channel: str = "web",
        strict_mode: bool = True,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate an LLM-generated response.
        
        Args:
            response: Raw LLM response
            sources: Source documents used for RAG
            channel: Response channel (web/whatsapp)
            strict_mode: If True, reject invalid responses; if False, attempt to fix
            
        Returns:
            Tuple of (is_valid, final_response, validation_metadata)
            
        Raises:
            ValidationException: If response is invalid and strict_mode is True
        """
        validation_metadata = {
            "original_length": len(response),
            "channel": channel,
            "validations_performed": [],
            "fixes_applied": [],
        }
        
        final_response = response
        
        # Step 1: Check for empty response
        if not response or not response.strip():
            validation_metadata["validations_performed"].append("empty_response")
            logger.error("empty_response_generated")
            
            if strict_mode:
                from app.core.exceptions import ValidationException
                raise ValidationException("Generated response is empty")
            else:
                final_response = self._get_fallback_response()
                validation_metadata["fixes_applied"].append("replaced_with_fallback")
                return False, final_response, validation_metadata
        
        # Step 2: Slogan check skipped (generic bot)
        validation_metadata["validations_performed"].append("slogan_check_skipped")
        
        # Step 3: Check length
        if len(response) < self.MIN_RESPONSE_LENGTH:
            validation_metadata["validations_performed"].append("response_too_short")
            logger.warning(
                "response_too_short",
                length=len(response),
                min_length=self.MIN_RESPONSE_LENGTH
            )
            
            if strict_mode:
                from app.core.exceptions import ValidationException
                raise ValidationException(f"Response too short: {len(response)} chars")
            # In non-strict mode, we keep it but log
        
        validation_metadata["validations_performed"].append("length_check_passed")
        
        # Step 4: Check for WhatsApp length limit
        if channel == "whatsapp" and len(final_response) > self.MAX_WHATSAPP_LENGTH:
            validation_metadata["validations_performed"].append("whatsapp_length_exceeded")
            final_response = self._truncate_for_whatsapp(final_response)
            validation_metadata["fixes_applied"].append("truncated_for_whatsapp")
            validation_metadata["truncated_length"] = len(final_response)
        
        # Step 5: Check for forbidden terms
        for pattern in self._forbidden_patterns:
            if pattern.search(final_response):
                validation_metadata["validations_performed"].append("forbidden_term_detected")
                matched = pattern.search(final_response).group()
                logger.error(
                    "forbidden_term_in_response",
                    term=matched,
                    response_preview=final_response[:200]
                )
                
                if strict_mode:
                    from app.core.exceptions import ValidationException
                    raise ValidationException(f"Forbidden term detected: {matched}")
                else:
                    # In non-strict mode, we replace with fallback
                    final_response = self._get_fallback_response()
                    validation_metadata["fixes_applied"].append("replaced_with_fallback")
                    return False, final_response, validation_metadata
        
        validation_metadata["validations_performed"].append("forbidden_terms_check_passed")
        
        # Step 6: Check for hallucination indicators
        hallucination_count = 0
        for indicator in self.HALLUCINATION_INDICATORS:
            if indicator.lower() in final_response.lower():
                hallucination_count += 1
        
        if hallucination_count > 2:
            validation_metadata["validations_performed"].append("hallucination_indicators_detected")
            logger.warning(
                "hallucination_indicators_in_response",
                count=hallucination_count,
                response_preview=final_response[:200]
            )
            # Don't reject, but flag for monitoring
        
        # Step 7: Verify numbers against sources (if sources provided)
        if sources:
            numbers_in_response = self.NUMBER_PATTERN.findall(final_response)
            numbers_in_sources = self._extract_numbers_from_sources(sources)
            
            invented_numbers = []
            for num in numbers_in_response:
                if num not in numbers_in_sources and len(num) > 3:
                    invented_numbers.append(num)
            
            if invented_numbers:
                validation_metadata["validations_performed"].append("potential_invented_numbers")
                validation_metadata["invented_numbers"] = invented_numbers[:5]
                logger.warning(
                    "potential_hallucinated_numbers",
                    numbers=invented_numbers[:5],
                    response_preview=final_response[:200]
                )
                # Don't reject, but flag heavily for monitoring
        
        # Step 8: Check for source attribution (if sources provided)
        if sources:
            has_source_attribution = any(
                source.get("document", "") in final_response
                for source in sources
            )
            
            if not has_source_attribution and len(final_response) > 100:
                validation_metadata["validations_performed"].append("missing_source_attribution")
                # Don't reject, but log
        
        validation_metadata["final_length"] = len(final_response)
        
        logger.debug(
            "response_validation_completed",
            **validation_metadata
        )
        
        return True, final_response, validation_metadata
    
    def _extract_numbers_from_sources(self, sources: List[Dict[str, Any]]) -> List[str]:
        """
        Extract all numbers from source texts.
        
        Args:
            sources: List of source chunks
            
        Returns:
            List of number strings found in sources
        """
        numbers = []
        
        for source in sources:
            text = source.get("text", "")
            found = self.NUMBER_PATTERN.findall(text)
            numbers.extend(found)
        
        return numbers
    
    def _truncate_for_whatsapp(self, text: str) -> str:
        """
        Truncate text for WhatsApp if it exceeds length limit.
        
        Args:
            text: Text to truncate
            
        Returns:
            Truncated text
        """
        max_len = self.MAX_WHATSAPP_LENGTH
        
        if len(text) <= max_len:
            return text
        
        truncated = text[:max_len]
        
        # Try to cut at last sentence
        last_period = truncated.rfind('.')
        last_exclaim = truncated.rfind('!')
        last_question = truncated.rfind('?')
        
        cut_point = max(last_period, last_exclaim, last_question)
        
        if cut_point > max_len * 0.7:
            truncated = truncated[:cut_point + 1]
        
        return truncated
    
    def _get_fallback_response(self) -> str:
        """Get a safe fallback response."""
        from app.core.company_config import company
        return company.get_response("error", "en")
    
    def validate_broadcast_message(
        self,
        message: str,
        template_name: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate a broadcast message before sending.
        
        Args:
            message: Broadcast message
            template_name: Optional template name
            
        Returns:
            Tuple of (is_valid, final_message, validation_metadata)
        """
        validation_metadata = {
            "original_length": len(message),
            "template_name": template_name,
            "validations_performed": [],
        }
        
        final_message = message
        
        # Check for empty message
        if not message or not message.strip():
            validation_metadata["validations_performed"].append("empty_message")
            return False, "", validation_metadata
        
        # Check for forbidden terms (stricter for broadcasts)
        for pattern in self._forbidden_patterns:
            if pattern.search(final_message):
                validation_metadata["validations_performed"].append("forbidden_term_detected")
                matched = pattern.search(final_message).group()
                logger.error(
                    "forbidden_term_in_broadcast",
                    term=matched,
                    template=template_name
                )
                return False, "", validation_metadata
        
        # No mandatory slogan for generic bot
        
        validation_metadata["validations_performed"].append("broadcast_validation_passed")
        validation_metadata["final_length"] = len(final_message)
        
        return True, final_message, validation_metadata
    
    def sanitize_for_logging(self, text: str, max_length: int = 200) -> str:
        """
        Sanitize text for safe logging (remove PII, truncate).
        
        Args:
            text: Text to sanitize
            max_length: Maximum length
            
        Returns:
            Sanitized text safe for logs
        """
        # Remove potential PII patterns
        # Email
        text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL]', text)
        # Phone numbers
        text = re.sub(r'\+?[\d\s-]{10,}', '[PHONE]', text)
        # Credit card patterns
        text = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[CARD]', text)
        
        if len(text) > max_length:
            text = text[:max_length] + "..."
        
        return text
