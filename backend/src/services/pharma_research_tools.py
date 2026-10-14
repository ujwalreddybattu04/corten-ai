"""Read-only Pharma tools. Fixed endpoints, bounded responses and explicit coverage."""
import asyncio
import base64
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal
from src.config.settings import settings
from src.services import pharma_repository
from src.services.pharma_sources import safe_source_url, read_response
from src.services.pharma_updates import clean_text

ToolName = Literal['drug_history','trials','fda','literature','labels','orange_book','official_search']
Scope = Literal['regulatory','safety','companies','commercial','patents','policy']
DOMAINS = {
    'regulatory': ('fda.gov','ema.europa.eu','ec.europa.eu','gov.uk'),
    'safety': ('fda.gov','ema.europa.eu','gov.uk','who.int'),
    'companies': ('bms.com','pfizer.com','novartis.com','astrazeneca.com','amgen.com','biogen.com','lilly.com','roche.com','sanofi.com','gsk.com','jnj.com','novonordisk.com','takeda.com'),
    'commercial': ('sec.gov','cms.gov','nice.org.uk','bms.com','pfizer.com','novartis.com','astrazeneca.com','amgen.com','biogen.com','lilly.com','roche.com','sanofi.com','gsk.com','jnj.com','novonordisk.com','takeda.com'),
    'patents': ('fda.gov','uspto.gov','epo.org','wipo.int','patents.google.com'),
    'policy': ('fda.gov','ema.europa.eu','who.int','cms.gov','nice.org.uk','gov.uk'),
}
TOOL_LABELS = {'drug_history':'Drug identity and archived events','trials':'ClinicalTrials.gov studies',
    'fda':'FDA applications and approval actions','literature':'Scientific publications',
    'labels':'FDA-submitted drug labels','orange_book':'FDA Orange Book patents and exclusivities','official_search':'Official publications'}


class ToolCall(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tool: ToolName
    query: str = Field(min_length=2,max_length=240)
    scope: Scope = 'regulatory'
    search_by: Literal['term','intervention','sponsor'] = 'term'
    phase: Literal['PHASE1','PHASE2','PHASE3','PHASE4'] | None = None
    condition: str | None = Field(default=None,min_length=2,max_length=160)
    compare_with: str | None = Field(default=None,min_length=2,max_length=120)

    @model_validator(mode='after')
    def applicable_scope(self):
        if self.tool!='official_search' and self.scope!='regulatory':raise ValueError('Only official search uses scope')
        if self.tool!='trials' and (self.phase or self.condition or self.compare_with or self.search_by!='term'):raise ValueError('Only trials use registry filters')
        return self

    @field_validator('query','condition','compare_with')
    @classmethod
    def scientific_term(cls, value):
        if value is None:return value
        value=value.strip()
        if len(value)<2 or re.search(r'https?://|[\x00-\x1f]',value,re.I):
            raise ValueError('Use scientific search terms, not links or control characters')
        return value


def finite_json(content):
    def invalid(value):raise ValueError('Non-finite source value')
    result=json.loads(content,parse_constant=invalid)
    if not isinstance(result,dict):raise ValueError('Expected a source object')
    json.dumps(result,allow_nan=False)  # Exponents such as 1e400 also overflow to infinity.
    return result


def row(title,url,kind,facts,excerpt='',date=None,date_meaning=None):
    if not safe_source_url(url):raise ValueError('Invalid public evidence link')
    return {'title':clean_text(title,300),'url':url,'kind':kind,'facts':facts,
        'excerpt':clean_text(excerpt,1200),'date':date,'date_meaning':date_meaning,
        'retrieved_at':datetime.now(timezone.utc).isoformat()}


async def data(client,url,*,params=None,body=None,headers=None,limit=3_000_000):
    async with client.stream('POST' if body is not None else 'GET',url,params=params,json=body,headers=headers) as response:
        if response.status_code==404 and url.startswith('https://api.fda.gov/'):
            error=finite_json(await read_response_allow_not_found(response))
            if error.get('error',{}).get('code')=='NOT_FOUND':return {'results':[]}
            raise ValueError('Invalid FDA error response')
        return finite_json(await read_response(response,limit))


async def read_response_allow_not_found(response):
    content=bytearray()
    async for chunk in response.aiter_bytes():
        content.extend(chunk)
        if len(content)>10000:raise ValueError('Source error response too large')
    return bytes(content)


async def drug_history(call,client):
    drugs=await pharma_repository.search_drugs(call.query)
    if len(drugs)>3:
        return [],'The drug name matched multiple identities. Ask for a more specific ingredient or brand; no identities were merged.'
    items=[]
    for drug in drugs[:3]:
        history=await pharma_repository.drug_timeline(drug['id'],limit=6)
        if not history:continue
        items.append(row(drug['name']+' — verified identity',drug['evidence_url'],'drug_identity',
            {'name':drug['name'],'aliases':history['drug']['aliases']}))
        for item in history['items']:
            items.append(row(item['title'],item['url'],'archived_event',
                {'event':item['event'],'impact':item['impact'],'details':item.get('details',{}),'source_version':item['version']},
                item.get('summary',''),item['date'],item['date_label']))
    return items[:12],'Verified aliases and up to six archived events per matched drug. History begins with recorded observations; missing events do not prove no event occurred.'


async def trials(call,client):
    search='query.id' if re.fullmatch(r'NCT\d{8}',call.query) else 'query.intr' if call.search_by=='intervention' or call.compare_with else 'query.spons' if call.search_by=='sponsor' else 'query.term'
    term=call.query if not call.compare_with else '"'+call.query.replace('"','')+'" AND "'+call.compare_with.replace('"','')+'"'
    params={search:term,'pageSize':12,'format':'json','countTotal':'true','sort':'@relevance' if call.compare_with else 'LastUpdatePostDate:desc'}
    if call.phase:params['filter.advanced']='AREA[Phase]'+call.phase
    condition=call.condition
    if condition and re.search(r'\b(?:MDS|myelodysplas\w*)\b',condition,re.I):condition='myelodysplastic syndromes'
    if condition:params['query.cond']=condition
    result=await data(client,'https://clinicaltrials.gov/api/v2/studies',params=params)
    if not isinstance(result.get('studies'),list):raise ValueError('Invalid trial response')
    rows=[]
    for study in result['studies'][:12]:
        protocol=study.get('protocolSection') or {};identity=protocol.get('identificationModule') or {}
        identifier=identity.get('nctId','')
        if not re.fullmatch(r'NCT\d{8}',identifier):continue
        status=protocol.get('statusModule') or {};design=protocol.get('designModule') or {}
        outcomes=protocol.get('outcomesModule') or {};interventions=protocol.get('armsInterventionsModule') or {}
        groups=interventions.get('armGroups',[])
        facts={'study_id':identifier,'acronym':identity.get('acronym'),'official_title':identity.get('officialTitle'),
            'study_type':design.get('studyType'),'design':design.get('designInfo'),
            'arm_groups':[{'label':g.get('label'),'type':g.get('type'),'intervention_names':g.get('interventionNames',[])} for g in groups[:8]],
            'status':status.get('overallStatus'),'phases':design.get('phases',[]),
            'conditions':(protocol.get('conditionsModule') or {}).get('conditions',[])[:8],
            'interventions':[{'name':i.get('name'),'type':i.get('type'),'other_names':i.get('otherNames',[]),'arm_group_labels':i.get('armGroupLabels',[])} for i in interventions.get('interventions',[])[:8]],
            'sponsor':(protocol.get('sponsorCollaboratorsModule') or {}).get('leadSponsor'),
            'enrollment':design.get('enrollmentInfo'),'primary_outcomes':outcomes.get('primaryOutcomes',[])[:3],
            'primary_completion':status.get('primaryCompletionDateStruct'),'completion':status.get('completionDateStruct'),
            'stop_reason':status.get('whyStopped'),'results_posted':status.get('resultsFirstPostDateStruct'),
            'results_present':True if status.get('resultsFirstPostDateStruct',{}).get('date') or study.get('resultsSection') else study.get('hasResults') if isinstance(study.get('hasResults'),bool) else None}
        date=(status.get('lastUpdatePostDateStruct') or {}).get('date')
        rows.append(row(identity.get('briefTitle',identifier),'https://clinicaltrials.gov/study/'+identifier,'trial_record',facts,
            (protocol.get('descriptionModule') or {}).get('briefSummary',''),date,'Registry update posted'))
    total=result.get('totalCount')
    filters=term+('; '+call.phase.replace('PHASE','Phase ') if call.phase else '')+('; '+condition if condition else '')
    method='joint intervention match; arm groups require verification' if call.compare_with else 'intervention match' if search=='query.intr' else 'study identifier' if search=='query.id' else 'sponsor match' if search=='query.spons' else 'keyword search'
    order='relevance' if call.compare_with else 'last update'
    return rows,f'{filters} ({method}): {total if isinstance(total,int) else "an unknown number of"} registry matches; {len(rows)} retrieved, sorted by {order} (maximum twelve). This is not a complete pipeline. Current status is not a verified transition; posted results are not proof of benefit. Full result tables were not analyzed.'


def fda_term(query):
    value=re.sub(r'[^\w .+/-]',' ',query,flags=re.UNICODE).strip()[:160]
    if not value:raise ValueError('Empty FDA drug term')
    if re.fullmatch(r'(?:ANDA|NDA|BLA)\d{6}',value,re.I):return 'application_number:"'+value.upper()+'"'
    return ' OR '.join(field+':"'+value+'"' for field in ('products.brand_name','products.active_ingredients.name','sponsor_name'))


async def fda(call,client):
    headers={'Authorization':'Basic '+base64.b64encode((settings.OPENFDA_API_KEY+':').encode()).decode()} if settings.OPENFDA_API_KEY else None
    result=await data(client,'https://api.fda.gov/drug/drugsfda.json',params={'search':fda_term(call.query),'limit':5,'sort':'submissions.submission_status_date:desc'},headers=headers)
    if not isinstance(result.get('results'),list):raise ValueError('Invalid FDA response')
    rows=[]
    for application in result['results'][:5]:
        identifier=application.get('application_number','')
        if not re.fullmatch(r'(?:ANDA|NDA|BLA)\d{6}',identifier):continue
        def tentative(s):return s.get('submission_status')=='TA' or 'tentative' in str(s.get('submission_public_notes','')).casefold()
        approved=sorted([s for s in application.get('submissions',[]) if s.get('submission_status')=='AP' and not tentative(s)],key=lambda s:s.get('submission_status_date',''),reverse=True)[:5]
        pending=sorted([s for s in application.get('submissions',[]) if tentative(s)],key=lambda s:s.get('submission_status_date',''),reverse=True)[:5]
        facts={'application':identifier,'sponsor':application.get('sponsor_name'),
            'products':[{'brand':p.get('brand_name'),'ingredients':p.get('active_ingredients'),'form':p.get('dosage_form'),'route':p.get('route')} for p in application.get('products',[])[:6]],
            'approved_submissions':[{'type':s.get('submission_type'),'number':s.get('submission_number'),'date':s.get('submission_status_date'),
                'classification':s.get('submission_class_code_description'),'notes':s.get('submission_public_notes')} for s in approved],
            'tentative_submissions':[{'type':s.get('submission_type'),'number':s.get('submission_number'),'date':s.get('submission_status_date'),
                'classification':s.get('submission_class_code_description'),'notes':s.get('submission_public_notes'),'marketing_authorised':False} for s in pending]}
        rows.append(row(identifier+' — '+str(application.get('sponsor_name','FDA application')),
            'https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo='+identifier[-6:],
            'fda_application',facts))
    return rows,'Up to five matching FDA applications, with up to five most recent approved submissions per application. FDA action dates are not market launch dates; ANDAs do not establish first-generic or exclusivity status.'


async def literature(call,client):
    result=await data(client,'https://www.ebi.ac.uk/europepmc/webservices/rest/search',
        params={'query':call.query,'pageSize':12,'format':'json','resultType':'core'})
    entries=(result.get('resultList') or {}).get('result')
    if not isinstance(entries,list):raise ValueError('Invalid publication response')
    rows=[];seen=set()
    for article in entries[:12]:
        identity=re.sub(r'\W','',str(article.get('title','')).casefold())
        if identity and identity in seen:continue
        identifier=str(article.get('id',''));source=str(article.get('source',''))
        if source=='MED' and identifier.isdigit():url='https://pubmed.ncbi.nlm.nih.gov/'+identifier+'/'
        elif re.fullmatch(r'[A-Za-z0-9._-]{1,100}',identifier) and re.fullmatch(r'[A-Z]{2,8}',source):url='https://europepmc.org/article/'+source+'/'+identifier
        else:continue
        if identity:seen.add(identity)
        abstract=clean_text(article.get('abstractText',''),20000)
        types=(article.get('pubTypeList') or {}).get('pubType',[])
        rows.append(row(article.get('title',identifier),url,'publication',
            {'identifier':identifier,'source':source,'doi':article.get('doi'),'authors':article.get('authorString'),
             'journal':((article.get('journalInfo') or {}).get('journal') or {}).get('title'),
             'publication_types':types,'abstract':abstract[:6000],'abstract_complete':len(abstract)<=6000,
             'evidence_type':'review' if any('review' in str(t).casefold() for t in types) else 'randomized_trial' if any('randomized controlled trial'==str(t).casefold() for t in types) else 'study_design_not_classified'},
            article.get('abstractText',''),article.get('firstPublicationDate'),'Publication date'))
        if len(rows)>=6:break
    return rows,'Up to six Europe PMC publication matches, with bounded abstract excerpts where supplied. Full text and complete methods/results were not reviewed; publication is not regulatory approval.'


async def labels(call,client):
    value=re.sub(r'[^\w .+/-]',' ',call.query,flags=re.UNICODE).strip()[:160]
    if not value:raise ValueError('Empty label term')
    search=' OR '.join(field+':"'+value+'"' for field in ('openfda.brand_name','openfda.generic_name','openfda.substance_name'))
    result=await data(client,'https://api.fda.gov/drug/label.json',params={'search':search,'limit':3,'sort':'effective_time:desc'})
    if not isinstance(result.get('results'),list):raise ValueError('Invalid label response')
    rows=[]
    for label in result['results'][:3]:
        identifier=label.get('set_id','')
        if not re.fullmatch(r'[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}',identifier):continue
        facts={'sections':{},'boxed_warning_present':bool(label.get('boxed_warning'))}
        for name in ('indications_and_usage','boxed_warning','warnings_and_cautions','contraindications'):
            value=label.get(name)
            if not isinstance(value,list):continue
            full=clean_text(' '.join(v for v in value if isinstance(v,str)),100000)
            # Choose representative passages from the entire section, not a prefix presented as complete.
            limit=28000 if name=='indications_and_usage' else 5000
            facts[name]=full if len(full)<=limit else full[:limit//2]+' … [middle omitted] … '+full[-limit//2:]
            facts['sections'][name]={'characters':len(full),'complete':len(full)<=limit}
            if name=='indications_and_usage':
                titles=re.findall(r'(?:^|\s)1(?:\.\d+)?\s+([A-Z][A-Za-z0-9 ,()\-/–]{4,140}?)(?=\s+(?:KEYTRUDA|[A-Z][A-Z]+\s+is|1\.\d)|$)',full)
                facts['indication_headings']=[t for t in dict.fromkeys(titles) if t!='INDICATIONS AND USAGE'][:50]
        facts['label_version']=label.get('version');facts['brand_names']=(label.get('openfda') or {}).get('brand_name',[])
        facts['generic_names']=(label.get('openfda') or {}).get('generic_name',[])
        rows.append(row(', '.join(facts['brand_names']) or 'FDA-submitted label','https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid='+identifier,
            'drug_label',facts,date=label.get('effective_time'),date_meaning='Label effective time as recorded'))
    return rows,'Up to three FDA-submitted labeling records. Section completeness and full character counts are explicit; omitted text must not be described as a complete list of main indications. A missing boxed-warning section is not a boxed warning. Read the linked full label; label availability alone does not establish FDA approval or suitability for an individual patient.'


async def orange_book(call,client):
    value=re.sub(r'[^\w .+/-]',' ',call.query,flags=re.UNICODE).strip()[:160]
    if not value:raise ValueError('Empty Orange Book term')
    search=' OR '.join(field+':"'+value+'"' for field in ('products.active_ingredients.name','products.brand_name'))
    if re.fullmatch(r'(?:NDA|ANDA)?\d{6}',value,re.I):search='products.application_number:'+value[-6:]
    found=await asyncio.gather(*(data(client,'https://api.fda.gov/drug/orangebook.json',params={'search':'('+search+') AND products.application_type:'+kind,'limit':6}) for kind in ('N','A')))
    if any(not isinstance(result.get('results'),list) for result in found):raise ValueError('Invalid Orange Book response')
    result={'results':[r for part in found for r in part['results']],'meta':found[0].get('meta',{})}
    rows=[]
    for entry in result['results'][:12]:
        products=entry.get('products',[])
        if isinstance(products,dict):products=[products]
        products=[p for p in products if isinstance(p,dict)]
        if not products:continue
        application=str(products[0].get('application_number',''))
        if not re.fullmatch(r'\d{6}',application):continue
        facts={'products':products,'product_number':entry.get('product_number'),'approval_date':entry.get('approval_date'),
            'patents':entry.get('patents',[]),'exclusivity':entry.get('exclusivity',[]),
            'dataset_updated':result.get('meta',{}).get('last_updated'),
            'launch_date_established':False}
        rows.append(row('Orange Book application '+application,
            'https://www.accessdata.fda.gov/scripts/cder/ob/results_product.cfm?Appl_Type='+str(products[0].get('application_type','N'))+'&Appl_No='+application,
            'orange_book',facts))
    totals=[part.get('meta',{}).get('results',{}).get('total',0) for part in found]
    total=sum(v for v in totals if isinstance(v,int))
    return rows,f'FDA Orange Book monthly data: {total} matching records, up to twelve retrieved, with listed patents and regulatory exclusivities. Listing and expiry do not resolve patent validity, litigation, settlements, tentative approval or actual generic launch; no launch date is established.'


async def official_search(call,client):
    if not settings.TAVILY_API_KEY:raise RuntimeError('Public search is not configured')
    domains=DOMAINS[call.scope]
    result=await data(client,'https://api.tavily.com/search',body={'query':call.query,'search_depth':'basic','max_results':5,
        'include_domains':list(domains),'include_answer':False,'include_raw_content':False,'include_images':False},
        headers={'Authorization':'Bearer '+settings.TAVILY_API_KEY})
    if not isinstance(result.get('results'),list):raise ValueError('Invalid indexed search response')
    rows=[]
    for item in result['results'][:5]:
        url=safe_source_url(item.get('url'),domains)
        if url:rows.append(row(item.get('title','Official publication'),url,'indexed_'+call.scope,{},item.get('content',''),
            item.get('published_date'),'Indexed publication date; may be unavailable'))
    return rows,'Domain-restricted public search excerpts, not a full-document review. Publisher statements remain attributed claims. No licensed sales/market-share feed is connected; patent listings alone do not establish enforceability, freedom to operate or launch timing.'


EXECUTORS={'drug_history':drug_history,'trials':trials,'fda':fda,'literature':literature,'labels':labels,'orange_book':orange_book,'official_search':official_search}


async def execute(call):
    async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),follow_redirects=False) as client:
        async with asyncio.timeout(20):rows,coverage=await EXECUTORS[call.tool](call,client)
    # Bound the entire result, not only each provider's response.
    kept=[];size=0
    for item in rows:
        length=len(json.dumps(item,ensure_ascii=False,allow_nan=False).encode())
        if length>42000 or size+length>88000:continue
        kept.append(item);size+=length
    if len(kept)<len(rows):coverage+=' Some records exceeded the evidence size limit and were omitted.'
    return {'tool':call.tool,'label':TOOL_LABELS[call.tool],'status':'available' if kept else 'empty','records':kept,'coverage':coverage}
