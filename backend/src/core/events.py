"""
Application lifecycle event handlers.
"""

import asyncio
import logging
from fastapi import FastAPI
from src.config.settings import settings
from src.config.logging import setup_logging, logger


def create_start_app_handler(app: FastAPI):
    async def start_app() -> None:
        setup_logging()
        logger.info(f"{settings.BRAND_NAME} AI API starting up...")

        # Warm up Redis connection
        try:
            from src.db.redis import get_redis
            redis = await get_redis()
            await asyncio.wait_for(redis.ping(), timeout=3.0)
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.warning("Redis connection failed at startup (continuing): %s", e)

        logger.info("Startup complete")

    return start_app


def create_stop_app_handler(app: FastAPI):
    async def stop_app() -> None:
        logger.info(f"{settings.BRAND_NAME} AI API shutting down...")

        # Close Redis gracefully
        try:
            from src.db.redis import close_redis
            await close_redis()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.warning("Redis close failed: %s", e)

        logger.info("Shutdown complete")

    return stop_app
