"""Release jobs serialize migrations and fail closed before traffic changes."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from src.db.migrate import migrate


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def run_job(self, code=0):
        connection = AsyncMock()
        connection.scalar.return_value = True
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=connection)
        context.__aexit__ = AsyncMock(return_value=False)
        engine = MagicMock()
        engine.connect.return_value = context
        engine.dispose = AsyncMock()
        process = MagicMock()
        process.wait = AsyncMock(return_value=code)
        with patch("src.db.migrate.engine", engine), patch("src.db.migrate.wait_for_database", new=AsyncMock()), patch("src.db.migrate.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as launch:
            if code:
                with self.assertRaisesRegex(RuntimeError, "must not receive traffic"): await migrate()
            else:
                await migrate()
            launch.assert_awaited_once()
            self.assertEqual(launch.await_args.args[-3:], ("alembic", "upgrade", "head"))
        self.assertIn("pg_try_advisory_lock", str(connection.scalar.await_args.args[0]))
        self.assertIn("pg_advisory_unlock", str(connection.execute.await_args.args[0]))
        engine.dispose.assert_awaited_once()

    async def test_success_releases_advisory_lock(self):
        await self.run_job()

    async def test_failure_releases_lock_and_blocks_release(self):
        await self.run_job(code=1)
