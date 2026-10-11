import asyncio
import os
import sys

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from src.config.settings import settings
from src.services.llm_service import groq_llm_service
from src.services.web_search_service import tavily_search_service

async def test_keys():
    print("--- Testing API Keys ---")
    print(f"Groq API Key set: {bool(settings.GROQ_API_KEY)}")
    print(f"Tavily API Key set: {bool(settings.TAVILY_API_KEY)}")
    
    if groq_llm_service.client:
        try:
            print("Testing Groq...")
            res = await groq_llm_service.client.chat.completions.create(
                messages=[{"role": "user", "content": "hi"}],
                model=settings.DEFAULT_MODEL,
                max_tokens=5
            )
            print("Groq SUCCESS")
        except Exception as e:
            print(f"Groq FAILED: {e}")
    else:
        print("Groq client not initialized")

    if tavily_search_service.client:
        try:
            print("Testing Tavily...")
            res = await tavily_search_service.search("hello", max_results=1)
            print(f"Tavily SUCCESS: Found {len(res.get('results', []))} results")
        except Exception as e:
            print(f"Tavily FAILED: {e}")
    else:
        print("Tavily client not initialized")

if __name__ == "__main__":
    asyncio.run(test_keys())
