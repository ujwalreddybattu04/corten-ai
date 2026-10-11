import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.services.query_router import query_router
from src.services.web_search_service import tavily_search_service
from src.services.llm_service import groq_llm_service

async def test_all():
    query = "what is stranger things ??"
    
    print("\n--- Testing Query Router ---")
    try:
        route = await query_router.route_query(query)
        print(f"Route Type: {type(route)}")
        print(f"Route Value: {route}")
        # Test .get()
        intent = route.get("intent")
        print(f"Intent: {intent}")
    except Exception as e:
        print(f"Router Error: {e}")

    print("\n--- Testing Search Service ---")
    try:
        search_data = await tavily_search_service.search(query)
        print(f"Search Data Type: {type(search_data)}")
        # print(f"Search Data: {search_data}")
        # Test .get()
        results = search_data.get("results")
        print(f"Results Count: {len(results) if results else 'None'}")
    except Exception as e:
        print(f"Search Error: {e}")

    print("\n--- Testing Research Plan ---")
    try:
        plan = await groq_llm_service.generate_research_plan(query)
        print(f"Plan Type: {type(plan)}")
        intent = plan.get("intent")
        print(f"Plan Intent: {intent}")
    except Exception as e:
        print(f"Plan Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_all())
