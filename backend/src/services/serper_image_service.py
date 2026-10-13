"""Bounded image retrieval with provider fallback; retain the existing caller API."""
import asyncio
import hashlib
import ipaddress
import json
import logging
import time
from collections import OrderedDict
from urllib.parse import urlsplit

import httpx
from src.config.settings import settings

logger = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class ImageSearchUnavailable(RuntimeError):
    """Configured providers failed, as distinct from an empty successful search."""


def public_image_url(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        return ""
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.scheme != "https" or not host or parts.username or parts.password or parts.port not in (None, 443):
            return ""
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            pass
        return value
    except ValueError:
        return ""


def normalized_images(payload, provider, query, limit):
    if not isinstance(payload, dict):
        raise ValueError("Invalid image response")
    if "images" not in payload and not (provider == "tavily" and "results" in payload):
        raise ValueError("Missing image response fields")
    candidates = payload.get("images", [])
    if not isinstance(candidates, list):
        raise ValueError("Invalid image list")
    linked = {}
    if provider == "tavily":
        pages = payload.get("results", [])
        for page in pages if isinstance(pages, list) else []:
            if not isinstance(page, dict) or not isinstance(page.get("images", []), list):
                continue
            for image in page["images"][:100]:
                image = {"url": image} if isinstance(image, str) else image
                if not isinstance(image, dict):
                    continue
                url = public_image_url(image.get("url"))
                if url:
                    linked.setdefault(url, {**image, "sourceUrl": page.get("url"), "alt": image.get("description") or page.get("title")})
        if not candidates:
            candidates = list(linked.values())
    output, seen = [], set()
    for candidate in candidates:
        candidate = {"url": candidate} if isinstance(candidate, str) else candidate
        if not isinstance(candidate, dict):
            continue
        url = public_image_url(candidate.get("imageUrl") if provider == "serper" else candidate.get("url"))
        if not url or url in seen:
            continue
        metadata = {**linked.get(url, {}), **candidate}
        alt = metadata.get("title") or metadata.get("description") or metadata.get("alt") or query
        source = metadata.get("source") or ""
        output.append({"url": url, "thumbnailUrl": public_image_url(metadata.get("thumbnailUrl")) or url,
            "alt": alt[:240] if isinstance(alt, str) else query[:240],
            "sourceUrl": public_image_url(metadata.get("link") or metadata.get("sourceUrl")),
            "source": source[:160] if isinstance(source, str) else ""})
        seen.add(url)
        if len(output) >= limit:
            break
    return output


class SerperImageService:
    BASE_URL = "https://google.serper.dev/images"
    TAVILY_URL = "https://api.tavily.com/search"

    def __init__(self):
        self._cooldowns = OrderedDict()
        self._cache = OrderedDict()

    async def _request(self, url, headers, body, timeout):
        async def fetch():
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=min(2, timeout))) as client:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    response.raise_for_status()
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_RESPONSE_BYTES:
                            raise ValueError("Image response exceeds limit")
                    return json.loads(content)
        return await asyncio.wait_for(fetch(), timeout=timeout)

    async def search_images(self, query: str, num: int = 9):
        query = query.strip()[:400]
        if not query:
            return []
        limit = min(20, max(1, num))
        configured = {p:k for p,k in {"serper":settings.SERPER_API_KEY,"tavily":settings.TAVILY_API_KEY}.items() if k}
        if not configured:
            return []
        fingerprints = {p:hashlib.sha256(k.encode()).hexdigest() for p,k in configured.items()}
        identity = hashlib.sha256(json.dumps([query,limit,fingerprints],sort_keys=True).encode()).hexdigest()
        cached = self._cache.get(identity)
        if cached and cached[0] > time.monotonic():
            return [dict(image) for image in cached[1]]
        valid_empty = False
        for provider, key in configured.items():
            cooldown_key = (provider,fingerprints[provider])
            if self._cooldowns.get(cooldown_key,0) > time.monotonic():
                continue
            try:
                if provider == "serper":
                    payload = await self._request(self.BASE_URL,{"X-API-KEY":key},{"q":query,"num":limit},2.5)
                else:
                    payload = await self._request(self.TAVILY_URL,{"Authorization":f"Bearer {key}"},
                        {"query":query,"search_depth":"basic","max_results":3,"include_images":True,
                         "include_answer":False,"include_raw_content":False},5.5)
                images = normalized_images(payload,provider,query,limit)
                valid_empty = True
                if not images:
                    continue
                self._cache[identity] = (time.monotonic()+300,[dict(image) for image in images])
                self._cache.move_to_end(identity)
                while len(self._cache) > 64:
                    self._cache.popitem(last=False)
                return images
            except (httpx.HTTPError,ValueError,asyncio.TimeoutError) as failure:
                delay = 20
                if isinstance(failure,httpx.HTTPStatusError):
                    status = failure.response.status_code
                    delay = 300 if status in (401,403,402,432,433) else 60
                    if status == 429:
                        try:
                            delay = min(300,max(1,int(failure.response.headers.get("Retry-After","60"))))
                        except ValueError:
                            pass
                    logger.warning("Image provider %s returned HTTP %s; trying available fallback",provider,status)
                else:
                    logger.warning("Image provider %s failed (%s); trying available fallback",provider,type(failure).__name__)
                self._cooldowns[cooldown_key] = time.monotonic()+delay
                self._cooldowns.move_to_end(cooldown_key)
                while len(self._cooldowns) > 8:
                    self._cooldowns.popitem(last=False)
        if valid_empty:
            return []
        raise ImageSearchUnavailable("Image search is temporarily unavailable. Please try again shortly.")


serper_image_service = SerperImageService()
