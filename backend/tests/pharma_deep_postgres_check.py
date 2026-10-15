"""Run only in a disposable corten_deep_check_* database, never in the application database."""
import asyncio,uuid,re
from datetime import timedelta
import httpx
from fastapi import FastAPI,Depends,HTTPException
from sqlalchemy import update
from src.config.settings import settings
from src.db.session import async_session_factory,engine
from src.models.user import User
from src.models.pharma_deep import PharmaDeepResearch as Job
from src.services import pharma_deep_store as store
from src.services.pharma_deep_plan import DeepPlan
from src.api.v1 import pharma_deep
from src.api.deps import get_current_user_id

async def main():
    assert re.fullmatch(r'corten_deep_check_[a-f0-9]{12}',settings.DATABASE_URL.rsplit('/',1)[-1]),'Disposable database required'
    owners=[str(uuid.uuid4()) for _ in range(3)]
    async with async_session_factory() as db:
        for index,owner in enumerate(owners):db.add(User(id=uuid.UUID(owner),name='Disposable research check',email=f'deep-{index}@example.invalid',preferences={}))
        await db.commit()
    plan=DeepPlan(subjects=['sildenafil'],topics=['trials']).model_dump()
    first=await store.create(owners[0],'Review sildenafil registered trials.',plan)
    second=await store.create(owners[0],'Review sildenafil trial results.',plan)
    other=await store.create(owners[1],'Review sildenafil public evidence.',plan)
    third=await store.create(owners[2],'Review sildenafil study records.',plan)
    try:await store.get(first['id'],owners[1]);raise AssertionError('Cross-account report disclosure')
    except HTTPException as exc:assert exc.status_code==404
    results=await asyncio.gather(store.start(first['id'],owners[0],plan,first['revision']),store.start(second['id'],owners[0],plan,second['revision']),return_exceptions=True)
    started=[r for r in results if isinstance(r,dict)];blocked=[r for r in results if isinstance(r,HTTPException)]
    assert len(started)==1 and len(blocked)==1 and blocked[0].status_code==409
    first=started[0]
    assert first['started_at'] is None,'Queue waiting must not consume the work time budget'
    duplicate=await store.start(first['id'],owners[0],plan,1)
    assert duplicate['id']==first['id'] and duplicate['status']=='queued'
    await store.start(other['id'],owners[1],plan,1);await store.start(third['id'],owners[2],plan,1)
    w1,w2,w3=[str(uuid.uuid4()) for _ in range(3)]
    claim1=await store.claim(w1);claim2=await store.claim(w2)
    assert claim1['started_at'] is not None
    assert claim1 and claim2 and claim1['id']!=claim2['id'] and await store.claim(w3) is None
    await store.save(claim1['id'],w1,{'model_calls':2,'phase':'read'},[],'read')
    try:await store.save(claim1['id'],w3,{'model_calls':0},[],'search');raise AssertionError('Stale worker overwrote a job')
    except InterruptedError:pass
    async with async_session_factory() as db:
        await db.execute(update(Job).where(Job.id==uuid.UUID(claim1['id'])).values(lease_until=store.now()-timedelta(seconds=1)));await db.commit()
    recovered=await store.claim(w3)
    assert recovered['id']==claim1['id'] and recovered['checkpoint']['model_calls']==2
    assert await store.heartbeat(claim1['id'],w1) is False
    # A browser cancellation invalidates the lease; it never resets the metered call counter.
    async with async_session_factory() as db:owner=str((await db.get(Job,uuid.UUID(claim1['id']))).owner_id)
    await store.cancel(claim1['id'],owner)
    assert await store.heartbeat(claim1['id'],w3) is False
    await store.finish_cancelled(claim1['id'],w3,{'model_calls':2},[],{'markdown':'Saved source evidence only.'})
    stopped=await store.get(claim1['id'],owner)
    assert stopped['status']=='cancelled' and stopped['metrics']['model_calls']==2
    await store.save(claim2['id'],w2,{'model_calls':3,'phase':'write'},[],'write',status='failed')
    async with async_session_factory() as db:owner2=str((await db.get(Job,uuid.UUID(claim2['id']))).owner_id)
    retried=await store.retry(claim2['id'],owner2)
    assert retried['status']=='queued' and retried['metrics']['model_calls']==3
    # Exercise actual HTTP auth, account filtering, input bounds and private-mode behavior.
    settings.PHARMA_INTELLIGENCE_ENABLED=True;settings.PHARMA_DEEP_RESEARCH_ENABLED=True
    app=FastAPI();app.include_router(pharma_deep.router,prefix='/deep',dependencies=[Depends(get_current_user_id)])
    app.dependency_overrides[get_current_user_id]=lambda:owners[2]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        assert (await client.get('/deep/'+first['id'])).status_code==404
        assert (await client.get('/deep/'+first['id']+'/download/xlsx')).status_code==404
        assert (await client.post('/deep/plan',json={'query':'Pfizer obesity pipeline','private':True})).status_code==422
        assert (await client.post('/deep/plan',content=b'x'*24577,headers={'Content-Type':'application/json'})).status_code==413
        app.dependency_overrides.clear()
        assert (await client.get('/deep')).status_code==401
    await engine.dispose()
    print(__import__('json').dumps({'passed':True,'migration':'0008','account_isolation':True,'idempotent_start':True,
        'one_active_run_per_account':True,'global_two_job_limit':True,'stale_worker_blocked':True,'lease_recovery_preserves_metering':True,
        'cancellation':True,'retry_preserves_metering':True,'http_auth_and_private_mode':True,'bounded_request_body':True,'production_account_writes':False}))

if __name__=='__main__':asyncio.run(main())
