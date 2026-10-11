import logging
from typing import List, Dict, Any, Optional
from tavily import AsyncTavilyClient

from src.config.settings import settings

logger = logging.getLogger(__name__)

class TavilySearchService:
    def __init__(self):
        self.api_key = settings.TAVILY_API_KEY
        if not self.api_key:
            logger.warning("TAVILY_API_KEY is not set. Web search will fail.")
            self.client = None
        else:
            self.client = AsyncTavilyClient(api_key=self.api_key)

    async def search(self, query: str, max_results: int = 12) -> Dict[str, Any]:
        """
        Perform a web search using the Tavily API.
        Returns a list of dictionaries with 'results' (text) and 'images'.
        """
        if not self.client:
            logger.error("Attempted to search without Tavily API key.")
            return []

        try:
            logger.info(f"Searching Tavily for: {query}")
            response = await self.client.search(
                query=query,
                max_results=max_results,
                search_depth="basic", # Switched back to basic for zero-latency feel
                include_answer=False,
                include_images=False, # Disabled: Separate API will be used for images
                include_raw_content=False,
            )
            
            # Robustness check: Ensure response is a dictionary
            if not isinstance(response, dict):
                logger.error(f"Unexpected Tavily response type: {type(response)}")
                return {"results": [], "images": []}
            
            results = []
            for item in response.get("results", []):
                domain = item.get("url", "").split("/")[2] if "://" in item.get("url", "") else ""
                if domain.startswith("www."):
                    domain = domain[4:]
                    
                results.append({
                    "title": item.get("title", "Unknown Title"),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                    "domain": domain
                })
                
            return {
                "results": results,
                "images": response.get("images", [])
            }
        except Exception as e:
            logger.exception(f"Tavily search failed: {e}")
            error_msg = str(e).lower()
            if "usage limit" in error_msg or "429" in error_msg or "exceeds your plan" in error_msg:
                # Re-raise so orchestrator can inform the user
                raise Exception("Tavily API usage limit reached. Please check your search provider plan.") from e
            return {"results": [], "images": []}

    async def extract(self, url: str) -> str:
        """
        Extract the full text content from a URL using Tavily Extract API.
        Returns the raw text content of the page.
        """
        if not self.client:
            logger.error("Attempted to extract without Tavily API key.")
            return ""

        try:
            logger.info(f"Extracting content from: {url}")
            response = await self.client.extract(urls=[url])

            if not response or not isinstance(response, dict):
                return ""

            results = response.get("results", [])
            if results and len(results) > 0:
                return results[0].get("raw_content", "") or results[0].get("text", "")
            return ""
        except Exception as e:
            logger.warning(f"Tavily extract failed for {url}: {e}")
            return ""

tavily_search_service = TavilySearchService()
