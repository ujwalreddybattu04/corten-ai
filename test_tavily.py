''' testing script of tavily search api with grounding'''
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / "backend" / ".env")
from tavily import AsyncTavilyClient

async def test_tavily():
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set TAVILY_API_KEY in backend/.env before running this smoke test")
    client = AsyncTavilyClient(api_key=api_key)
    
    print("Testing configured Tavily connection")
    try:
        response = await client.search(
            query="deep learning basics",
            search_depth="advanced"
        )
        print("Tavily Response keys:", response.keys())
        results = response.get("results", [])
        print(f"Found {len(results)} results")
        if results:
            print("Sample result title:", results[0].get("title"))
    except Exception as e:
        print(f"Tavily Test FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_tavily())
