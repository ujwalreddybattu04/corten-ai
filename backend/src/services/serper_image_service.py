import httpx
import logging
from typing import List, Dict, Any

from src.config.settings import settings

logger = logging.getLogger(__name__)


class SerperImageService:
    BASE_URL = "https://google.serper.dev/images"

    async def search_images(self, query: str, num: int = 9) -> List[Dict[str, Any]]:
        """
        Fetch query-relevant images from Serper.dev (Google Images).
        Fires concurrently with Tavily — zero latency impact on the answer stream.
        """
        if not settings.SERPER_API_KEY:
            logger.debug("SERPER_API_KEY not set — image search skipped.")
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.BASE_URL,
                    headers={
                        "X-API-KEY": settings.SERPER_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={"q": query, "num": num},
                    timeout=6.0,
                )
                response.raise_for_status()
                data = response.json()

                images = []
                for item in data.get("images", []):
                    image_url = item.get("imageUrl", "")
                    if not image_url:
                        continue
                    images.append({
                        "url": image_url,
                        "thumbnailUrl": item.get("thumbnailUrl", image_url),
                        "alt": item.get("title", ""),
                        "sourceUrl": item.get("link", ""),
                        "source": item.get("source", ""),
                    })

                logger.info(f"Serper returned {len(images)} images for: {query}")
                return images

        except httpx.HTTPStatusError as e:
            logger.error(f"Serper API HTTP error {e.response.status_code}: {e}")
            return []
        except Exception as e:
            logger.error(f"Serper image search failed: {e}")
            return []


serper_image_service = SerperImageService()
