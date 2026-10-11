import asyncio
import httpx

async def test():
    async with httpx.AsyncClient() as client:
        try:
            print("Sending request to backend...")
            async with client.stream("POST", "http://localhost:8000/api/v1/search/stream", json={"query": "what is ai", "focus_mode": "all"}) as response:
                print("Response status:", response.status_code)
                async for chunk in response.aiter_text():
                    print("CHUNK:", chunk)
            print("Done.")
        except Exception as e:
            print("ERROR:", e)

asyncio.run(test())
