"""
Discover service — news feed, market data, and weather.
Uses Guardian, NewsAPI and attributed RSS headlines, Yahoo Finance for market data,
and wttr.in for weather. Successful news has a bounded last-good cache.
"""

import asyncio
import hashlib
import logging
import time
import re
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree
from collections import defaultdict
from itertools import zip_longest
from urllib.parse import urlparse

import httpx

from src.config.settings import settings
from src.db.redis import cache_get, cache_set

logger = logging.getLogger(__name__)

# ── Cache TTLs ────────────────────────────────────────────────────────────────
NEWS_CACHE_TTL = 900       # 15 min
NEWS_STALE_TTL = 21600    # Last successful feed is usable for at most six hours.
NEWS_POOL_SIZE = 20
_news_memory: dict[str, dict] = {}
_news_pending: dict[str, asyncio.Task] = {}
_news_retry_at: dict[str, float] = {}
_provider_retry_at: dict[tuple[str, str], float] = {}
RSS_FEEDS = {
    "for-you": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "top": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "entertainment": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "sports": "https://feeds.bbci.co.uk/sport/rss.xml",
    "health": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
}
MARKET_CACHE_TTL = 300     # 5 min
WEATHER_CACHE_TTL = 600    # 10 min — weather changes fast, accuracy matters

# ── NewsAPI category mapping (for /top-headlines, page 1) ────────────────────
NEWSAPI_CATEGORY_MAP = {
    "for-you":       "general",
    "top":           "general",
    "technology":    "technology",
    "business":      "business",
    "entertainment": "entertainment",
    "sports":        "sports",
    # The existing UI uses "health" as the Entertainment tab's stored ID.
    "health":        "entertainment",
}

# ── NewsAPI /everything rotating keywords (for pages 2+) ─────────────────────
# Each page picks a different keyword, giving fresh articles each scroll
NEWSAPI_KEYWORDS = {
    "for-you":       ["world news", "breaking news today", "top stories", "global headlines", "daily news", "latest news", "trending stories", "major events"],
    "top":           ["top headlines", "breaking news", "major stories", "world events", "important news", "news today", "global news", "headline news"],
    "technology":    ["artificial intelligence", "tech innovation", "software news", "cybersecurity", "gadgets technology", "AI machine learning", "tech companies", "digital tech"],
    "business":      ["stock market news", "business economy", "corporate finance", "startup funding", "trade economics", "market analysis", "business deals", "financial news"],
    "entertainment": ["arts culture", "art exhibitions", "cultural events", "creative arts", "performing arts", "literature books", "cultural news", "arts news"],
    "sports":        ["sports news", "football soccer", "basketball scores", "sports results", "athletics", "sports championship", "game scores", "sports today"],
    "health":        ["celebrity news", "movies TV", "entertainment news", "film reviews", "music news", "streaming shows", "celebrity gossip", "TV shows"],
}

# ── Guardian API section mapping ──────────────────────────────────────────────
GUARDIAN_SECTION_MAP = {
    "for-you":       "",
    "top":           "",
    "technology":    "technology",
    "business":      "business",
    "entertainment": "culture",
    "sports":        "sport",
    "health":        "film",
}

# ── Curated trending stocks ───────────────────────────────────────────────────
TRENDING_STOCKS = [
    ("Apple Inc.", "AAPL"),
    ("NVIDIA Corp.", "NVDA"),
    ("Microsoft Corp.", "MSFT"),
    ("Tesla Inc.", "TSLA"),
    ("Amazon.com Inc.", "AMZN"),
    ("Alphabet Inc.", "GOOGL"),
    ("Meta Platforms", "META"),
    ("JPMorgan Chase", "JPM"),
]


# ── News Articles ─────────────────────────────────────────────────────────────

async def get_news_articles(category: str = "for-you", page: int = 1, page_size: int = 18) -> dict:
    """Slice shared 20-story pools without skipping stories for smaller page sizes."""
    if category not in RSS_FEEDS or not 1 <= page <= 10 or not 6 <= page_size <= 20:
        raise ValueError("Invalid news category or pagination")
    offset = (page - 1) * page_size
    pool_page, start = divmod(offset, NEWS_POOL_SIZE)
    articles, pools = [], []
    more = False
    slots_remaining = page_size
    while slots_remaining > 0 and pool_page < 10:
        pool = await _get_news_pool(category, pool_page + 1)
        if pool["status"] == "unavailable":
            if not articles:
                return _news_unavailable(page)
            return {**pools[0], "articles": articles, "page": page,
                    "has_more": True, "partial": True}
        pools.append(pool)
        span = min(slots_remaining, NEWS_POOL_SIZE - start)
        articles.extend(pool["articles"][start:start + span])
        slots_remaining -= span
        more = start + span < len(pool["articles"]) or pool["has_more"]
        if slots_remaining == 0 or not pool["has_more"] or not pool["articles"]:
            break
        pool_page += 1
        start = 0
    stale = any(p["status"] == "stale" for p in pools)
    oldest = min(pools, key=lambda p: p["fetched_at_epoch"])
    return {**oldest, "articles": articles, "has_more": more and page < 10, "page": page,
            "status": "stale" if stale else "available" if articles else "empty"}


async def _get_news_pool(category: str, page: int) -> dict:
    # Size-independent keys share quota across personalized and category feeds.
    key = f"discover:news:g4:{category}:{page}"
    task = _news_pending.get(key)
    if task is None:
        task = asyncio.create_task(_refresh_news_pool(key, category, page))
        _news_pending[key] = task
        task.add_done_callback(lambda done: _news_pending.pop(key, None))
    # Cancelling one browser request must not cancel other readers' shared refresh.
    return await asyncio.shield(task)


async def _refresh_news_pool(key: str, category: str, page: int) -> dict:
    now = time.time()
    cached = _news_memory.get(key)
    if not cached:
        try:
            cached = await asyncio.wait_for(cache_get(key), timeout=1.0)
        except Exception:
            cached = None
    if cached and not _valid_news_cache(cached):
        cached = None
    age = now - cached["fetched_at_epoch"] if cached else float("inf")
    if cached and not 0 <= age <= NEWS_STALE_TTL:
        cached = None
    if cached:
        _news_memory[key] = cached
        if age < cached.get("fresh_for", NEWS_CACHE_TTL):
            return cached
    if now < _news_retry_at.get(key, 0):
        return _stale_news(cached) if cached and cached["articles"] else _news_unavailable(page)

    empty_result = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=3.0), follow_redirects=True) as client:
        for fetch_provider in (_fetch_guardian, _fetch_newsapi, _fetch_rss):
            try:
                result = await asyncio.wait_for(fetch_provider(client, category, page, NEWS_POOL_SIZE), timeout=7.0)
            except TimeoutError:
                logger.warning("News source deadline exceeded (category=%s, page=%s)", category, page)
                result = _news_unavailable(page)
            if result["status"] == "unavailable":
                continue
            if result["articles"] or page > 1:
                fetched = time.time()
                result.update(fetched_at_epoch=fetched,
                              fetched_at=datetime.fromtimestamp(fetched, timezone.utc).isoformat())
                _news_memory[key] = result
                _news_retry_at.pop(key, None)
                try:
                    await asyncio.wait_for(cache_set(key, result, ttl=NEWS_STALE_TTL), timeout=1.0)
                except Exception:
                    pass
                return result
            empty_result = result
    _news_retry_at[key] = time.time() + 30
    if cached and cached["articles"]:
        return _stale_news(cached)
    if empty_result is not None:
        fetched = time.time()
        result = {**empty_result, "fetched_at_epoch": fetched, "fresh_for": 30,
                  "fetched_at": datetime.fromtimestamp(fetched, timezone.utc).isoformat()}
        _news_memory[key] = result
        return result
    return _news_unavailable(page)


def _valid_news_cache(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    timestamp = value.get("fetched_at_epoch")
    fresh_for = value.get("fresh_for", NEWS_CACHE_TTL)
    articles = value.get("articles")
    return (isinstance(timestamp, (int, float)) and math.isfinite(timestamp)
            and isinstance(fresh_for, (int, float)) and 0 < fresh_for <= NEWS_CACHE_TTL
            and isinstance(value.get("fetched_at"), str)
            and isinstance(value.get("has_more"), bool)
            and value.get("status") in ("available", "empty")
            and isinstance(articles, list) and len(articles) <= NEWS_POOL_SIZE
            and all(isinstance(a, dict) and isinstance(a.get("title"), str)
                    and _news_url(a.get("url")) and isinstance(a.get("source"), dict)
                    and isinstance(a["source"].get("name"), str) for a in articles))


def _news_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.hostname)
    except ValueError:
        return False


def _stale_news(cached: dict) -> dict:
    return {**cached, "status": "stale",
            "message": "Showing saved stories while news sources reconnect."}


def _provider_identity(name: str, credential: str) -> tuple[str, str]:
    return name, hashlib.sha256(credential.encode()).hexdigest()


def _provider_ready(name: str, credential: str) -> bool:
    return time.time() >= _provider_retry_at.get(_provider_identity(name, credential), 0)


def _provider_failed(name: str, credential: str, response: httpx.Response | None = None) -> None:
    # An invalid credential waits longer; changing it immediately enables the provider.
    delay = 3600 if response is not None and response.status_code in (401, 403) else 30
    if response is not None and response.status_code == 429:
        try:
            delay = max(30, min(3600, float(response.headers.get("Retry-After", "60"))))
        except ValueError:
            delay = 60
    if len(_provider_retry_at) > 20:
        _provider_retry_at.clear()
    _provider_retry_at[_provider_identity(name, credential)] = time.time() + delay


def _news_unavailable(page: int) -> dict:
    return {
        "articles": [], "has_more": False, "page": page,
        "status": "unavailable",
        "message": "News is temporarily unavailable. Please try again.",
    }


async def _fetch_newsapi(client: httpx.AsyncClient, category: str, page: int, page_size: int) -> dict:
    """
    Page 1 → /top-headlines (fresh breaking news for the category).
    Pages 2+ → /everything with rotating keywords (gives fresh articles each scroll,
                bypasses the 100-result cap by using different queries per page).
    """
    if not settings.NEWSAPI_KEY or not _provider_ready("newsapi", settings.NEWSAPI_KEY):
        return _news_unavailable(page)
    try:
        if page == 1 and category != "entertainment":
            # Top headlines for the category — freshest breaking news
            newsapi_category = NEWSAPI_CATEGORY_MAP.get(category, "general")
            resp = await client.get(
                "https://newsapi.org/v2/top-headlines",
                headers={"X-Api-Key": settings.NEWSAPI_KEY},
                params={
                    "category": newsapi_category,
                    "language": "en",
                    "pageSize": min(page_size, 20),
                    "page": 1,
                },
            )
        else:
            # Rotate through category keywords — each page gets different articles
            keywords = NEWSAPI_KEYWORDS.get(category, NEWSAPI_KEYWORDS["for-you"])
            # Arts & Culture has no dedicated headline category in NewsAPI.
            keyword_index = page - 1 if category == "entertainment" else page - 2
            keyword = keywords[keyword_index % len(keywords)]
            resp = await client.get(
                "https://newsapi.org/v2/everything",
                headers={"X-Api-Key": settings.NEWSAPI_KEY},
                params={
                    "q": keyword,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": min(page_size, 20),
                    "page": 1,   # always page 1 of each keyword = fresh unique articles
                },
            )

        if resp.status_code != 200:
            _provider_failed("newsapi", settings.NEWSAPI_KEY, resp)
            logger.warning("NewsAPI HTTP %s (category=%s, page=%s)", resp.status_code, category, page)
            return _news_unavailable(page)
        data = resp.json()
        if data.get("status") != "ok":
            _provider_failed("newsapi", settings.NEWSAPI_KEY)
            return _news_unavailable(page)
        articles = _transform_newsapi_articles(data.get("articles", []))
        # Keep going as long as we have keywords to rotate through
        keywords_count = len(NEWSAPI_KEYWORDS.get(category, NEWSAPI_KEYWORDS["for-you"]))
        last_page = keywords_count if category == "entertainment" else keywords_count + 1
        has_more = page < last_page and len(articles) > 0
        return {
            "articles": articles, "has_more": has_more, "page": page,
            "status": "available" if articles else "empty", "provider": "newsapi",
        }

    except Exception as exc:
        _provider_failed("newsapi", settings.NEWSAPI_KEY)
        # HTTP exception strings can contain provider keys in the request URL.
        logger.warning("NewsAPI failed (category=%s, page=%s): %s", category, page, type(exc).__name__)
        return _news_unavailable(page)


async def _fetch_guardian(client: httpx.AsyncClient, category: str, page: int, page_size: int) -> dict:
    """Fetch from The Guardian API. Thousands of articles per section, true infinite scroll."""
    if not settings.GUARDIAN_API_KEY or not _provider_ready("guardian", settings.GUARDIAN_API_KEY):
        return _news_unavailable(page)

    section = GUARDIAN_SECTION_MAP.get(category, "")
    params: dict = {
        "api-key": settings.GUARDIAN_API_KEY,
        "page": page,
        "page-size": min(page_size, 20),
        "show-fields": "thumbnail,trailText",
        "order-by": "newest",
        "show-tags": "contributor",
    }
    if section:
        params["section"] = section

    try:
        resp = await client.get("https://content.guardianapis.com/search", params=params)
        logger.info(f"Guardian HTTP {resp.status_code} | category={category} page={page}")
        if resp.status_code != 200:
            _provider_failed("guardian", settings.GUARDIAN_API_KEY, resp)
            return _news_unavailable(page)

        data = resp.json().get("response", {})
        if data.get("status") != "ok":
            _provider_failed("guardian", settings.GUARDIAN_API_KEY)
            return _news_unavailable(page)
        current_page = data.get("currentPage", 1)
        total_pages = data.get("pages", 1)
        articles = _transform_guardian_articles(data.get("results", []))
        logger.info(f"Guardian OK | category={category} page={current_page}/{total_pages} articles={len(articles)}")
        return {
            "articles": articles,
            "has_more": current_page < total_pages,
            "total": data.get("total", 0),
            "page": page,
            "status": "available" if articles else "empty",
            "provider": "guardian",
        }
    except Exception as exc:
        _provider_failed("guardian", settings.GUARDIAN_API_KEY)
        logger.warning("Guardian failed (category=%s, page=%s): %s", category, page, type(exc).__name__)
        return _news_unavailable(page)


async def _fetch_rss(client: httpx.AsyncClient, category: str, page: int, page_size: int) -> dict:
    """Read attributed public headlines without depending on API credentials."""
    feed_url = RSS_FEEDS[category]
    if not _provider_ready("rss", feed_url):
        return _news_unavailable(page)
    try:
        async with client.stream("GET", feed_url) as resp:
            if resp.status_code != 200:
                _provider_failed("rss", feed_url, resp)
                return _news_unavailable(page)
            content = bytearray()
            async for chunk in resp.aiter_bytes():
                content.extend(chunk)
                if len(content) > 1_000_000:
                    raise ValueError("RSS exceeds size limit")
        # Strict UTF-8 plus DTD/entity rejection prevents XML expansion attacks.
        xml = content.decode("utf-8-sig")
        if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
            raise ValueError("RSS declarations are not supported")
        root = ElementTree.fromstring(xml)
        articles, seen = [], set()
        for item in root.findall("./channel/item")[:200]:
            title = (item.findtext("title") or "").strip()
            url = (item.findtext("link") or "").strip()
            parsed = urlparse(url)
            if not title or parsed.scheme not in ("https", "http") or not parsed.hostname or url in seen:
                continue
            seen.add(url)
            try:
                published = parsedate_to_datetime(item.findtext("pubDate") or "")
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                published_at = published.astimezone(timezone.utc).isoformat()
            except (ValueError, TypeError, OverflowError):
                published_at = ""
            thumbnail = item.find("{http://search.yahoo.com/mrss/}thumbnail")
            image = thumbnail.get("url", "") if thumbnail is not None else ""
            if urlparse(image).scheme not in ("https", "http"):
                image = ""
            articles.append({
                "id": hashlib.md5(url.encode()).hexdigest(), "title": title,
                "description": unescape(re.sub(r"<[^>]*>", "", item.findtext("description") or "")),
                "url": url, "image": image, "publishedAt": published_at,
                "source": {"name": "BBC News" if category != "sports" else "BBC Sport",
                           "domain": parsed.netloc.removeprefix("www."),
                           "favicon": "https://www.google.com/s2/favicons?domain=bbc.com&sz=32"},
                "isHero": False,
            })
        start = (page - 1) * page_size
        selected = articles[start:start + page_size]
        return {"articles": selected, "has_more": start + page_size < len(articles),
                "page": page, "status": "available" if selected else "empty", "provider": "bbc-rss"}
    except Exception as exc:
        _provider_failed("rss", feed_url)
        logger.warning("RSS failed (category=%s, page=%s): %s", category, page, type(exc).__name__)
        return _news_unavailable(page)


def _transform_newsapi_articles(raw: list) -> list[dict]:
    """Normalise NewsAPI article shape into our internal format."""
    out = []
    for art in raw:
        title = art.get("title", "") or ""
        if not title or title == "[Removed]":
            continue
        url = art.get("url", "") or ""
        if not _news_url(url):
            continue
        domain = ""
        try:
            domain = urlparse(url).netloc.replace("www.", "")
        except Exception:
            pass
        source_name = (art.get("source") or {}).get("name") or domain
        out.append({
            "id": hashlib.md5(url.encode()).hexdigest(),
            "title": title,
            "description": art.get("description") or "",
            "url": url,
            "image": art.get("urlToImage") or "",
            "publishedAt": art.get("publishedAt") or "",
            "source": {
                "name": source_name,
                "domain": domain,
                "favicon": f"https://www.google.com/s2/favicons?domain={domain}&sz=32" if domain else "",
            },
            "isHero": False,
        })
    return out


def _transform_guardian_articles(raw: list) -> list[dict]:
    """Normalise Guardian API article shape into our internal format."""
    out = []
    for art in raw:
        title = art.get("webTitle", "") or ""
        if not title:
            continue
        url = art.get("webUrl", "") or ""
        if not _news_url(url):
            continue
        domain = ""
        try:
            domain = urlparse(url).netloc.replace("www.", "")
        except Exception:
            pass
        fields = art.get("fields", {})
        out.append({
            "id": hashlib.md5(url.encode()).hexdigest(),
            "title": title,
            "description": fields.get("trailText", "") or "",
            "url": url,
            "image": fields.get("thumbnail", "") or "",
            "publishedAt": art.get("webPublicationDate", "") or "",
            "source": {
                "name": "The Guardian",
                "domain": domain,
                "favicon": f"https://www.google.com/s2/favicons?domain={domain}&sz=32" if domain else "",
            },
            "isHero": False,
        })
    return out


# ── Market Data ───────────────────────────────────────────────────────────────

async def get_market_data() -> dict:
    """Fetch S&P 500, NASDAQ, VIX, and Bitcoin from Yahoo Finance (no key needed)."""
    cache_key = "discover:market"

    cached = await cache_get(cache_key)
    if cached:
        return cached

    indices = {
        "S&P 500": "^GSPC",
        "NASDAQ": "^IXIC",
        "VIX": "^VIX",
        "Bitcoin": "BTC-USD",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        results = await asyncio.gather(
            *[_fetch_yahoo(client, name, sym) for name, sym in indices.items()],
            return_exceptions=True,
        )

    market = {}
    for r in results:
        if isinstance(r, dict):
            market.update(r)

    await cache_set(cache_key, market, ttl=MARKET_CACHE_TTL)
    return market


async def _fetch_yahoo(client: httpx.AsyncClient, name: str, symbol: str) -> dict:
    """Fetch a single symbol's current price + sparkline from Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()

        result = data["chart"]["result"][0]
        meta = result["meta"]

        price = meta.get("regularMarketPrice", 0)
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose") or price
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0.0

        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        sparkline = [c for c in closes if c is not None][-12:]

        return {
            name: {
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "symbol": symbol,
                "sparkline": sparkline,
                "is_crypto": symbol == "BTC-USD",
            }
        }
    except Exception as exc:
        logger.warning(f"Yahoo Finance failed for {symbol}: {exc}")
        return {}


# ── Trending Companies ────────────────────────────────────────────────────────

async def get_trending_stocks() -> list[dict]:
    """Fetch live prices for a curated list of trending stocks."""
    cache_key = "discover:trending_stocks"

    cached = await cache_get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=10.0) as client:
        results = await asyncio.gather(
            *[_fetch_yahoo(client, name, sym) for name, sym in TRENDING_STOCKS],
            return_exceptions=True,
        )

    stocks = []
    for (name, sym), r in zip(TRENDING_STOCKS, results):
        if isinstance(r, dict) and name in r:
            d = r[name]
            stocks.append({
                "name": name,
                "symbol": sym,
                "price": d["price"],
                "change": d["change"],
                "change_pct": d["change_pct"],
                "favicon": f"https://www.google.com/s2/favicons?domain={_ticker_domain(sym)}&sz=32",
            })

    top5 = stocks[:5]
    await cache_set(cache_key, top5, ttl=MARKET_CACHE_TTL)
    return top5


def _ticker_domain(ticker: str) -> str:
    domains = {
        "AAPL": "apple.com", "NVDA": "nvidia.com", "MSFT": "microsoft.com",
        "TSLA": "tesla.com", "AMZN": "amazon.com", "GOOGL": "google.com",
        "META": "meta.com", "JPM": "jpmorganchase.com",
    }
    return domains.get(ticker, "finance.yahoo.com")


# ── Weather ───────────────────────────────────────────────────────────────────

OWM_ICON_MAP = {
    "01": "sunny", "02": "partly-cloudy", "03": "cloudy", "04": "cloudy",
    "09": "rain", "10": "rain", "11": "thunderstorm", "13": "snow", "50": "fog",
}


async def get_weather(city: str = "") -> dict:
    """Fetch weather using OpenWeatherMap — auto-detects user location via their IP."""
    location = city.strip()
    # Cache key: use coords or IP as identifier so each user gets their own weather
    cache_key = f"discover:weather3:{location or 'unknown'}"

    cached = await cache_get(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                lat, lon = await _resolve_coords(client, location)
                coord_params: dict = {"lat": lat, "lon": lon}
            except ValueError as ve:
                # City name path — OWM can geocode directly by name
                city_name = str(ve).removeprefix("city_name:")
                coord_params = {"q": city_name} if city_name else {}
                if not coord_params:
                    raise

            # Fetch current weather + 5-day forecast in parallel
            current_task = client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={**coord_params, "appid": settings.OPENWEATHER_API_KEY, "units": "metric"},
            )
            forecast_task = client.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={**coord_params, "appid": settings.OPENWEATHER_API_KEY, "units": "metric", "cnt": 40},
            )
            cur_resp, fore_resp = await asyncio.gather(current_task, forecast_task)
            cur_resp.raise_for_status()
            fore_resp.raise_for_status()

            cur = cur_resp.json()
            fore = fore_resp.json()

        # Current conditions
        temp_c = round(cur["main"]["temp"])
        feels_c = round(cur["main"]["feels_like"])
        humidity = str(cur["main"]["humidity"])
        desc = cur["weather"][0]["description"].title()
        icon_code = cur["weather"][0]["icon"][:2]
        icon_key = OWM_ICON_MAP.get(icon_code, "partly-cloudy")

        city_name = cur.get("name", "")
        country = cur.get("sys", {}).get("country", "")
        city_label = f"{city_name}, {country}" if city_name and country else city_name or "Your Location"

        # 5-day forecast — aggregate ALL 3-hour entries per day for true min/max
        daily: dict = defaultdict(lambda: {"temps": [], "icons": []})
        for item in fore.get("list", []):
            date = item["dt_txt"][:10]
            daily[date]["temps"].append(item["main"]["temp_max"])
            daily[date]["temps"].append(item["main"]["temp_min"])
            # Prefer daytime icon (12:00 or nearest midday entry)
            hour = int(item["dt_txt"][11:13])
            daily[date]["icons"].append((abs(hour - 13), item["weather"][0]["icon"][:2]))

        forecast = []
        today_str = cur_resp.headers.get("Date", "")  # server date
        for date in sorted(daily.keys()):
            d = daily[date]
            if not d["temps"]:
                continue
            # Pick icon closest to midday for representative weather
            best_icon = min(d["icons"], key=lambda x: x[0])[1]
            forecast.append({
                "date": date,
                "max_c": round(max(d["temps"])),
                "min_c": round(min(d["temps"])),
                "icon": OWM_ICON_MAP.get(best_icon, "partly-cloudy"),
            })
            if len(forecast) == 5:
                break

        # Today's H/L from current weather API (more accurate than forecast for today)
        today_high = round(cur["main"].get("temp_max", temp_c))
        today_low = round(cur["main"].get("temp_min", temp_c))

        weather = {
            "temp_c": temp_c,
            "feels_like_c": feels_c,
            "humidity": humidity,
            "description": desc,
            "city": city_label,
            "icon": icon_key,
            "high_c": today_high,
            "low_c": today_low,
            "forecast": forecast,
        }

        if weather.get("temp_c") is not None:
            await cache_set(cache_key, weather, ttl=WEATHER_CACHE_TTL)
        return weather

    except Exception as exc:
        logger.warning(f"OpenWeatherMap failed for location={location!r}: {exc}")
        return {}


async def _resolve_coords(client: httpx.AsyncClient, location: str) -> tuple[float, float]:
    """Return (lat, lon) for a user.

    Priority:
    1. 'lat,lon'  — precise GPS coords from browser (most accurate)
    2. 'ip:x.x.x.x' — geolocate the user's actual client IP
    3. city name  — forward geocode via OWM (handled by caller)
    4. empty      — geolocate server IP as last resort
    """
    if location and location.startswith("ip:"):
        client_ip = location[3:].strip()
        # Geolocate the actual user's IP, not the server's IP
        url = f"http://ip-api.com/json/{client_ip}" if client_ip and client_ip not in ("127.0.0.1", "::1", "") else "http://ip-api.com/json/"
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "success":
            raise ValueError(f"ip-api.com failed for IP {client_ip}: {data.get('message')}")
        return float(data["lat"]), float(data["lon"])

    if location and "," in location and not any(c.isalpha() for c in location):
        # Pure 'lat,lon' numeric string from browser GPS
        parts = location.split(",", 1)
        return float(parts[0].strip()), float(parts[1].strip())

    # City name — let caller use OWM geocoding (pass through as city param)
    raise ValueError(f"city_name:{location}")


