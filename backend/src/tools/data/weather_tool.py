"""
Weather Tool — real-time weather data for search queries.

When users ask "weather in Tokyo" or "temperature in New York",
this tool fetches live data from OpenWeatherMap instead of
relying on web search results (which may be stale).

Returns structured weather data that the LLM can format beautifully.
"""

import httpx
import logging
import re
from typing import Dict, Any, Optional

from src.tools.base_tool import BaseTool, ToolCategory, ToolContext, ToolResult, ToolStatus
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Patterns that indicate a weather query
_WEATHER_PATTERNS = [
    re.compile(r'\bweather\b', re.IGNORECASE),
    re.compile(r'\btemperature\b.*\b(in|at|for)\b', re.IGNORECASE),
    re.compile(r'\bhow\s+(hot|cold|warm)\b.*\b(in|is)\b', re.IGNORECASE),
    re.compile(r'\bforecast\b', re.IGNORECASE),
    re.compile(r'\brain(ing)?\b.*\b(in|today)\b', re.IGNORECASE),
    re.compile(r'\bsnow(ing)?\b.*\b(in|today)\b', re.IGNORECASE),
    re.compile(r'\bhumidity\b.*\bin\b', re.IGNORECASE),
    re.compile(r'\bwind\s*(speed)?\b.*\bin\b', re.IGNORECASE),
]

# Common city name extraction
_LOCATION_PATTERN = re.compile(
    r'(?:weather|temperature|forecast|rain|snow|humidity|wind)\s+'
    r'(?:in|at|for|of)\s+(.+?)(?:\?|$|today|tomorrow|this week)',
    re.IGNORECASE,
)


class WeatherTool(BaseTool):
    name = "weather"
    description = "Get real-time weather data including temperature, conditions, humidity, and forecast for any city worldwide"
    category = ToolCategory.DATA
    version = "1.0.0"

    timeout_seconds = 5.0
    max_retries = 1
    retry_delay_seconds = 0.3
    is_concurrent_safe = True
    priority = 88  # High — weather queries should use this, not web search

    def can_handle(self, context: ToolContext) -> bool:
        """Detect weather-related queries."""
        q = context.query.lower()
        return any(p.search(q) for p in _WEATHER_PATTERNS)

    async def execute(self, context: ToolContext) -> ToolResult:
        api_key = settings.OPENWEATHER_API_KEY
        if not api_key:
            return ToolResult(
                success=False,
                error="OpenWeatherMap API key not configured",
                tool_name=self.name,
            )

        # Extract city name from query
        location = self._extract_location(context.query)
        if not location:
            return ToolResult(
                success=False,
                error="Could not determine location from query",
                tool_name=self.name,
            )

        try:
            async with httpx.AsyncClient() as client:
                # Current weather
                current_resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={
                        "q": location,
                        "appid": api_key,
                        "units": "metric",
                    },
                    timeout=4.0,
                )
                current_resp.raise_for_status()
                current = current_resp.json()

                # 5-day forecast
                forecast_resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/forecast",
                    params={
                        "q": location,
                        "appid": api_key,
                        "units": "metric",
                        "cnt": 8,  # Next 24 hours (3-hour intervals)
                    },
                    timeout=4.0,
                )
                forecast_resp.raise_for_status()
                forecast = forecast_resp.json()

            # Build structured result
            weather_data = self._format_weather(current, forecast, location)

            return ToolResult(
                success=True,
                data=weather_data,
                sources=[{
                    "url": f"https://openweathermap.org/city/{current.get('id', '')}",
                    "title": f"Weather in {weather_data['city']}, {weather_data['country']}",
                    "domain": "openweathermap.org",
                    "favicon": "https://www.google.com/s2/favicons?domain=openweathermap.org&sz=128",
                    "snippet": weather_data["formatted_summary"],
                    "citationIndex": 1,
                }],
                tool_name=self.name,
                cost=0.0,  # OpenWeatherMap free tier
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ToolResult(
                    success=False,
                    error=f"City '{location}' not found. Please check the spelling.",
                    tool_name=self.name,
                )
            raise
        except Exception as e:
            logger.warning(f"[WeatherTool] Failed for '{location}': {e}")
            raise

    async def health_check(self) -> ToolStatus:
        if not settings.OPENWEATHER_API_KEY:
            return ToolStatus.DOWN
        return ToolStatus.HEALTHY

    def _extract_location(self, query: str) -> Optional[str]:
        """Extract city/location name from the query."""
        match = _LOCATION_PATTERN.search(query)
        if match:
            location = match.group(1).strip().rstrip("?.!, ")
            return location

        # Fallback: try to find a capitalized word after weather-related terms
        q = query.strip()
        # Remove question marks etc
        q = re.sub(r'[?!.,]', '', q)
        words = q.split()

        # Find weather keyword and take everything after preposition
        for i, word in enumerate(words):
            if word.lower() in ("in", "at", "for", "of") and i + 1 < len(words):
                location = " ".join(words[i + 1:])
                return location.strip()

        return None

    def _format_weather(self, current: dict, forecast: dict, location: str) -> dict:
        """Format raw OpenWeatherMap data into structured result."""
        main = current.get("main", {})
        weather = current.get("weather", [{}])[0]
        wind = current.get("wind", {})
        sys = current.get("sys", {})

        temp = round(main.get("temp", 0))
        feels_like = round(main.get("feels_like", 0))
        temp_min = round(main.get("temp_min", 0))
        temp_max = round(main.get("temp_max", 0))
        humidity = main.get("humidity", 0)
        description = weather.get("description", "").capitalize()
        icon = weather.get("icon", "01d")
        wind_speed = round(wind.get("speed", 0) * 3.6, 1)  # m/s to km/h
        city = current.get("name", location)
        country = sys.get("country", "")

        # Format forecast
        forecast_items = []
        for item in forecast.get("list", [])[:6]:
            f_main = item.get("main", {})
            f_weather = item.get("weather", [{}])[0]
            forecast_items.append({
                "time": item.get("dt_txt", ""),
                "temp": round(f_main.get("temp", 0)),
                "description": f_weather.get("description", ""),
                "icon": f_weather.get("icon", "01d"),
            })

        summary = (
            f"{city}, {country}: {temp}°C ({description}), "
            f"feels like {feels_like}°C, H: {temp_max}°C / L: {temp_min}°C, "
            f"humidity {humidity}%, wind {wind_speed} km/h"
        )

        return {
            "type": "weather",
            "city": city,
            "country": country,
            "temperature_c": temp,
            "temperature_f": round(temp * 9 / 5 + 32),
            "feels_like_c": feels_like,
            "temp_min_c": temp_min,
            "temp_max_c": temp_max,
            "humidity": humidity,
            "description": description,
            "icon": icon,
            "icon_url": f"https://openweathermap.org/img/wn/{icon}@2x.png",
            "wind_speed_kmh": wind_speed,
            "wind_direction": wind.get("deg", 0),
            "visibility_km": round(current.get("visibility", 10000) / 1000, 1),
            "pressure_hpa": main.get("pressure", 0),
            "forecast": forecast_items,
            "formatted_summary": summary,
            "formatted": (
                f"## Weather in {city}, {country}\n\n"
                f"**{temp}°C** ({round(temp * 9/5 + 32)}°F) — {description}\n\n"
                f"| | |\n|---|---|\n"
                f"| Feels Like | {feels_like}°C |\n"
                f"| High / Low | {temp_max}°C / {temp_min}°C |\n"
                f"| Humidity | {humidity}% |\n"
                f"| Wind | {wind_speed} km/h |\n"
                f"| Visibility | {round(current.get('visibility', 10000) / 1000, 1)} km |\n"
            ),
        }


weather_tool = WeatherTool()
