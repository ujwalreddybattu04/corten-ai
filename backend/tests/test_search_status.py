import unittest
from unittest.mock import patch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from src.api.v1.search import router, search_orchestrator


class SearchStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_startup_check_never_generates_an_answer(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/search")
        with patch.object(search_orchestrator, "stream_search") as generate:
            async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
                response = await client.get("/api/v1/search/status")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ready"})
            self.assertEqual(response.headers["cache-control"], "no-store")
            generate.assert_not_called()
