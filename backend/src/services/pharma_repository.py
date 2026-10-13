"""Immutable public evidence, idempotent events and archived drug timelines."""
import copy
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import and_, or_, select, delete
from sqlalchemy.dialects.postgresql import insert
from src.db.session import async_session_factory
from src.models.pharma import PharmaDocument, PharmaSnapshot, PharmaEvent, PharmaSourceState, PharmaDrug, PharmaDrugAlias, PharmaEventDrug
from src.services.pharma_catalog import SOURCE_CATALOG, VERIFIED_IDENTITIES, AliasMatcher, drug_identity, normalize_name, unique_aliases, mentioned_drugs
from src.services.pharma_events import RULE_VERSION, digest, impact, trial_events


async def register_drug(db,name,ingredients,aliases,url):
    identity=drug_identity(ingredients)
    if not identity or not name or len(name)>240:
        return None
    canonical=" + ".join(ingredients)[:240]
    await db.execute(insert(PharmaDrug).values(id=identity,name=canonical,ingredients=ingredients,evidence_url=url).on_conflict_do_nothing())
    for alias in set([name,canonical,*aliases]):
        if isinstance(alias,str) and alias.strip() and len(alias)<=240:
            await db.execute(insert(PharmaDrugAlias).values(alias=normalize_name(alias),drug_id=identity,display_name=alias,
                evidence_url=url).on_conflict_do_nothing())
    return identity


async def seed_identities(db):
    for drug in VERIFIED_IDENTITIES:
        await register_drug(db,drug["name"],drug["ingredients"],drug["aliases"],drug["evidence_url"])


async def store_record(db,item,raw,events=None,now=None):
    now=now or datetime.now(timezone.utc)
    version=digest(raw)
    document_id=item["id"]
    await db.execute(insert(PharmaDocument).values(id=document_id,source=item["source"],latest_version=version,
        item=item,event_date=date.fromisoformat(item["date"]),observed_at=now).on_conflict_do_nothing())
    document=await db.scalar(select(PharmaDocument).where(PharmaDocument.id==document_id).with_for_update())
    existing=await db.get(PharmaSnapshot,(document_id,version))
    if existing and document.latest_version==version:
        document.observed_at=now
        return 0
    previous=await db.get(PharmaSnapshot,(document_id,document.latest_version))
    if previous and item["source"]=="trials" and item["date"]<previous.item["date"]:
        # An older provider page must not rewind an already newer registry snapshot.
        return 0
    detected=trial_events(raw,previous.raw if previous else None) if item["source"]=="trials" else events
    if not detected:
        detected=[{"kind":"record_observed","label":"Source record","date":item["date"],
            "date_label":item["date_label"],"changes":[],"reason":None,"baseline":previous is None}]
    if not existing:
        snapshot=PharmaSnapshot(document_id=document_id,version=version,raw=raw,item=item,recorded_at=now)
        db.add(snapshot);await db.flush()
    added=0
    for event in detected:
        rating=impact(event,item)
        # Known posting milestones are single events; repeat observations do not recreate them.
        anchor = [document_id,event["kind"],event["date"],event.get("changes") or []]
        if event["kind"] in {"record_updated","record_observed"}:anchor.append(version)
        event_id=digest(anchor)
        public={**copy.deepcopy(item),"id":"event:"+event_id,"document_id":document_id,"raw_version":version,
            "date":event["date"],"date_label":event["date_label"],"event":{**event,"impact":rating},"impact":rating}
        values=dict(id=event_id,document_id=document_id,version=version,
            event_date=date.fromisoformat(event["date"]),kind=event["kind"],impact=rating["rating"],evidence={"item":public})
        statement=insert(PharmaEvent).values(**values)
        if item["source"]!="trials":
            # A corrected source article/action gets a new canonical version, not a duplicate publication.
            statement=statement.on_conflict_do_update(index_elements=[PharmaEvent.id],set_={
                "version":version,"evidence":values["evidence"],"impact":rating["rating"]})
        else:
            statement=statement.on_conflict_do_nothing()
        inserted=await db.execute(statement.returning(PharmaEvent.id))
        added+=int(inserted.scalar_one_or_none() is not None)
    document.latest_version=version;document.item=item;document.event_date=date.fromisoformat(item["date"]);document.observed_at=now
    details=item.get("details") or {}
    ingredients=details.get("ingredients") or []
    if ingredients:
        await register_drug(db," + ".join(ingredients)[:240],ingredients,details.get("brands") or [],item["url"])
    return added


async def link_drugs(db):
    aliases=unique_aliases((await db.execute(select(PharmaDrugAlias.alias,PharmaDrugAlias.drug_id))).all())
    signature=digest([aliases,"literal-matcher-1"]);matcher=AliasMatcher(aliases)
    state=await db.get(PharmaSourceState,"drug_links")
    since=state.checked_at if state and state.metadata_json.get("aliases_version")==signature else None
    now=datetime.now(timezone.utc)
    # Ingest batches are bounded; historical public records acquire newly verified aliases too.
    marker=""
    while True:
        query=select(PharmaEvent).join(PharmaDocument,PharmaDocument.id==PharmaEvent.document_id).where(PharmaEvent.id>marker)
        if since:query=query.where(PharmaDocument.observed_at>=since)
        batch=(await db.scalars(query.order_by(PharmaEvent.id).limit(200))).all()
        if not batch:break
        for event in batch:
            drugs=mentioned_drugs(event.evidence["item"],aliases,matcher)
            # A later ambiguous alias or corrected article must remove obsolete associations.
            await db.execute(delete(PharmaEventDrug).where(PharmaEventDrug.event_id==event.id,
                PharmaEventDrug.drug_id.not_in(drugs)))
            for drug in drugs:
                await db.execute(insert(PharmaEventDrug).values(event_id=event.id,drug_id=drug).on_conflict_do_nothing())
        marker=batch[-1].id
    await db.execute(insert(PharmaSourceState).values(id="drug_links",status="available",checked_at=now,attempted_at=now,
        metadata_json={"aliases_version":signature}).on_conflict_do_update(index_elements=[PharmaSourceState.id],
        set_={"checked_at":now,"attempted_at":now,"metadata_json":{"aliases_version":signature}}))


async def _public_item(db,event):
    item=copy.deepcopy(event.evidence["item"])
    rows=(await db.execute(select(PharmaDrug).join(PharmaEventDrug,PharmaEventDrug.drug_id==PharmaDrug.id)
        .where(PharmaEventDrug.event_id==event.id).order_by(PharmaDrug.name).limit(8))).scalars().all()
    item["drugs"]=[{"id":d.id,"name":d.name,"evidence_url":d.evidence_url} for d in rows]
    item["version"]=digest([event.id,event.version,RULE_VERSION,item["drugs"]])
    return item


def source_info(source,state,now):
    checked=state.checked_at if state else None
    healthy=state and state.status in ("available","empty")
    retained=checked and now-checked<=timedelta(hours=24)
    status=state.status if healthy and retained else "stale" if retained else "unavailable" if healthy else state.status if state else "unavailable"
    metadata=state.metadata_json if state else {}
    return {"id":source,**SOURCE_CATALOG[source],"status":status,
        "checked_at":checked.isoformat() if checked else None,"source_updated_at":metadata.get("source_updated_at"),
        "limited":bool(metadata.get("limited")),"coverage":{k:v for k,v in metadata.items()
            if k in ("coverage","method","records_received","undated_excluded","rejected_records","monitored_domains")}}


def matches_topic(item,topic):
    if topic=="all" or item["source"]=="fda":return True
    vocabulary={"oncology":("cancer","oncology","tumor","tumour","leukemia","lymphoma","myeloma"),
        "rare-disease":("rare disease","orphan","thalassemia","hemophilia","haemophilia"),
        "immunology":("immune","immunology","arthritis","lupus","psoriasis"),
        "cns":("neurolog","alzheimer","parkinson","nervous system","depression","epilepsy"),
        "cardiometabolic":("cardiovascular","diabetes","metabolic","obesity","heart","cardiac")}
    text=" ".join([item.get("title",""),item.get("summary",""),str(item.get("details") or {})]).casefold()
    return any(word in text for word in vocabulary[topic])


async def get_feed(topic,days):
    now=datetime.now(timezone.utc);today=now.date();since=today-timedelta(days=days-1)
    async with async_session_factory() as db:
        states={s.id:s for s in (await db.scalars(select(PharmaSourceState))).all()}
        sources=[]
        for name in SOURCE_CATALOG:
            source=source_info(name,states.get(name),now)
            events=(await db.scalars(select(PharmaEvent).join(PharmaDocument,PharmaDocument.id==PharmaEvent.document_id)
                .where(PharmaDocument.source==name,PharmaEvent.event_date>=since,PharmaEvent.event_date<=today)
                .order_by(PharmaEvent.event_date.desc(),PharmaEvent.id).limit(500))).all()
            usable=source["status"] in ("available","empty","stale")
            selected=[event for event in events if matches_topic(event.evidence["item"],topic)]
            source["limited"]=source["limited"] or len(selected)>20 or len(events)==500
            source["items"]=[await _public_item(db,event) for event in selected[:20]] if usable else []
            sources.append(source)
        items=sorted([i for s in sources for i in s["items"]],key=lambda i:(i["date"],i["id"]),reverse=True)
        successful=any(s["status"] in ("available","empty") for s in sources)
        return {"schema_version":2,"topic":topic,"days":days,"since":since.isoformat(),"until":today.isoformat(),
            "checked_at":now.isoformat(),"next_check_at":(now+timedelta(minutes=15)).isoformat(),"items":items,"sources":sources,
            "status":"available" if successful else "stale" if items else "unavailable",
            "partial":any(s["status"] not in ("available","empty") for s in sources),"limit_per_source":20}


async def get_record(identifier):
    if len(identifier)>240:return None
    async with async_session_factory() as db:
        if identifier.startswith("event:"):
            event=await db.get(PharmaEvent,identifier[6:])
        else:
            event=await db.scalar(select(PharmaEvent).where(PharmaEvent.document_id==identifier)
                .order_by(PharmaEvent.event_date.desc(),PharmaEvent.id).limit(1))
        if not event:return None
        item=await _public_item(db,event)
        document=await db.get(PharmaDocument,event.document_id)
        state=await db.get(PharmaSourceState,document.source)
        source=source_info(document.source,state,datetime.now(timezone.utc))
        # Archive availability never renews the observation time of its immutable snapshot.
        snapshot=await db.get(PharmaSnapshot,(event.document_id,event.version))
        source["record_observed_at"]=snapshot.recorded_at.isoformat()
        return {"item":item,"source":source,"history_started_at":document.first_observed_at.isoformat()}


async def get_evidence(item):
    async with async_session_factory() as db:
        snapshot=await db.get(PharmaSnapshot,(item["document_id"],item["raw_version"]))
        if not snapshot:raise ValueError("Source version unavailable")
        return copy.deepcopy(snapshot.raw)


async def search_drugs(query):
    async with async_session_factory() as db:
        needle="%"+normalize_name(query).replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
        rows=(await db.scalars(select(PharmaDrug).join(PharmaDrugAlias,PharmaDrugAlias.drug_id==PharmaDrug.id)
            .where(PharmaDrugAlias.alias.ilike(needle,escape="\\")).distinct().order_by(PharmaDrug.name).limit(20))).all()
        return [{"id":d.id,"name":d.name,"evidence_url":d.evidence_url} for d in rows]


async def drug_timeline(identifier,limit=30,before=None):
    async with async_session_factory() as db:
        drug=await db.get(PharmaDrug,identifier)
        if not drug:return None
        query=select(PharmaEvent).join(PharmaEventDrug,PharmaEventDrug.event_id==PharmaEvent.id).where(PharmaEventDrug.drug_id==identifier)
        if before:
            when,marker=before
            query=query.where(or_(PharmaEvent.event_date<when,and_(PharmaEvent.event_date==when,PharmaEvent.id>marker)))
        events=(await db.scalars(query.order_by(PharmaEvent.event_date.desc(),PharmaEvent.id).limit(limit+1))).all()
        aliases=(await db.scalars(select(PharmaDrugAlias.display_name).where(PharmaDrugAlias.drug_id==identifier).order_by(PharmaDrugAlias.display_name))).all()
        visible=events[:limit]
        return {"drug":{"id":drug.id,"name":drug.name,"aliases":aliases,"evidence_url":drug.evidence_url},
            "items":[await _public_item(db,event) for event in visible],
            "next":(visible[-1].event_date.isoformat(),visible[-1].id) if len(events)>limit else None}
