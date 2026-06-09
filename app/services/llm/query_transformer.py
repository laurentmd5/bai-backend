import json
from typing import Dict, Any, Tuple
from app.services.interfaces.llm_provider import ILLMProvider
from app.core.logging import get_logger

logger = get_logger(__name__)

class QueryTransformer:
    """
    Handles Query Rewriting, Language Detection, and HyDE (Hypothetical Document Embeddings)
    to bridge the lexical and semantic gap for poorly structured or Wolof queries.
    """
    
    def __init__(self, llm_provider: ILLMProvider):
        self._llm = llm_provider
        
    async def transform_query(self, raw_query: str) -> Dict[str, Any]:
        """
        Analyzes the user's raw query to detect language, rewrite it into an optimal search query,
        and optionally generate a hypothetical answer for HyDE.
        
        Returns a dict:
        {
            "detected_language": "wolof", # or "en", "fr", "francolof"
            "optimized_search_query": "The rewritten question in English/French with good keywords",
            "hypothetical_document": "A theoretical answer to help semantic matching (HyDE)",
            "is_casual_conversation": false
        }
        """
        
        system_prompt = """
        You are an expert Search Query Transformer and Linguist for a Retrieval-Augmented Generation (RAG) system.
        The system has a knowledge base consisting of official documents about government policies, infrastructure, youth programs, and digital transformation for the NPP (National People's Party) in The Gambia. The documents are primarily written in English or French.
        
        Your task is to analyze the user's raw input and output a JSON object with the following fields:
        1. "detected_language": Detect the language of the user's input (e.g., "en", "fr", "wolof", "mandinka", "fular").
        2. "is_casual_conversation": true if the input is just a greeting, chit-chat, or clearly doesn't require searching a document database. false otherwise.
        3. "optimized_search_query": Translate the query to standard English or French, fix any spelling/grammar errors, and expand it with highly relevant keywords that might appear in official documents. If it's a casual conversation, leave this empty.
        4. "hypothetical_document": Write a short (1-2 sentences) hypothetical answer to the user's question in English or French. This will be used for HyDE (Hypothetical Document Embeddings) to find semantically similar documents. Do not write a hypothetical document if it's a casual conversation.
        
        CRITICAL: Your output MUST be valid JSON, with no markdown formatting blocks like ```json around it. Just the raw JSON object.
        """
        
        try:
            response = await self._llm.generate(
                prompt=f"Raw User Input: {raw_query}",
                system_prompt=system_prompt,
                temperature=0.1, # Keep it deterministic
            )
            
            # Clean up the response if the LLM added markdown backticks
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
                
            result = json.loads(cleaned_response.strip())
            
            logger.info("query_transformed", 
                        original=raw_query, 
                        language=result.get("detected_language"), 
                        optimized=result.get("optimized_search_query"))
            
            return result
            
        except Exception as e:
            logger.error("query_transformation_failed", error=str(e), query=raw_query)
            # Fallback gracefully
            return {
                "detected_language": "unknown",
                "is_casual_conversation": False,
                "optimized_search_query": raw_query,
                "hypothetical_document": ""
            }
