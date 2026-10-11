import unittest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient
from src.main import app


class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_requires_both_database_and_cache(self):
        for database, cache, status in ((True, True, 200), (False, True, 503), (True, False, 503)):
            with self.subTest(database=database, cache=cache), patch("src.core.readiness.database_ready", AsyncMock(side_effect=None if database else RuntimeError("private database URL"))), patch("src.core.readiness.cache_ready", AsyncMock(side_effect=None if cache else RuntimeError("private cache credentials"))):
                async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
                    result = await client.get("/ready")
                    self.assertEqual(result.status_code, status)
                    self.assertEqual(result.json()["checks"], {"database": database, "cache": cache})
                    self.assertNotIn("private", result.text)
                    self.assertEqual(result.headers["cache-control"], "no-store")
                    self.assertEqual((await client.get("/health")).status_code, 200)
