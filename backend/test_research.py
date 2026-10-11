import asyncio
import json
from src.services.llm_service import groq_llm_service
from src.services.search_orchestrator import search_orchestrator

async def test_llm():
    print("Testing generate_research_plan...")
    plan = await groq_llm_service.generate_research_plan("How do Waymo and Tesla compare?")
    print(f"Plan: {json.dumps(plan, indent=2)}")

async def test_orchestrator():
    print("\nTesting search_orchestrator stream...")
    count = 0
    async for event in search_orchestrator.stream_search("Tesla vs Waymo"):
        print(f"Event received: {event[:100]}...")
        count += 1
        if "query_step" in event:
            print("  -> Found query_step!")
        if count > 10: break

if __name__ == "__main__":
    asyncio.run(test_llm())
    asyncio.run(test_orchestrator())
