import json
from typing import Dict, Any, Tuple, Optional
from app.services.interfaces.llm_provider import ILLMProvider
from app.core.logging import get_logger

logger = get_logger(__name__)


class QueryTransformer:
    """
    Handles Query Rewriting, Language Detection, and HyDE (Hypothetical Document Embeddings)
    to bridge the lexical and semantic gap for poorly structured queries.
    
    Provider order: Groq (primary) -> Gemini (fallback)
    """
    
    def __init__(self, groq_provider: ILLMProvider, gemini_provider: ILLMProvider = None):
        """
        Initialize QueryTransformer with Groq as primary and Gemini as fallback.
        
        Args:
            groq_provider: Primary LLM provider (Groq)
            gemini_provider: Optional fallback LLM provider (Gemini)
        """
        self._groq_provider = groq_provider
        self._llm = gemini_provider  # Gemini as fallback
        
    async def transform_query(self, raw_query: str, history: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyzes the user's raw query to detect language, rewrite it into an optimal search query,
        and optionally generate a hypothetical answer for HyDE.
        
        Returns a dict:
        {
            "detected_language": "en",  # or "fr"
            "optimized_search_query": "The rewritten question in English/French with good keywords",
            "hypothetical_document": "A theoretical answer to help semantic matching (HyDE)",
            "is_casual_conversation": false
        }
        """
        
        system_prompt = """
        You are an expert Search Query Transformer and Linguist for a Retrieval-Augmented Generation (RAG) system.
        The system has a knowledge base consisting of official company documents about products, services, technical documentation, and support information.
        
        Your task is to analyze the user's raw input and output a JSON object with the following fields:
        1. "detected_language": Detect the language of the user's input. Detect the primary language. Output "en" for English or "fr" for French. If uncertain, default to "fr".
        2. "is_casual_conversation": true if the input is just a greeting, chit-chat, or clearly doesn't require searching a document database. false otherwise.
        3. "optimized_search_query": Translate the query to standard English, fix any spelling/grammar errors, and expand it with highly relevant keywords that might appear in official documents. 
           CRITICAL: If conversation history is provided, and the user's input is short (e.g., "Yes", "And?", "What about health?"), use the context from the history to formulate a complete, standalone search query.
           CRITICAL: DO NOT DROP OR REPLACE SPECIFIC NOUNS, NAMES, OR TECHNICAL TERMS FROM THE ORIGINAL QUERY (e.g., "product name", "service name", etc.). ALWAYS preserve the core entities the user asked about. If it's a casual conversation, leave this empty.
        
        CRITICAL: Your output MUST be valid JSON, with no markdown formatting blocks like ```json around it. Just the raw JSON object.
        """
        
        prompt = f"""
        Historique de la conversation :
        {history if history else 'Aucun historique récent.'}

        Question actuelle de l'utilisateur : {raw_query}

        INSTRUCTION CRITIQUE : Si la question actuelle est une réponse courte (ex: "Yes", "No", "Tell me more") ou fait référence à un sujet précédent, vous DEVEZ utiliser l'historique pour reformuler la question de manière complète et indépendante.
        """
        
        # =====================================================================
        # PRIMARY: Groq
        # =====================================================================
        if self._groq_provider and await self._groq_provider.is_available():
            try:
                logger.info("query_transformation_via_groq", query=raw_query)
                response = await self._groq_provider.generate_with_retry(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_retries=2
                )
                
                result = self._parse_json_response(response)
                if result:
                    logger.info(
                        "query_transformed",
                        provider="groq",
                        original=raw_query,
                        language=result.get("detected_language"),
                        optimized=result.get("optimized_search_query")
                    )
                    return result
                    
            except Exception as groq_e:
                logger.warning(
                    "groq_query_transformation_failed_falling_back_to_gemini",
                    error=str(groq_e),
                    query=raw_query
                )
        else:
            logger.warning("groq_provider_unavailable_using_gemini", query=raw_query)
        
        # =====================================================================
        # FALLBACK: Gemini
        # =====================================================================
        if self._llm:
            try:
                logger.info("query_transformation_via_gemini_fallback", query=raw_query)
                response = await self._llm.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=0.1,
                )
                
                result = self._parse_json_response(response)
                if result:
                    logger.info(
                        "query_transformed",
                        provider="gemini",
                        original=raw_query,
                        language=result.get("detected_language"),
                        optimized=result.get("optimized_search_query")
                    )
                    return result
                    
            except Exception as gemini_e:
                logger.error(
                    "gemini_query_transformation_failed",
                    error=str(gemini_e),
                    query=raw_query
                )
        
        # =====================================================================
        # ULTIMATE FALLBACK: Return raw query
        # =====================================================================
        logger.error("all_query_transformers_failed", query=raw_query)
        return {
            "detected_language": None,  # Preserves existing session language
            "is_casual_conversation": False,
            "optimized_search_query": raw_query,
            "hypothetical_document": None
        }
    
    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Parse JSON from LLM response, handling markdown backticks and extra text.
        
        Args:
            response: Raw LLM response string
            
        Returns:
            Parsed JSON dict or None if parsing fails
        """
        if not response:
            return None
            
        try:
            # Clean up markdown backticks
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()
            
            # Extract only the first JSON object to avoid "Extra data" errors
            brace_count = 0
            first_json_end = -1
            for i, char in enumerate(cleaned_response):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        first_json_end = i + 1
                        break
            if first_json_end > 0:
                cleaned_response = cleaned_response[:first_json_end]
            
            result = json.loads(cleaned_response)
            return result
            
        except json.JSONDecodeError as e:
            logger.error("json_parsing_failed", error=str(e), response_preview=response[:200])
            return None
        except Exception as e:
            logger.error("response_parsing_failed", error=str(e))
            return None