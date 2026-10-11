"""
Thread service — CRUD for threads and messages.
"""

import uuid
import secrets
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from src.models.thread import Thread
from src.models.message import Message
from src.models.source import Source
from src.db.redis import cache_delete, make_cache_key

logger = logging.getLogger(__name__)


class ThreadService:

    async def list_threads(self, db, user_id, limit=20, offset=0):
        result = await db.execute(
            select(Thread)
            .where(Thread.user_id == uuid.UUID(user_id))
            .order_by(Thread.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_thread(self, db, thread_id, user_id=None):
        stmt = select(Thread).where(Thread.id == uuid.UUID(thread_id))
        if user_id:
            stmt = stmt.where(Thread.user_id == uuid.UUID(user_id))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_thread_by_share_token(self, db, share_token):
        result = await db.execute(
            select(Thread).where(Thread.share_token == share_token, Thread.is_public.is_(True))
        )
        return result.scalar_one_or_none()

    async def create_thread(self, db, user_id, title, focus_mode="all",
                             model_used="llama-3.1-8b-instant", space_id=None):
        thread = Thread(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            space_id=uuid.UUID(space_id) if space_id else None,
            title=title[:500],
            focus_mode=focus_mode,
            model_used=model_used,
        )
        db.add(thread)
        await db.flush()
        return thread

    async def rename_thread(self, db, thread_id, user_id, new_title):
        thread = await self.get_thread(db, thread_id, user_id)
        if not thread:
            return None
        thread.title = new_title[:500]
        await db.flush()
        await cache_delete(make_cache_key("thread", thread_id))
        return thread

    async def delete_thread(self, db, thread_id, user_id):
        thread = await self.get_thread(db, thread_id, user_id)
        if not thread:
            return False
        await db.delete(thread)
        await db.flush()
        await cache_delete(make_cache_key("thread", thread_id))
        return True

    async def toggle_share(self, db, thread_id, user_id, make_public):
        thread = await self.get_thread(db, thread_id, user_id)
        if not thread:
            return None
        thread.is_public = make_public
        if make_public and not thread.share_token:
            thread.share_token = secrets.token_urlsafe(32)
        elif not make_public:
            thread.share_token = None
        await db.flush()
        return thread

    async def get_messages(self, db, thread_id, limit=50, offset=0):
        result = await db.execute(
            select(Message)
            .where(Message.thread_id == uuid.UUID(thread_id))
            .order_by(Message.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def add_message(self, db, thread_id, role, content, model_used=None,
                          tokens_used=None, search_provider=None, search_query=None,
                          processing_time_ms=None):
        message = Message(
            id=uuid.uuid4(),
            thread_id=uuid.UUID(thread_id),
            role=role,
            content=content,
            model_used=model_used,
            tokens_used=tokens_used,
            search_provider=search_provider,
            search_query=search_query,
            processing_time_ms=processing_time_ms,
        )
        db.add(message)
        await db.execute(
            update(Thread)
            .where(Thread.id == uuid.UUID(thread_id))
            .values(message_count=Thread.message_count + 1, last_message_at=func.now(), updated_at=func.now())
        )
        await db.flush()
        return message

    async def add_sources(self, db, message_id, sources):
        records = []
        for i, s in enumerate(sources):
            record = Source(
                id=uuid.uuid4(),
                message_id=uuid.UUID(message_id),
                url=s.get("url", ""),
                title=s.get("title", ""),
                domain=s.get("domain", ""),
                favicon_url=s.get("favicon_url"),
                snippet=s.get("snippet"),
                citation_index=s.get("citation_index", i + 1),
                relevance_score=s.get("relevance_score"),
                is_primary=(i == 0),
            )
            records.append(record)
            db.add(record)
        await db.flush()
        return records


thread_service = ThreadService()
