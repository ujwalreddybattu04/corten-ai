import json
import logging
import re
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List

from groq import AsyncGroq
from src.config.settings import settings
from src.services.agents.query_context import clean_history, company_alias
from src.config.prompts import (
    RAG_SYSTEM_PROMPT, DIRECT_SYSTEM_PROMPT, PLANNING_SYSTEM_PROMPT,
    TITLE_SYSTEM_PROMPT, FOLLOW_UP_SYSTEM_PROMPT, ARTICLE_SUMMARY_SYSTEM_PROMPT,
    FOCUS_MODE_PROMPTS, FOCUS_MODE_PLANNING_HINTS,
    COMPANY_FACTS_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def format_evidence(context_results: list, char_budget: int = 10000) -> str:
    """Use stable UI citation IDs and bound source material for generation and review."""
    entries = []
    chars_used = 0
    for idx, result in enumerate(context_results[:8], start=1):
        snippet = result.get("snippet", "")
        if len(snippet) > 4000:
            snippet = snippet[:2600] + "\n[excerpt continues]\n" + snippet[-1400:]
        citation = result.get("citationIndex", idx)
        label = f"Source [{citation}]" if citation is not None else "Tool output (no citation number)"
        entry = f"{label}:\nTitle: {result.get('title', 'N/A')}\nURL: {result.get('url', '')}\nContent: {snippet}\n\n"
        if chars_used + len(entry) > char_budget:
            break
        entries.append(entry)
        chars_used += len(entry)
    return "".join(entries)

class GroqLLMService:
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        if not self.api_key:
            logger.warning("GROQ_API_KEY is not set. LLM generation will fail.")
            self.client = None
        else:
            self.client = AsyncGroq(api_key=self.api_key)
            
        self.default_model = settings.DEFAULT_MODEL

    def _build_system_prompt(self, context_results: List[Dict[str, Any]], focus_mode: str = "all", company_lookup: bool = False) -> str:
        """Constructs a dynamic system prompt, token-budgeted for Groq limits.

        Injects focus-mode-specific instructions when a specialized mode is active.
        """
        current_date = datetime.now().strftime("%B %d, %Y")

        if company_lookup:
            return COMPANY_FACTS_SYSTEM_PROMPT.format(
                company_name=company_alias(settings.COMPANY_NAME), current_date=current_date
            ) + format_evidence(context_results)

        if not context_results:
            prompt = DIRECT_SYSTEM_PROMPT.format(
                brand_name=settings.BRAND_NAME,
                company_name=settings.COMPANY_NAME,
                current_date=current_date
            )
            # Inject focus mode instructions for direct answers too
            if focus_mode and focus_mode != "all":
                focus_instructions = FOCUS_MODE_PROMPTS.get(focus_mode, "")
                if focus_instructions:
                    prompt += "\n" + focus_instructions
            return prompt

        prompt = RAG_SYSTEM_PROMPT.format(
            brand_name=settings.BRAND_NAME,
            company_name=settings.COMPANY_NAME,
            current_date=current_date
        )

        # Inject focus mode instructions before sources
        if focus_mode and focus_mode != "all":
            focus_instructions = FOCUS_MODE_PROMPTS.get(focus_mode, "")
            if focus_instructions:
                prompt += focus_instructions

        return prompt + format_evidence(context_results)

    async def stream_answer(self, query: str, context_results: List[Dict[str, Any]], history: List[Dict[str, str]] = None, focus_mode: str = "all", company_lookup: bool = False) -> AsyncGenerator[str, None]:
        """
        Streams the LLM response chunk by chunk using Groq.
        Token-budgeted to stay within Groq limits.
        Focus mode injects specialized instructions for different query types.
        """
        if not self.client:
            yield "LLM generation failed because Groq API key is missing."
            return

        system_prompt = self._build_system_prompt(context_results, focus_mode, company_lookup)

        # Build message history
        messages_payload = [{"role": "system", "content": system_prompt}]
        if history:
            # Take only the last 4 messages (2 complete turns) to save tokens
            recent_history = clean_history(history)[-4:]
            # Trim each history message to prevent overflow
            for msg in recent_history:
                trimmed = {**msg}
                if len(trimmed.get("content", "")) > 1500:
                    trimmed["content"] = trimmed["content"][:1500] + "..."
                messages_payload.append(trimmed)
        current_request = query[:1000]
        if context_results:
            current_request += "\nUse inline numeric source citations after factual claims, for example [1]."
        elif re.search(r"\b(?:write|draft|compose|explain)\b", query, re.I) and re.search(
            r"\b(?:forecast|assumptions?|revenue|sales|budget|expenses?)\b", query, re.I
        ):
            current_request += (
                "\nUse only the inputs actually provided in this conversation. "
                "For a conceptual explanation, explain the concept generally; do not invent a "
                "company-specific forecast or numerical assumptions. For a requested template, "
                "use clearly marked placeholders for missing figures. Do not claim to have reviewed "
                "financial projections, historical data or market analysis that was not supplied."
            )
        messages_payload.append({"role": "user", "content": current_request})

        try:
            model_options = {}
            if self.default_model.startswith("openai/gpt-oss-"):
                model_options["reasoning_effort"] = "low"
            stream = await self.client.chat.completions.create(
                messages=messages_payload,
                model=self.default_model,
                temperature=0.2,
                max_tokens=1024 if company_lookup else 4096,
                stream=True,
                stop=[
                    "\n\n**Sources", "\n\nSources"
                ] if context_results else None,
                **model_options,
            )

            has_content = False
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    has_content = has_content or bool(chunk.choices[0].delta.content.strip())
                    yield chunk.choices[0].delta.content
            if not has_content:
                raise RuntimeError("The AI returned an empty answer. Please try again.")

        except Exception as e:
            logger.exception(f"Groq API streaming failed: {e}")
            raise e

    async def stream_article_summary(self, title: str, article_text: str, search_results: List[Dict[str, Any]], description: str = "") -> AsyncGenerator[str, None]:
        """
        Streams a narrative-style article summary using a dedicated journalist prompt.
        Token-budgeted to stay within Groq free tier limits (~4500 input tokens).
        """
        if not self.client:
            yield "LLM generation failed because Groq API key is missing."
            return

        # ── Token Budget ──────────────────────────────────────────────────
        # Groq model context is large enough; the real constraint is TPM.
        # Give the LLM plenty of source material so the summary is complete.
        INPUT_CHAR_BUDGET = 18000
        system_prompt = ARTICLE_SUMMARY_SYSTEM_PROMPT
        remaining = INPUT_CHAR_BUDGET - len(system_prompt) - 200  # 200 for user message framing

        # Prioritize: article text gets most budget, then sources fill the rest
        article_budget = min(len(article_text), int(remaining * 0.75)) if article_text else 0
        source_budget = remaining - article_budget

        # Add sources (capped to fit budget)
        source_chars_used = 0
        max_sources = 4
        for idx, result in enumerate(search_results[:max_sources], start=1):
            snippet = result.get('snippet', '')[:400]
            entry = f"Source [{idx}]:\nTitle: {result.get('title', 'N/A')}\nContent: {snippet}\n\n"
            if source_chars_used + len(entry) > source_budget:
                break
            system_prompt += entry
            source_chars_used += len(entry)

        # Build the user message with article content
        user_content = f"Write an in-depth summary of this story: \"{title}\"\n\n"
        if article_text and article_budget > 0:
            user_content += f"FULL ARTICLE TEXT:\n{article_text[:article_budget]}\n\n"
        if description and not article_text:
            user_content += f"ARTICLE EXCERPT: {description[:800]}\n\n"
        user_content += "Write a COMPLETE, compelling, flowing narrative summary. Tell the full story from beginning to end. Include a proper concluding paragraph — never stop mid-sentence or mid-thought."

        messages_payload = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            stream = await self.client.chat.completions.create(
                messages=messages_payload,
                model=self.default_model,
                temperature=0.4,
                max_tokens=4096,
                stream=True,
                # No stop sequences — the prompt already forbids source lists,
                # and stop words like "Sources" / "References" can appear in
                # legitimate article prose, causing premature truncation.
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.exception(f"Groq API article summary streaming failed: {e}")
            raise e

    async def stream_article_followup(self, title: str, followup: str, previous_summary: str, search_results: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """
        Streams a follow-up answer about a specific article.
        Token-budgeted for Groq limits.
        """
        if not self.client:
            yield "LLM generation failed because Groq API key is missing."
            return

        system_prompt = (
            "You are a knowledgeable journalist assistant. The user is reading an article and asking follow-up questions about it.\n\n"
            f"ARTICLE: \"{title}\"\n\n"
        )
        if previous_summary:
            system_prompt += f"YOUR PREVIOUS SUMMARY OF THIS ARTICLE:\n{previous_summary[:1500]}\n\n"

        system_prompt += (
            "RULES:\n"
            "- Answer the user's question specifically about THIS article.\n"
            "- Use inline citations [1], [2] when referencing sources.\n"
            "- NEVER add a Sources/References section at the end.\n"
            "- Write in clear, flowing prose.\n\n"
            "CONTEXT DATA:\n"
        )
        source_chars = 0
        for idx, result in enumerate(search_results[:4], start=1):
            snippet = result.get('snippet', '')[:400]
            entry = f"Source [{idx}]:\nTitle: {result.get('title', 'N/A')}\nContent: {snippet}\n\n"
            if source_chars + len(entry) > 6000:
                break
            system_prompt += entry
            source_chars += len(entry)

        messages_payload = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": followup[:500]},
        ]

        try:
            stream = await self.client.chat.completions.create(
                messages=messages_payload,
                model=self.default_model,
                temperature=0.4,
                max_tokens=2048,
                stream=True,
                stop=["\n\n**Sources", "\n\nSources", "\n\nReferences"],
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.exception(f"Groq API article follow-up streaming failed: {e}")
            raise e

    async def generate_research_plan(self, query: str, focus_mode: str = "all") -> Dict[str, Any]:
        """
        Generates a formal research intent and 3-4 specific search strings.
        Used for the 'Thinking' UI phase. Focus mode steers sub-query generation.
        """
        if not self.client:
            return {"intent": f"Search for {query}", "queries": [query]}

        system_prompt = PLANNING_SYSTEM_PROMPT
        system_prompt += ("\nToday is " + datetime.now().strftime("%B %d, %Y") +
                          ". Preserve dates explicitly requested by the user. For latest/current "
                          "requests, use the current year; do not introduce stale years from examples.")

        # Inject focus mode planning hint
        if focus_mode and focus_mode != "all":
            hint = FOCUS_MODE_PLANNING_HINTS.get(focus_mode)
            if hint:
                system_prompt += f"\n\nFOCUS MODE INSTRUCTION: {hint}"

        try:
            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                model=self.default_model,
                temperature=0.3,
                max_tokens=200,
                response_format={"type": "json_object"}
            )
            return json.loads(chat_completion.choices[0].message.content)
        except Exception as e:
            logger.error(f"Error generating research plan: {str(e)}")
            return {"intent": f"Searching for {query}...", "queries": [query]}

    async def generate_thread_title(self, query: str) -> str:
        """
        Generates a concise 3-5 word title based on the user's initial query.
        """
        if not self.client:
            return "New Thread"
            
        system_prompt = TITLE_SYSTEM_PROMPT
        
        try:
            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                model=self.default_model,
                temperature=0.3,
                max_tokens=20,
            )
            return chat_completion.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating title: {str(e)}")
            return "New Thread"

    async def generate_follow_up_questions(self, query: str, context: list) -> list[str]:
        """
        Generates exactly 3 follow-up questions based on the query and context.
        Designed to be run concurrently with the main answer stream.
        """
        if not self.client:
            return []
            
        system_prompt = FOLLOW_UP_SYSTEM_PROMPT
        
        # Create a lightweight context summary to save tokens
        context_str = " ".join([f"{item.get('title', '')}: {item.get('snippet', item.get('content', ''))}" for item in context])[:3000]
        user_prompt = f"Original Query: {query}\n\nContext: {context_str}"
        
        try:
            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model=self.default_model,
                temperature=0.4,
                response_format={"type": "json_object"}
            )
            response_text = chat_completion.choices[0].message.content
            parsed = json.loads(response_text)
            questions = parsed.get("questions", [])
            return questions[:5]
        except Exception as e:
            logger.error(f"Error generating follow-ups: {str(e)}")
            return []

groq_llm_service = GroqLLMService()
