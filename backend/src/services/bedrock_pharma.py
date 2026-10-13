"""Text-only regional model calls through the protected host gateway."""
import httpx
from src.config.settings import settings
from src.services.llm_runtime import LLMProviderError


async def complete(messages, model, max_tokens=1024):
    system = [{"text": m["content"]} for m in messages if m["role"] == "system"]
    turns = []
    for message in messages:
        if message["role"] not in ("user", "assistant"):
            continue
        if turns and turns[-1]["role"] == message["role"]:
            turns[-1]["content"][0]["text"] += "\n\n" + message["content"]
        else:
            turns.append({"role": message["role"], "content": [{"text": message["content"]}]})
    transport = httpx.AsyncHTTPTransport(uds=settings.PHARMA_BEDROCK_SOCKET, retries=0)
    try:
        async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(110, connect=5)) as client:
            response = await client.post("http://bedrock/complete", json={"modelId": model, "system": system,
                "messages": turns, "inferenceConfig": {"maxTokens": max_tokens}})
        if response.status_code == 429:
            code=response.json().get("error")
            message = "The monthly Pharma analysis budget has been reached." if code == "monthly_budget_reached" else "The daily Pharma generation limit has been reached. Existing briefs remain available." if code == "daily_budget_reached" else "The analysis service is busy. Please retry shortly."
            raise LLMProviderError(message)
        response.raise_for_status()
        result = response.json()
        if result.get("stop_reason") != "end_turn" or result.get("model") != model or not isinstance(result.get("text"), str) or not result["text"].strip():
            raise ValueError("Incomplete model response")
        return result
    except LLMProviderError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise LLMProviderError("The Pharma analysis could not be completed. Please retry shortly.") from exc
