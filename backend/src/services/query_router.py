import json
import logging
from typing import Dict, Any, Optional

from src.services.llm_service import groq_llm_service
from src.config.settings import settings
from src.config.prompts import ROUTER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class QueryRouter:
    """
    The 'Brain' of Corten AI. 
    Uses LLM-based intent classification to route queries with zero hardcoding.
    """
    
    async def route_query(self, query: str) -> Dict[str, Any]:
        """
        Classifies the intent of the user query.
        Returns a dictionary with intent and reasoning.
        """
        system_prompt = ROUTER_SYSTEM_PROMPT.format(
            brand_name=settings.BRAND_NAME,
            company_name=settings.COMPANY_NAME
        )

        try:
            # Use the very fast 8b model for low-latency routing
            response = await groq_llm_service.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                model=settings.ROUTER_MODEL,
                temperature=0.0,
                max_tokens=50,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            if not isinstance(result, dict):
                logger.warning(f"Router LLM returned non-object JSON: {result}. Wrapping in dict.")
                result = {"intent": str(result), "reasoning": "LLM returned single string"}
                
            logger.info(f"Query Routing: '{query}' -> {result.get('intent')} ({result.get('reasoning')})")
            return result
        except Exception as e:
            logger.error(f"Routing failed for query '{query}': {e}")
            # Robust Fallback: Default to SEARCH to ensure user gets an answer
            return {"intent": "SEARCH", "reasoning": "Fallback due to routing error"}

query_router = QueryRouter()
