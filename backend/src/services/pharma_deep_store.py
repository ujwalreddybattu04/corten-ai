"""Account isolation, idempotent starts and database leases for recoverable background work."""
import copy,uuid
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,update,func,or_,and_,text
from fastapi import HTTPException
from src.db.session import async_session_factory
from src.models.pharma_deep import PharmaDeepResearch as Job
from src.config.settings import settings

ACTIVE=('queued','running','cancel_requested')
TERMINAL=('completed','partial','cancelled','failed')
def now():return datetime.now(timezone.utc)

def view(job,*,full=True):
    value={key:getattr(job,key) for key in ('query','status','stage','plan','activity','revision')}
    value.update(id=str(job.id),created_at=job.created_at.isoformat(),started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None)
    if full:
        value['report']=job.report
        state=job.checkpoint or {}
        value['metrics']={key:state.get(key,0) for key in ('round','model_calls','search_count','documents_read','verified_claims')}
        value['coverage']=state.get('coverage',[])
        value['outline']=state.get('outline',[])
        value['error']=state.get('last_error','')
        value['retryable']=job.status=='failed' and state.get('retries',0)<1 and state.get('model_calls',0)<12 and bool(job.started_at and (now()-job.started_at).total_seconds()<=900)
        value['evidence_preview']=[{k:q.get(k) for k in ('id','text','source','topic')} for q in state.get('quotes',[])[-5:]]
    else:value['activity']=[]
    return value

async def owned(db,identifier,owner,*,lock=False):
    query=select(Job).where(Job.id==uuid.UUID(str(identifier)),Job.owner_id==uuid.UUID(str(owner)))
    if lock:query=query.with_for_update()
    job=await db.scalar(query)
    if not job:raise HTTPException(404,'Research report not found in this account.')
    return job

async def create(owner,query,plan):
    async with async_session_factory() as db:
        # Serialize the owner's draft/start mutations without locking unrelated accounts.
        await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner, 17))'),{'owner':str(owner)})
        count=await db.scalar(select(func.count()).select_from(Job).where(Job.owner_id==uuid.UUID(owner),Job.created_at>now()-timedelta(days=1)))
        if count>=settings.PHARMA_DEEP_DAILY_REPORTS*3:raise HTTPException(429,'Your daily research planning limit has been reached. Existing reports remain available.')
        job=Job(owner_id=uuid.UUID(owner),query=query,plan=plan,status='draft',stage='plan',checkpoint={},activity=[])
        db.add(job);await db.commit();await db.refresh(job);return view(job)

async def get(identifier,owner):
    async with async_session_factory() as db:return view(await owned(db,identifier,owner))

async def recent(owner):
    async with async_session_factory() as db:
        rows=(await db.scalars(select(Job).where(Job.owner_id==uuid.UUID(owner)).order_by(Job.created_at.desc()).limit(30))).all()
        return [view(row,full=False) for row in rows]

async def start(identifier,owner,plan,revision):
    async with async_session_factory() as db:
        await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner, 17))'),{'owner':str(owner)})
        job=await owned(db,identifier,owner,lock=True)
        if job.status!='draft':return view(job)  # Safe retry after a lost POST response.
        if revision!=job.revision:raise HTTPException(409,'This plan was edited elsewhere. Reopen it before starting.')
        if await db.scalar(select(func.count()).select_from(Job).where(Job.owner_id==uuid.UUID(owner),Job.status.in_(ACTIVE))):
            raise HTTPException(409,'A research report is already running in your account. Open it or stop it before starting another.')
        count=await db.scalar(select(func.count()).select_from(Job).where(Job.owner_id==uuid.UUID(owner),Job.started_at>now()-timedelta(days=1)))
        if count>=settings.PHARMA_DEEP_DAILY_REPORTS:raise HTTPException(429,'Your daily Deep research limit has been reached. Existing reports remain available.')
        # A transaction advisory lock makes the queue admission count exact across API processes.
        await db.execute(text('SELECT pg_advisory_xact_lock(43831729)'))
        count=await db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(ACTIVE)))
        if count>=settings.PHARMA_DEEP_QUEUE_LIMIT:raise HTTPException(429,'Deep research is busy. Your plan is saved; please start it shortly.',headers={'Retry-After':'30'})
        job.plan=plan;job.status='queued';job.started_at=now();job.revision+=1;job.updated_at=now()
        await db.commit();await db.refresh(job);return view(job)

async def cancel(identifier,owner):
    async with async_session_factory() as db:
        job=await owned(db,identifier,owner,lock=True)
        if job.status in ('draft','queued'):
            job.status='cancelled';job.completed_at=now()
        elif job.status=='running':job.status='cancel_requested'
        job.revision+=1;job.updated_at=now();await db.commit();await db.refresh(job);return view(job)

async def claim(worker):
    async with async_session_factory() as db:
        if not await db.scalar(text('SELECT pg_try_advisory_xact_lock(43831730)')):return None
        active=await db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(('running','cancel_requested')),Job.lease_until>=now()))
        if active>=2:return None
        job=await db.scalar(select(Job).where(or_(Job.status=='queued',and_(Job.status.in_(('running','cancel_requested')),Job.lease_until<now())))
            .order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if not job:return None
        if job.status=='cancel_requested':
            job.status='cancelled';job.completed_at=now();await db.commit();return None
        job.status='running';job.lease_owner=worker;job.lease_until=now()+timedelta(seconds=75);job.updated_at=now();job.revision+=1
        await db.commit();return {'id':str(job.id),'query':job.query,'plan':copy.deepcopy(job.plan),'checkpoint':copy.deepcopy(job.checkpoint),'activity':copy.deepcopy(job.activity),'started_at':job.started_at}

async def heartbeat(identifier,worker):
    async with async_session_factory() as db:
        result=await db.execute(update(Job).where(Job.id==uuid.UUID(identifier),Job.lease_owner==worker,Job.status=='running')
            .values(lease_until=now()+timedelta(seconds=75)))
        await db.commit();return result.rowcount==1

async def save(identifier,worker,state,activity,stage,*,report=None,status='running'):
    if len(__import__('json').dumps(state,ensure_ascii=False).encode())>3_000_000:raise ValueError('Research evidence size limit reached')
    values={'checkpoint':copy.deepcopy(state),'activity':copy.deepcopy(activity[-160:]),'stage':stage,'updated_at':now(),'revision':Job.revision+1}
    if status in TERMINAL:values.update(status=status,report=report,completed_at=now(),lease_owner=None,lease_until=None)
    async with async_session_factory() as db:
        result=await db.execute(update(Job).where(Job.id==uuid.UUID(identifier),Job.lease_owner==worker,Job.status=='running').values(**values))
        await db.commit()
        if not result.rowcount:raise InterruptedError('Research stopped or moved to another worker')

async def release(identifier,worker):
    async with async_session_factory() as db:
        await db.execute(update(Job).where(Job.id==uuid.UUID(identifier),Job.lease_owner==worker,Job.status=='running')
            .values(lease_until=now()-timedelta(seconds=1),lease_owner=None))
        await db.execute(update(Job).where(Job.id==uuid.UUID(identifier),Job.lease_owner==worker,Job.status=='cancel_requested')
            .values(status='cancelled',completed_at=now(),lease_owner=None,lease_until=None,revision=Job.revision+1))
        await db.commit()

async def finish_cancelled(identifier,worker,state,activity,report):
    async with async_session_factory() as db:
        await db.execute(update(Job).where(Job.id==uuid.UUID(identifier),Job.lease_owner==worker,Job.status=='cancel_requested')
            .values(status='cancelled',checkpoint=state,activity=activity[-160:],report=report,completed_at=now(),updated_at=now(),lease_owner=None,lease_until=None,revision=Job.revision+1))
        await db.commit()

async def retry(identifier,owner):
    async with async_session_factory() as db:
        await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner, 17))'),{'owner':str(owner)})
        job=await owned(db,identifier,owner,lock=True)
        if job.status in ACTIVE:return view(job)
        if job.status!='failed' or (job.checkpoint or {}).get('retries',0)>=1:raise HTTPException(409,'Create a new plan to run this question again.')
        if job.started_at and (now()-job.started_at).total_seconds()>900:raise HTTPException(409,'This run has expired. Create a new plan; the retrieved evidence is preserved.')
        if await db.scalar(select(func.count()).select_from(Job).where(Job.owner_id==uuid.UUID(owner),Job.status.in_(ACTIVE))):raise HTTPException(409,'Another report is already running in this account.')
        await db.execute(text('SELECT pg_advisory_xact_lock(43831729)'))
        if await db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(ACTIVE)))>=settings.PHARMA_DEEP_QUEUE_LIMIT:raise HTTPException(429,'Deep research is busy. Please retry shortly.',headers={'Retry-After':'30'})
        state=copy.deepcopy(job.checkpoint);state['retries']=state.get('retries',0)+1
        job.checkpoint=state;job.status='queued';job.completed_at=None;job.revision+=1;job.updated_at=now()
        await db.commit();await db.refresh(job);return view(job)
