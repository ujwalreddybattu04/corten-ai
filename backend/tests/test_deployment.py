"""Deployment configuration and password-hashing regressions; no live credentials."""
import unittest
from pydantic import ValidationError
from src.config.settings import Settings
from src.core.security import hash_password, verify_password


class DeploymentTests(unittest.TestCase):
    def test_render_postgres_urls_use_async_driver(self):
        for scheme in ("postgres://", "postgresql://", "postgresql+asyncpg://"):
            settings = Settings(_env_file=None, DATABASE_URL=scheme + "user:p%25ass@db:5432/app")
            self.assertEqual(settings.DATABASE_URL, "postgresql+asyncpg://user:p%25ass@db:5432/app")

    def test_production_requires_strong_jwt_secret(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY="change-me-in-production")
        settings = Settings(_env_file=None, APP_ENV="production", JWT_SECRET_KEY="x" * 40)
        self.assertEqual(settings.APP_ENV, "production")

    def test_password_hash_round_trip(self):
        hashed = hash_password("deployment-test-password")
        self.assertTrue(verify_password("deployment-test-password", hashed))
        self.assertFalse(verify_password("different-password", hashed))


if __name__ == "__main__":
    unittest.main()
