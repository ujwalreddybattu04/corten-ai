"""One validated public brief per event version. Questions and histories are private."""
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from src.db.session import async_session_factory
from src.models.pharma import PharmaSharedBrief
from src.services.pharma_events import digest
from src.services.llm_runtime import LLMProviderError

CONTRACT = "source-only-regional-v5"
# Tasks survive an individual reader disconnect; the durable lease coordinates workers.
_tasks = {}


async def _generate(item, model, generate, refresh=False):
    key = digest([item["id"], item["version"], CONTRACT, model])
    owner = secrets.token_hex(16)
    deadline = asyncio.get_running_loop().time() + 125
    while asyncio.get_running_loop().time() < deadline:
        now = datetime.now(timezone.utc)
        async with async_session_factory() as db:
            await db.execute(insert(PharmaSharedBrief).values(key=key, document_id=item["document_id"],
                version=item["raw_version"], contract=CONTRACT, model=model, status="pending", owner=owner,
                lease_until=now+timedelta(seconds=130), usage={}).on_conflict_do_nothing())
            row = await db.scalar(select(PharmaSharedBrief).where(PharmaSharedBrief.key==key).with_for_update())
            recent=row.generated_at and row.generated_at>=now-timedelta(minutes=5)
            if row.status=="ready" and row.answer and (not refresh or recent):
                return {"text":row.answer,"model":row.model,"usage":row.usage,"shared":True}
            if row.status=='fallback' and row.answer and row.lease_until and row.lease_until>now and not refresh:
                return {'text':row.answer,'model':row.model,'usage':row.usage,'shared':True}
            if row.owner==owner or not row.lease_until or row.lease_until<=now or (row.status=='fallback' and refresh):
                row.owner=owner;row.status="pending";row.lease_until=now+timedelta(seconds=130)
                await db.commit()
                break
            await db.commit()
        await asyncio.sleep(.3)
    else:
        raise LLMProviderError("This record's brief is being prepared. Please retry shortly.")
    try:
        # The generator accepts no caller question or caller history.
        result = await asyncio.wait_for(generate(), timeout=115)
        async with async_session_factory() as db:
            fallback=result['usage'].get('basis')=='source_summary'
            saved = await db.execute(update(PharmaSharedBrief).where(PharmaSharedBrief.key==key,
                PharmaSharedBrief.owner==owner, PharmaSharedBrief.status=="pending").values(status="fallback" if fallback else "ready",
                answer=result["text"],usage=result["usage"],generated_at=datetime.now(timezone.utc),lease_until=datetime.now(timezone.utc)+timedelta(minutes=2) if fallback else None,owner=None))
            if not saved.rowcount:
                raise LLMProviderError("The source brief changed while it was being prepared. Please retry.")
            await db.commit()
        return {**result,"shared":False}
    except BaseException:
        async with async_session_factory() as db:
            await db.execute(update(PharmaSharedBrief).where(PharmaSharedBrief.key==key,PharmaSharedBrief.owner==owner)
                .values(status="failed",owner=None,lease_until=datetime.now(timezone.utc)))
            await db.commit()
        raise


async def shared_brief(item, model, generate, refresh=False):
    key = digest([item["id"],item["version"],CONTRACT,model])
    task = _tasks.get(key)
    if task is None:
        if len(_tasks)>=16:raise LLMProviderError("The analyst brief service is busy. Please retry shortly.")
        task = asyncio.create_task(_generate(item,model,generate,refresh));_tasks[key]=task
        def done(completed):
            if _tasks.get(key) is completed:_tasks.pop(key,None)
            if not completed.cancelled():completed.exception()
        task.add_done_callback(done)
    return await asyncio.shield(task)
