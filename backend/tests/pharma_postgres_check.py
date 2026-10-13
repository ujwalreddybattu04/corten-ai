"""Run only against a disposable corten_pharma_check_* database after migrations.

python -m tests.pharma_postgres_check is intentionally separate from unit tests.
"""
import asyncio
import copy
import json
from sqlalchemy import select,func
from src.config.settings import settings
from src.db.session import async_session_factory,engine
from src.models.pharma import PharmaSnapshot,PharmaEvent,PharmaSharedBrief
from src.services.pharma_repository import store_record,seed_identities,link_drugs,get_record,drug_timeline
from src.services.pharma_catalog import drug_identity
from src.services.pharma_briefs import shared_brief,_generate


async def main():
    assert settings.DATABASE_URL.rsplit('/',1)[-1].startswith('corten_pharma_check_'),"Disposable database required"
    raw={'protocolSection':{'identificationModule':{'nctId':'NCT12345678'},
        'statusModule':{'overallStatus':'RECRUITING','lastUpdatePostDateStruct':{'date':'2026-10-14'},'studyFirstPostDateStruct':{'date':'2020-01-01'}},
        'designModule':{'phases':['PHASE3']},'sponsorCollaboratorsModule':{'leadSponsor':{'class':'INDUSTRY'}}}}
    item={'id':'trial:NCT12345678','title':'Reblozyl study','summary':'Existing study','source':'trials','date':'2026-10-14','date_label':'Record updated',
        'organization':'Synthetic sponsor','url':'https://clinicaltrials.gov/study/NCT12345678','details':{'study_id':'NCT12345678','interventions':['Reblozyl']},
        'evidence':{'phases':['PHASE3'],'sponsor_class':'INDUSTRY'},'tags':[],'category':'Clinical trials'}
    async with async_session_factory() as db:
        await seed_identities(db)
        assert await store_record(db,item,raw)==2
        assert await store_record(db,item,raw)==0
        stopped=copy.deepcopy(raw);stopped['protocolSection']['statusModule'].update(overallStatus='TERMINATED',whyStopped='Enrollment target could not be met.')
        assert await store_record(db,item,stopped)==1
        # A same-date source correction can legitimately return to an earlier content version.
        assert await store_record(db,item,raw)==1
        await link_drugs(db);await db.commit()
        assert await db.scalar(select(func.count()).select_from(PharmaSnapshot))==2
        assert await db.scalar(select(func.count()).select_from(PharmaEvent))==4
    timeline=await drug_timeline(drug_identity(['luspatercept']),limit=1)
    assert timeline and len(timeline['items'])==1 and timeline['next']
    next_page=await drug_timeline(timeline['drug']['id'],limit=1,before=(__import__('datetime').date.fromisoformat(timeline['next'][0]),timeline['next'][1]))
    assert next_page['items'][0]['id']!=timeline['items'][0]['id']
    row=await get_record(timeline['items'][0]['id']);assert row and row['item']['version']
    chosen=row['item'];calls=0
    async def generate():
        nonlocal calls
        calls+=1;await asyncio.sleep(.4)
        return {'text':'Source-grounded synthetic answer','model':'amazon.nova-pro-v1:0','usage':{'inputTokens':10,'outputTokens':5}}
    # Independent worker leases (not just the in-process task dictionary).
    results=await asyncio.gather(*[_generate(chosen,'amazon.nova-pro-v1:0',generate) for _ in range(6)])
    assert calls==1 and len(results)==6
    cached=await shared_brief(chosen,'amazon.nova-pro-v1:0',generate);assert cached['shared'] and calls==1
    # A disconnected reader leaves the source-only work running, with no private payload.
    other={**chosen,'version':'a'*64}
    reader=asyncio.create_task(shared_brief(other,'amazon.nova-pro-v1:0',generate));await asyncio.sleep(.1);reader.cancel()
    try:await reader
    except asyncio.CancelledError:pass
    await asyncio.sleep(.6)
    assert (await shared_brief(other,'amazon.nova-pro-v1:0',generate))['shared'] and calls==2
    async with async_session_factory() as db:
        briefs=(await db.scalars(select(PharmaSharedBrief))).all()
        assert len(briefs)==2 and all(b.status=='ready' and b.owner is None for b in briefs)
    await engine.dispose()
    print(json.dumps({'snapshots':2,'real_events':4,'source_reversion_preserved':True,'multi_worker_single_generation':True,'cancelled_reader_cache':True,'archive_and_cursor':True}))

if __name__=='__main__':asyncio.run(main())
