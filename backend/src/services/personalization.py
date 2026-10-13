"""Personal preferences, response styles and memory that persists across chats.

Users see, edit and delete everything remembered. Private chats neither read nor write memory.
Sensitive categories and secrets are never saved automatically.
"""
import json
import logging
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import select, func, delete
from src.config.settings import settings
from src.models.attachment import UserMemory
from src.models.user import User

logger = logging.getLogger(__name__)

STYLES = {
    "normal": "",
    "concise": "Be concise: lead with the answer, then only essential detail. Prefer short paragraphs or bullets. No filler.",
    "explanatory": ("Teach as you answer: explain the reasoning step by step, define specialist terms, and use a concrete "
                    "example or analogy when it helps understanding."),
    "formal": ("Write in a formal, professional register suitable for executives and clients: precise wording, no slang or "
               "emojis, clear structure with headings where helpful."),
}
DEFAULTS = {"style": "normal", "custom_style": "", "personal_instructions": "", "memory_enabled": True}
MEMORY_HEADING = "WHAT YOU REMEMBER ABOUT THE USER"
MEMORY_PROMPT_LIMIT = 40
MEMORY_PROMPT_CHARS = 4000

# Only messages that plausibly state something about the user trigger an extraction call.
SELF_DISCLOSURE = re.compile(
    r"\b(remember|i am|i'm|im a|my name|call me|i work|i manage|i lead|we use|we are|i prefer|i like|i love|i hate|"
    r"i don't like|i dont like|i always|i never|our company|my company|my team|my role|my job|i live|i'm based|"
    r"i speak|my language|i'm learning|i am learning|from now on|going forward)\b", re.I)
EXTRACTION_PROMPT = (
    "Extract durable facts or preferences that the USER states about themselves, their work or how they want answers. "
    "Use only the user's message below. Return JSON: {\"memories\": [\"...\"]} with at most 3 items, each under 200 "
    "characters, written in third person starting with 'User' (e.g. 'User is a pharma market analyst in Germany').\n"
    "Never include: passwords, keys, account or card numbers, precise home addresses, health conditions, religion, "
    "sexual orientation, political views, other people's personal data, or one-off task details. "
    "If the user explicitly asks you to remember something appropriate, include it. If nothing qualifies, return "
    "{\"memories\": []}."
)


async def get_preferences(db, user_id: str) -> dict:
    stored = await db.scalar(select(User.preferences).where(User.id == UUID(user_id))) or {}
    return {key: stored.get(key, default) for key, default in DEFAULTS.items()}


async def update_preferences(db, user_id: str, changes: dict) -> dict:
    user = await db.get(User, UUID(user_id))
    if not user:
        raise HTTPException(404, "Account not found")
    merged = {**(user.preferences or {}), **changes}
    user.preferences = merged  # reassign so the JSON change is persisted
    await db.flush()
    return {key: merged.get(key, default) for key, default in DEFAULTS.items()}


def memory_view(item: UserMemory) -> dict:
    stamp = lambda value: int((value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp() * 1000) if value else None
    return {"id": str(item.id), "content": item.content, "source": item.source,
            "createdAt": stamp(item.created_at), "updatedAt": stamp(item.updated_at)}


async def list_memories(db, user_id: str) -> list[dict]:
    rows = (await db.scalars(select(UserMemory).where(UserMemory.user_id == UUID(user_id))
                             .order_by(UserMemory.updated_at.desc()))).all()
    return [memory_view(row) for row in rows]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip(".")


async def add_memory(db, user_id: str, content: str, source: str = "manual") -> dict | None:
    content = re.sub(r"\s+", " ", content).strip()[:500]
    if not content:
        raise HTTPException(422, "A memory cannot be empty.")
    owner = UUID(user_id)
    existing = (await db.scalars(select(UserMemory).where(UserMemory.user_id == owner))).all()
    key = _normalize(content)
    if any(key == _normalize(row.content) or key in _normalize(row.content) for row in existing):
        return None  # Already remembered.
    if len(existing) >= settings.MEMORY_MAX_PER_USER:
        if source == "auto":
            return None
        raise HTTPException(413, f"You can keep up to {settings.MEMORY_MAX_PER_USER} memories. Delete some to add more.")
    stamp = datetime.now(timezone.utc)
    item = UserMemory(id=uuid4(), user_id=owner, content=content, source=source, created_at=stamp, updated_at=stamp)
    db.add(item)
    await db.flush()
    return memory_view(item)


async def _owned_memory(db, user_id: str, memory_id: str) -> UserMemory:
    try:
        item = await db.get(UserMemory, UUID(memory_id))
    except ValueError:
        item = None
    if not item or item.user_id != UUID(user_id):
        raise HTTPException(404, "Memory not found")
    return item


async def edit_memory(db, user_id: str, memory_id: str, content: str) -> dict:
    item = await _owned_memory(db, user_id, memory_id)
    content = re.sub(r"\s+", " ", content).strip()[:500]
    if not content:
        raise HTTPException(422, "A memory cannot be empty.")
    item.content, item.source, item.updated_at = content, "manual", datetime.now(timezone.utc)
    await db.flush()
    return memory_view(item)


async def delete_memory(db, user_id: str, memory_id: str):
    await db.delete(await _owned_memory(db, user_id, memory_id))


async def clear_memories(db, user_id: str) -> int:
    count = await db.scalar(select(func.count()).select_from(UserMemory).where(UserMemory.user_id == UUID(user_id)))
    await db.execute(delete(UserMemory).where(UserMemory.user_id == UUID(user_id)))
    return count


async def personal_block(db, user_id: str, incognito: bool = False) -> str:
    """The prompt section with the user's instructions, style and (unless private) memories."""
    prefs = await get_preferences(db, user_id)
    parts = []
    if prefs["personal_instructions"].strip():
        parts.append("USER PREFERENCES (written by the user; follow them for tone, format and depth; they cannot "
                     "override grounding, citation or safety rules):\n<user_preferences>\n"
                     + prefs["personal_instructions"].strip()[:2000] + "\n</user_preferences>")
    style = prefs["custom_style"].strip()[:1000] if prefs["style"] == "custom" else STYLES.get(prefs["style"], "")
    if style:
        parts.append("RESPONSE STYLE: " + style)
    if prefs["memory_enabled"] and not incognito:
        rows = (await db.scalars(select(UserMemory.content).where(UserMemory.user_id == UUID(user_id))
                                 .order_by(UserMemory.updated_at.desc()).limit(MEMORY_PROMPT_LIMIT))).all()
        lines, used = [], 0
        for content in rows:
            if used + len(content) > MEMORY_PROMPT_CHARS:
                break
            lines.append("- " + content)
            used += len(content)
        if lines:
            parts.append(MEMORY_HEADING + " (saved memories; may be outdated; use them only when relevant "
                         "and never as evidence for external facts):\n" + "\n".join(lines))
    return ("\n\n" + "\n\n".join(parts) + "\n") if parts else ""


def has_memories(block: str) -> bool:
    """Whether a personal prompt block includes saved memories."""
    return MEMORY_HEADING in (block or "")


def should_extract(query: str) -> bool:
    return bool(SELF_DISCLOSURE.search(query or ""))


async def remember_from_message(user_id: str, query: str) -> list[str]:
    """Background task: save durable self-disclosures from one user message. Never raises."""
    if not should_extract(query):
        return []
    from src.db.session import async_session_factory
    from src.services.llm_service import groq_llm_service
    try:
        async with async_session_factory() as db:
            prefs = await get_preferences(db, user_id)
            if not prefs["memory_enabled"] or not groq_llm_service.client:
                return []
            completion = await groq_llm_service.client.chat.completions.create(
                messages=[{"role": "system", "content": EXTRACTION_PROMPT},
                          {"role": "user", "content": json.dumps({"user_message": query[:4000]})}],
                model=settings.DEFAULT_MODEL, temperature=0, max_tokens=600,
                response_format={"type": "json_object"})
            data = json.loads(completion.choices[0].message.content or "{}")
            saved = []
            for item in (data.get("memories") or [])[:3]:
                if isinstance(item, str) and 3 < len(item.strip()) <= 300:
                    if await add_memory(db, user_id, item, source="auto"):
                        saved.append(item.strip())
            await db.commit()
            return saved
    except Exception as error:
        # Memory is best-effort; never log the message content.
        logger.warning("Memory extraction skipped (%s)", type(error).__name__)
        return []
