"""Wait for a newly provisioned database before running migrations."""
import asyncio
from sqlalchemy import text
from src.db.session import engine


async def wait_for_database(timeout: float = 120) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while True:
            try:
                async def ping():
                    async with engine.connect() as connection:
                        await connection.execute(text("SELECT 1"))
                await asyncio.wait_for(ping(), timeout=5)
                print("Database connection ready", flush=True)
                return
            except Exception as error:
                if asyncio.get_running_loop().time() >= deadline:
                    raise RuntimeError("Database did not become ready before startup timeout") from None
                print(f"Waiting for database provisioning ({type(error).__name__})", flush=True)
                await asyncio.sleep(3)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(wait_for_database())
