"""Small database-leased worker; jobs survive browser disconnects and process restarts."""
import asyncio,copy,logging,uuid
from src.config.settings import settings
from src.services import pharma_deep_store as store
from src.services.pharma_deep_engine import DeepResearch
from src.services.pharma_deep_evidence import coverage
from src.services.pharma_deep_report import build_report
logger=logging.getLogger(__name__)

async def run_job(job,worker):
    async def publish(state,activity,stage):await store.save(job['id'],worker,state,activity,stage)
    research=DeepResearch(job,publish)
    task=asyncio.create_task(research.run())
    async def watch():
        while not task.done():
            await asyncio.sleep(10)
            if not await store.heartbeat(job['id'],worker):task.cancel();return
    heartbeat=asyncio.create_task(watch())
    try:
        report,status=await task
        await store.save(job['id'],worker,research.state,research.activity,'deliver',report=report,status=status)
    except (asyncio.CancelledError,InterruptedError):
        task.cancel();await asyncio.gather(task,return_exceptions=True)
        state=copy.deepcopy(research.state)
        for section in state['sections']:section['claims']=[]
        state['coverage']=coverage(state,research.plan.topics);state['limits'].append('Research was stopped before delivery. Only saved source evidence is shown.')
        await store.finish_cancelled(job['id'],worker,state,research.activity,build_report(job['query'],research.plan,state))
        if asyncio.current_task().cancelling():raise
    except Exception as exc:
        logger.warning('Pharma Deep research failed (%s)',type(exc).__name__)
        state=research.state
        state['last_error']='Research was interrupted. Your plan and retrieved evidence are saved. You can retry this report once.'
        research.activity.append({'id':len(research.activity)+1,'stage':research.stage,'title':'Research interrupted','detail':state['last_error'],'status':'failed','round':state['round'],'at':store.now().isoformat()})
        try:await store.save(job['id'],worker,state,research.activity,research.stage,status='failed')
        except InterruptedError:pass
    finally:
        heartbeat.cancel();await asyncio.gather(heartbeat,return_exceptions=True)
        await store.release(job['id'],worker)

async def work():
    worker=str(uuid.uuid4())
    while True:
        try:
            job=await store.claim(worker)
            if job:await run_job(job,worker)
            else:await asyncio.sleep(2)
        except asyncio.CancelledError:raise
        except Exception as exc:
            logger.warning('Pharma research worker waiting (%s)',type(exc).__name__);await asyncio.sleep(10)

def start_worker():return asyncio.create_task(work(),name='pharma-deep-research')
