"""
Discover endpoints — trending news, market data, and weather.
"""

import asyncio
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.services.discover_service import (
    get_news_articles,
    get_market_data,
    get_trending_stocks,
    get_weather,
)
from src.services.search_orchestrator import search_orchestrator

router = APIRouter()


class ArticleSummaryRequest(BaseModel):
    title: str
    url: str
    description: str = ""
    followup: str = ""
    previous_summary: str = ""


@router.post("/article/summarize")
async def summarize_article(req: ArticleSummaryRequest):
    """Stream an AI-generated summary of an article by extracting its content + web search."""
    return StreamingResponse(
        search_orchestrator.stream_article_summary(
            title=req.title,
            url=req.url,
            description=req.description,
            followup=req.followup,
            previous_summary=req.previous_summary,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP from request headers (handles proxies/load balancers)."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else ""


@router.get("")
async def get_discover_feed(
    category: str = Query("for-you", description="News category"),
    page: int = Query(1, ge=1, le=10),
    page_size: int = Query(18, ge=6, le=20),
):
    """Get trending news articles for the discover feed. Supports pagination for infinite scroll."""
    result = await get_news_articles(category=category, page=page, page_size=page_size)
    return {**result, "category": category}


@router.get("/sidebar")
async def get_sidebar_data(
    request: Request,
    lat: float = Query(None, description="Latitude from browser geolocation"),
    lon: float = Query(None, description="Longitude from browser geolocation"),
    city: str = Query("", description="City fallback"),
):
    """Fetch all right-sidebar data: market + stocks + weather."""
    if lat is not None and lon is not None:
        # Precise GPS coords from browser — most accurate
        location = f"{lat},{lon}"
    elif city:
        location = city
    else:
        # No coords — pass client IP so backend geolocates the actual user, not the server
        location = f"ip:{_get_client_ip(request)}"

    market_task = get_market_data()
    stocks_task = get_trending_stocks()
    weather_task = get_weather(city=location)

    market, stocks, weather = await asyncio.gather(market_task, stocks_task, weather_task)

    return {"market": market, "trending_stocks": stocks, "weather": weather}


@router.get("/market")
async def get_market():
    """Get S&P 500, NASDAQ, VIX, and Bitcoin market data."""
    return await get_market_data()


@router.get("/weather")
async def get_weather_data(
    request: Request,
    city: str = Query("", description="City name, 'lat,lon', or empty for auto-detect"),
):
    """Get weather for a city (or auto-detect from client IP)."""
    location = city if city else f"ip:{_get_client_ip(request)}"
    return await get_weather(city=location)
