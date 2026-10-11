"""Maintained application self-description and basic workspace explanations."""
from src.config.settings import settings


def self_answer(intent: str, clarification: str | None = None) -> str | None:
    brand = settings.BRAND_NAME
    if intent == "identity":
        return f"I’m {brand}, an AI assistant developed by {settings.COMPANY_NAME}."
    if intent == "greeting":
        return f"Hello! I’m {brand}. How can I help you today?"
    if intent == "agents":
        return (
            f"Yes. {brand} uses a query router to choose how to answer and a research agent "
            "for multi-step research. The research agent can break a question into sub-questions, "
            "gather sources, check for information gaps and combine the findings. "
            "It can use search and other tools when relevant. These components help with research; "
            "they do not provide autonomous company approvals or make forecasting decisions for your team."
        )
    if intent == "capabilities":
        from src.tools import tool_registry
        descriptions = {
            "web_search": "web research", "url_reader": "reading public webpages",
            "calculator": "calculations", "weather": "weather lookups", "image_search": "image search",
        }
        enabled = [descriptions[name] for name in tool_registry.get_tool_names() if name in descriptions]
        tools = ", ".join(enabled) or "answering questions"
        return (f"I can help with {tools}, explanations, writing and multi-step research. "
                "The Analyst Workspace converts yearly CSV inputs into smooth monthly series using Average "
                "or Exit mode, verifies yearly targets and exports CSV, JSON and PDF results. "
                "External tools depend on their configured providers.")
    if intent == "training":
        return (f"{settings.COMPANY_NAME} developed the {brand} application. That is different from "
                "training the underlying language model, which is supplied through the configured AI provider. "
                "I don’t have verified details of its training dataset.")
    if intent == "forecast_explanation":
        return ("Forecast assumptions describe the expected conditions and inputs used to build a forecast, "
                "such as demand, pricing and costs. Review these assumptions with the team, record their "
                "supporting evidence and update them when the underlying conditions change.")
    if intent == "clarification":
        return clarification or "Which company, person, place or topic are you referring to?"
    return None
