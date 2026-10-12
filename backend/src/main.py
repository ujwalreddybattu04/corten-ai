"""
# Corten AI — FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config.settings import settings
from src.api.v1.router import api_router
from src.core.events import create_start_app_handler, create_stop_app_handler
from src.core.interpolation_limits import InterpolationBodyLimit
from src.core.generation_limits import GenerationLimits

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_start_app_handler(app)()
    try:
        yield
    finally:
        await create_stop_app_handler(app)()

app = FastAPI(
    title=f"{settings.BRAND_NAME} AI API",
    description="AI-Powered Answer Engine — Backend API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Browsers use the frontend proxy; direct clients use the configured origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.add_middleware(InterpolationBodyLimit)
app.add_middleware(GenerationLimits)
app.include_router(api_router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": f"{settings.BRAND_NAME.lower()}-ai"}

@app.get("/ready", tags=["Health"])
async def readiness_check():
    from src.core.readiness import readiness
    result = await readiness()
    return JSONResponse(result, status_code=200 if result["status"] == "ready" else 503, headers={"Cache-Control": "no-store"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
