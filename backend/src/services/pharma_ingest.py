"""Scheduled public-source ingestion. User page views never trigger upstream pulls."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import httpx
from sqlalchemy import select,text
from sqlalchemy.dialects.postgresql import insert
from src.db.session import async_session_factory,engine
from src.models.pharma import PharmaSourceState
from src.services.pharma_catalog import SOURCE_CATALOG,TRADE_DOMAINS
from src.services.pharma_repository import store_record,register_drug,seed_identities,link_drugs
from src.services.pharma_sources import (
    FDA_DRUGS_RSS,FDA_SAFETY_RSS,EMA_JSON,TRADE_FEEDS,USER_AGENT,
    read_response,get_json,rss_records,clinical_records,fda_records,ema_records,indexed_news,
)

logger=logging.getLogger(__name__)
INGEST_LOCK=281415705


async def fetch_source(client,name,since,until,state):
    if name=="fda":
        records,metadata=await fda_records(client,since,until);return records,[],metadata
    if name=="trials":
        prior=(state.metadata_json or {}) if state else {}
        cursor=prior.get("next_cursor")
        window=prior.get("window") if cursor else [since,until]
        records=[];metadata={};rejected=0
        # A fresh first page prevents backfill from delaying the newest updates.
        if cursor:
            recent,latest=await clinical_records(client,since,until)
            records.extend(recent);rejected+=latest.get("rejected_records",0)
        for _ in range(3 if cursor else 4):
            page,metadata=await clinical_records(client,*window,cursor)
            records.extend(page);cursor=metadata.get("next_cursor")
            rejected+=metadata.get("rejected_records",0)
            if not cursor:break
        return records,[],{**metadata,"next_cursor":cursor,"window":window,"rejected_records":rejected,"limited":bool(cursor) or bool(rejected)}
    if name in ("fda_updates","fda_safety"):
        url=FDA_DRUGS_RSS if name=="fda_updates" else FDA_SAFETY_RSS
        async with client.stream("GET",url) as response:body=await read_response(response)
        records,metadata=rss_records(body,name,("fda.gov",),since,until)
        return records,[],metadata
    if name=="ema":
        data=await get_json(client,EMA_JSON,limit=32*1024*1024)
        records,aliases,metadata=ema_records(data,since,until)
        return records,aliases,metadata
    if name=="news":
        failures=[]
        for url in TRADE_FEEDS:
            try:
                async with client.stream("GET",url) as response:body=await read_response(response)
                records,metadata=rss_records(body,name,TRADE_DOMAINS,since,until)
                if records:return records,[],metadata
            except (httpx.HTTPError,ValueError) as failure:failures.append(type(failure).__name__)
        records,metadata=await indexed_news(client,name,since,until)
        return records,[],{**metadata,"feed_access_failed":bool(failures)}
    records,metadata=await indexed_news(client,name,since,until)
    return records,[],metadata


async def ingest_source(name,now):
    async with async_session_factory() as db:
        state=await db.get(PharmaSourceState,name)
        previous=state.checked_at if state else None
        retry_at=(state.metadata_json or {}).get("retry_at") if state else None
        if retry_at and datetime.fromisoformat(retry_at)>now:return {"source":name,"deferred":True}
        interval=timedelta(minutes=15) if name=="trials" and state and state.metadata_json.get("next_cursor") else timedelta(hours=6 if name in ("company","news","ema") else 1)
        if previous and state.status in ("available","empty") and now-previous<interval:return {"source":name,"fresh":True}
        since=(now.date()-timedelta(days=89)).isoformat();until=now.date().isoformat()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(25,connect=5),headers={"User-Agent":USER_AGENT},follow_redirects=False) as client:
                records,aliases,metadata=await asyncio.wait_for(fetch_source(client,name,since,until,state),timeout=110)
            inserted=0
            for title,ingredients,names,url in aliases:
                await register_drug(db,title,ingredients,names,url)
            for item,raw,events in records:
                inserted+=await store_record(db,item,raw,events,now)
            metadata={**metadata,"records_received":len(records),"last_event_count":inserted}
            status="available" if records else "empty"
            await db.execute(insert(PharmaSourceState).values(id=name,status=status,checked_at=now,attempted_at=now,metadata_json=metadata)
                .on_conflict_do_update(index_elements=[PharmaSourceState.id],set_={"status":status,"checked_at":now,"attempted_at":now,"metadata_json":metadata}))
            await db.commit()
            return {"source":name,"status":status,"received":len(records),"events":inserted}
        except (httpx.HTTPError,ValueError,asyncio.TimeoutError) as failure:
            await db.rollback()
            delay=timedelta(minutes=15);code=type(failure).__name__;status="unavailable"
            if isinstance(failure,httpx.HTTPStatusError):
                code="HTTP_"+str(failure.response.status_code)
                if failure.response.status_code in (401,403):status="authentication_required";delay=timedelta(hours=6)
                if failure.response.status_code==429:
                    try:delay=timedelta(seconds=min(86400,max(60,int(failure.response.headers.get("Retry-After","900")))))
                    except ValueError:
                        try:delay=timedelta(seconds=min(86400,max(60,(parsedate_to_datetime(failure.response.headers["Retry-After"])-now).total_seconds())))
                        except (ValueError,TypeError,KeyError):pass
            metadata={**(state.metadata_json if state else {}),"last_error":code,"retry_at":(now+delay).isoformat(),"limited":True}
            await db.execute(insert(PharmaSourceState).values(id=name,status=status,checked_at=previous,attempted_at=now,metadata_json=metadata)
                .on_conflict_do_update(index_elements=[PharmaSourceState.id],set_={"status":status,"attempted_at":now,"metadata_json":metadata}))
            await db.commit()
            logger.warning("Pharma source %s unavailable (%s)",name,code)
            return {"source":name,"status":status,"error":code}


async def run():
    # Dedicated session-level advisory lock survives commits in per-source sessions.
    async with engine.connect() as connection:
        locked=await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"),{"key":INGEST_LOCK})
        if not locked:return {"already_running":True}
        try:
            async with async_session_factory() as db:
                await seed_identities(db);await db.commit()
            now=datetime.now(timezone.utc);results=[]
            for source in SOURCE_CATALOG:
                results.append(await ingest_source(source,now))
            async with async_session_factory() as db:
                await link_drugs(db);await db.commit()
            return {"sources":results}
        finally:await connection.execute(text("SELECT pg_advisory_unlock(:key)"),{"key":INGEST_LOCK})

if __name__=="__main__":print(json.dumps(asyncio.run(run())))
