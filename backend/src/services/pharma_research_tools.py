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
from src.services.pharma_updates import clean_text, iso_date, tentative_submission

ToolName = Literal['drug_history','trials','fda','literature','labels','orange_book','recalls','official_search']
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
    'labels':'FDA-submitted drug labels','orange_book':'FDA Orange Book patents and exclusivities','recalls':'FDA drug recall reports',
    'official_search':'Official publications'}
FILLER=re.compile(r'\b(?:fda|recent(?:ly)?|latest|new|approvals?|approved|actions?|labels?|label+ing|patents?|exclusivit(?:y|ies)|recalls?|safety|alerts?|'
    r'drugs?|medicines?|generics?|brand(?:ed)?|the|of|for|and|on|in|current|history|information|status|data|records?|applications?|products?|us|usa)\b',re.I)
# Broad therapy areas expand to registry condition terms; specific diseases are searched as written.
THERAPY_AREAS=[
    ('cardiovascular',r'\bcardio\w*|\bcardiac\b|\bheart\b|\bcv\b',['cardiovascular diseases','heart failure','hypertension','atherosclerosis','hypercholesterolemia','dyslipidemias','atrial fibrillation','myocardial infarction','coronary artery disease','cardiomyopathy','stroke']),
    ('obesity',r'\bobes\w*|\bweight management\b',['obesity','overweight']),
    ('diabetes',r'\bdiabet\w*',['diabetes mellitus']),
    ('oncology',r'\boncolog\w*|\bcancers?\b|\btumou?rs?\b|\bcarcinomas?\b',['cancer','neoplasms','lymphoma','leukemia','multiple myeloma']),
    ('hematology',r'\bhae?matolog\w*',['anemia','hemophilia','sickle cell disease','thalassemia','myelodysplastic syndromes','thrombocytopenia']),
    ('immunology',r'\bimmunolog\w*|\binflammat\w*|\bautoimmun\w*|\bi&i\b',['rheumatoid arthritis','psoriasis','psoriatic arthritis','atopic dermatitis','lupus','ulcerative colitis','crohn disease','ankylosing spondylitis']),
    ('neuroscience',r'\bneuro\w*|\bcns\b',['alzheimer disease','parkinson disease','multiple sclerosis','epilepsy','migraine','amyotrophic lateral sclerosis']),
    ('psychiatry',r'\bpsychiatr\w*|\bmental health\b',['depressive disorder','schizophrenia','bipolar disorder','anxiety disorders']),
    ('respiratory',r'\brespirator\w*|\bpulmonar\w*',['asthma','chronic obstructive pulmonary disease','idiopathic pulmonary fibrosis','bronchiectasis']),
    ('infectious disease',r'\binfecti\w*|\bvaccines?\b|\bantivir\w*|\bantibiotic\w*',['infections','vaccines','hiv','hepatitis b','influenza','covid-19','respiratory syncytial virus']),
    ('renal',r'\brenal\b|\bkidney\b|\bnephrolog\w*',['chronic kidney disease','kidney diseases','iga nephropathy','glomerulonephritis']),
    ('liver',r'\bliver\b|\bhepatolog\w*|\bmash\b|\bnash\b',['liver diseases','non-alcoholic steatohepatitis','cirrhosis']),
    ('dermatology',r'\bdermatolog\w*',['atopic dermatitis','psoriasis','hidradenitis suppurativa','vitiligo','alopecia areata']),
    ('ophthalmology',r'\bophthalm\w*|\bretina\w*',['macular degeneration','diabetic retinopathy','glaucoma','uveitis']),
    ('rare disease',r'\brare diseases?\b|\borphan\b',['rare diseases']),
]


def therapy_area(text):
    """(area label, registry condition expression) for a broad therapy-area phrase, else None."""
    if not text:return None
    for label,pattern,terms in THERAPY_AREAS:
        if re.search(pattern,text,re.I):
            return label,' OR '.join('"'+t+'"' if ' ' in t else t for t in terms)
    return None


def drug_terms(query):
    """Exact product terms from planner wording such as 'Mounjaro (tirzepatide)' or 'Mounjaro recent approvals'."""
    def clean(value):
        value=re.sub(r'[^\w .+/-]',' ',value,flags=re.UNICODE)
        return re.sub(r'\s+',' ',FILLER.sub(' ',value)).strip(' .-/')[:120]
    inside=re.findall(r'\(([^()]{2,80})\)',query)
    terms=[clean(part) for part in [re.sub(r'\([^()]*\)',' ',query),*inside]]
    terms=[t for t in terms if len(t)>=2]
    for value in list(terms):
        if ' ' in value:terms.extend(t for t in value.split() if len(t)>=4)
    return list(dict.fromkeys(terms))[:6]


async def openfda_first(client,url,fields,terms,params,headers=None,suffix=''):
    """Search the full product phrase first; only if FDA has no match, try its separate brand/ingredient words."""
    if not terms:raise ValueError('Empty drug term')
    attempts=[terms[:1]]+([terms[1:]] if len(terms)>1 else [])
    for group in attempts:
        search='('+' OR '.join(field+':"'+term.replace('"','')+'"' for term in group for field in fields)+')'+suffix
        result=await data(client,url,params={**params,'search':search},headers=headers)
        if not isinstance(result.get('results'),list):raise ValueError('Invalid FDA response')
        if result['results']:return result,group
    return result,attempts[-1]


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


def compact(value):
    if isinstance(value,dict):return {k:compact(v) for k,v in value.items() if v not in (None,'',[],{})}
    if isinstance(value,list):return [compact(v) for v in value]
    return value


def timing(value,today):
    """Chronology computed in code so a model never decides whether a registry date has passed."""
    if not isinstance(value,dict) or not value.get('date'):return None
    when=str(value['date']);passed=when<today[:len(when)]
    if value.get('type')=='ESTIMATED':
        return when+': estimated date has already passed; completion is not confirmed by this record' if passed else when+': estimated, still upcoming'
    if value.get('type')=='ACTUAL':return when+': actual, already occurred'
    return when+(': date has passed' if passed else ': upcoming')


def primary_results(study):
    """Posted primary-outcome values and analyses exactly as the registry reports them."""
    measures=((study.get('resultsSection') or {}).get('outcomeMeasuresModule') or {}).get('outcomeMeasures') or []
    output=[]
    for measure in measures:
        if measure.get('type')!='PRIMARY':continue
        groups={g.get('id'):clean_text(g.get('title'),120) for g in measure.get('groups') or []}
        values=[]
        for category_class in (measure.get('classes') or [])[:3]:
            for category in (category_class.get('categories') or [])[:3]:
                for item in (category.get('measurements') or [])[:6]:
                    values.append({'group':groups.get(item.get('groupId'),item.get('groupId')),'value':item.get('value'),'spread':item.get('spread'),
                        'lower':item.get('lowerLimit'),'upper':item.get('upperLimit'),'class':clean_text(category_class.get('title'),80) or None,
                        'category':clean_text(category.get('title'),80) or None})
        analyses=[{'groups':[groups.get(g,g) for g in a.get('groupIds') or []],'parameter':a.get('paramType'),'estimate':a.get('paramValue'),
            'ci_percent':a.get('ciPctValue'),'ci_lower':a.get('ciLowerLimit'),'ci_upper':a.get('ciUpperLimit'),'p_value':a.get('pValue'),
            'test':a.get('nonInferiorityType'),'method':a.get('statisticalMethod')} for a in (measure.get('analyses') or [])[:4]]
        output.append(compact({'measure':clean_text(measure.get('title'),240),'time_frame':clean_text(measure.get('timeFrame'),160),
            'parameter':measure.get('paramType'),'dispersion':measure.get('dispersionType'),'unit':clean_text(measure.get('unitOfMeasure'),80),
            'values':values[:12],'analyses':analyses}))
        if len(output)>=2:break
    return output


def comparison_design(facts,first_terms,second_terms):
    """Direct comparison only when separate registry arms give each drug without the other (background therapy ignored)."""
    interventions=facts.get('interventions') or []
    def names(i):return [str(i.get('name') or ''),*[str(v) for v in i.get('other_names') or []]]
    def active(i):return not re.search(r'\bplacebo|\bsham\b|\bvehicle\b',' '.join(names(i)),re.I)
    def matches(i,terms):
        text=' | '.join(names(i)).casefold()
        return any(re.search(r'(?<![a-z0-9])'+re.escape(t.casefold())+r'(?![a-z0-9])',text) for t in terms if t)
    arms=[]
    for group in facts.get('arm_groups') or []:
        members={index for index,i in enumerate(interventions) if group.get('label') in (i.get('arm_group_labels') or [])}
        for name in group.get('intervention_names') or []:
            bare=re.sub(r'^[A-Za-z /]+:\s*','',str(name)).casefold()
            members|={index for index,i in enumerate(interventions) if str(i.get('name') or '').casefold()==bare}
        arms.append((group.get('label'),{m for m in members if active(interventions[m])}))
    if not arms or not interventions:return {'direct_comparison':None,'basis':'Registry arm assignments are not listed'}
    common=set.intersection(*(m for _,m in arms)) if len(arms)>1 else set()
    background={m for m in common if not matches(interventions[m],first_terms) and not matches(interventions[m],second_terms)}
    def alone(members,terms,other):
        core=members-background
        return bool(core) and all(matches(interventions[m],terms) for m in core) and not any(matches(interventions[m],other) for m in core)
    first=[label for label,m in arms if alone(m,first_terms,second_terms)]
    second=[label for label,m in arms if alone(m,second_terms,first_terms)]
    direct=bool(first and second)
    return compact({'direct_comparison':direct,'first_drug_arms':first[:4],'second_drug_arms':second[:4],
        'basis':'Separate registry arms give each drug without the other' if direct else 'No pair of registry arms gives each drug alone; combination, add-on or single-drug designs are not direct comparisons'})


_INGREDIENTS={}


async def ingredient_names(client,term):
    """Brand-to-ingredient names from FDA product records, so 'Dupixent' also matches 'dupilumab' arms."""
    key=term.casefold()
    if key in _INGREDIENTS:return _INGREDIENTS[key]
    names={term}
    try:
        result=await data(client,'https://api.fda.gov/drug/drugsfda.json',params={'search':'products.brand_name:"'+term.replace('"','')+'"','limit':3})
        for application in result.get('results',[])[:3]:
            for product in application.get('products',[])[:6]:
                for ingredient in product.get('active_ingredients',[])[:4]:
                    if isinstance(ingredient.get('name'),str):names.add(ingredient['name'].split()[0])
    except (httpx.HTTPError,ValueError):pass
    if len(_INGREDIENTS)<256:_INGREDIENTS[key]=names
    return names


async def trials(call,client):
    search='query.id' if re.fullmatch(r'NCT\d{8}',call.query) else 'query.intr' if call.search_by=='intervention' or call.compare_with else 'query.spons' if call.search_by=='sponsor' else 'query.term'
    term=call.query if not call.compare_with else '"'+call.query.replace('"','')+'" AND "'+call.compare_with.replace('"','')+'"'
    params={search:term,'pageSize':12,'format':'json','countTotal':'true','sort':'@relevance' if call.compare_with else 'LastUpdatePostDate:desc'}
    filters=['AREA[Phase]'+call.phase] if call.phase else []
    # A company pipeline means interventional development, not observational chart reviews.
    if call.search_by=='sponsor':filters.append('AREA[StudyType]INTERVENTIONAL')
    if filters:params['filter.advanced']=' AND '.join(filters)
    condition=call.condition;area=None
    if condition and re.search(r'\b(?:MDS|myelodysplas\w*)\b',condition,re.I):condition='myelodysplastic syndromes'
    elif condition and len(condition.split())<=3:
        area=therapy_area(condition)
        if area and not re.search(r'\b(?:failure|fibrillation|infarction|hypertension|sclerosis|arthritis|dermatitis|psoriasis|colitis|asthma|epilepsy|migraine|anemia|lymphoma|leukemia|myeloma)\b',condition,re.I):
            condition=area[1]
        else:area=None
    if condition:params['query.cond']=condition
    result=await data(client,'https://clinicaltrials.gov/api/v2/studies',params=params,limit=6_000_000)
    if not isinstance(result.get('studies'),list):raise ValueError('Invalid trial response')
    today=datetime.now(timezone.utc).date().isoformat()
    first_terms=second_terms=None
    if call.compare_with and result['studies']:
        first_terms,second_terms=await asyncio.gather(ingredient_names(client,call.query),ingredient_names(client,call.compare_with))
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
        chronology=compact({'today':today,'primary_completion':timing(facts['primary_completion'],today),'study_completion':timing(facts['completion'],today)})
        if len(chronology)>1:facts['date_timing']=chronology
        results=primary_results(study)
        if results:facts['primary_results']=results
        if call.compare_with:
            facts['comparison_design']=comparison_design(facts,first_terms,second_terms)
            # Observational cohorts can also have one "arm" per drug; only randomized interventional studies are head-to-head trials.
            facts['comparison_design']['randomized_trial']=design.get('studyType')=='INTERVENTIONAL' and (design.get('designInfo') or {}).get('allocation')=='RANDOMIZED'
        date=(status.get('lastUpdatePostDateStruct') or {}).get('date')
        rows.append(row(identity.get('briefTitle',identifier),'https://clinicaltrials.gov/study/'+identifier,'trial_record',facts,
            (protocol.get('descriptionModule') or {}).get('briefSummary',''),date,'Registry update posted'))
    if call.compare_with:
        # Randomized head-to-head trials with posted results first, then other direct comparisons, then other joint matches.
        def rank(r):
            design=r['facts'].get('comparison_design',{})
            return (0 if design.get('direct_comparison') and design.get('randomized_trial') else 1 if design.get('direct_comparison') else 2,
                    0 if r['facts'].get('primary_results') else 1)
        rows.sort(key=rank)
    total=result.get('totalCount')
    shown=call.condition if area else condition
    filters=term+('; '+call.phase.replace('PHASE','Phase ') if call.phase else '')+('; '+shown if shown else '')+(' (therapy area: '+area[0]+')' if area else '')
    method='joint intervention match; registry arms classified for direct comparison' if call.compare_with else 'intervention match' if search=='query.intr' else 'study identifier' if search=='query.id' else 'sponsor match, interventional studies' if search=='query.spons' else 'keyword search'
    order='relevance' if call.compare_with else 'last update'
    posted=sum(1 for r in rows if r['facts'].get('primary_results'))
    return rows,f'{filters} ({method}): {total if isinstance(total,int) else "an unknown number of"} registry matches; {len(rows)} retrieved, sorted by {order} (maximum twelve). This is not a complete pipeline. Current status is not a verified transition; posted results are not proof of benefit. Posted primary-outcome values were read for {posted} retrieved record(s); secondary outcomes and adverse-event tables were not analyzed.'


def fda_term(query):
    value=re.sub(r'[^\w .+/-]',' ',query,flags=re.UNICODE).strip()[:160]
    if not value:raise ValueError('Empty FDA drug term')
    if re.fullmatch(r'(?:ANDA|NDA|BLA)\d{6}',value,re.I):return 'application_number:"'+value.upper()+'"'
    return ' OR '.join(field+':"'+value+'"' for field in ('products.brand_name','products.active_ingredients.name','sponsor_name'))


def fda_headers():
    return {'Authorization':'Basic '+base64.b64encode((settings.OPENFDA_API_KEY+':').encode()).decode()} if settings.OPENFDA_API_KEY else None


async def fda(call,client):
    params={'limit':5,'sort':'submissions.submission_status_date:desc'}
    application_id=re.sub(r'\s+','',call.query.upper())
    if re.fullmatch(r'(?:ANDA|NDA|BLA)\d{6}',application_id):
        result=await data(client,'https://api.fda.gov/drug/drugsfda.json',params={**params,'search':'application_number:"'+application_id+'"'},headers=fda_headers())
    else:
        result,_=await openfda_first(client,'https://api.fda.gov/drug/drugsfda.json',('products.brand_name','products.active_ingredients.name','sponsor_name'),
            drug_terms(call.query),params,fda_headers())
    if not isinstance(result.get('results'),list):raise ValueError('Invalid FDA response')
    rows=[]
    for application in result['results'][:5]:
        identifier=application.get('application_number','')
        if not re.fullmatch(r'(?:ANDA|NDA|BLA)\d{6}',identifier):continue
        products=application.get('products',[])
        def tentative(s):return tentative_submission(s,products)
        approved=sorted([s for s in application.get('submissions',[]) if s.get('submission_status')=='AP' and not tentative(s)],key=lambda s:s.get('submission_status_date',''),reverse=True)[:5]
        pending=sorted([s for s in application.get('submissions',[]) if tentative(s)],key=lambda s:s.get('submission_status_date',''),reverse=True)[:5]
        statuses=[str(p.get('marketing_status') or '') for p in products]
        facts={'application':identifier,'sponsor':application.get('sponsor_name'),
            'marketing_authorised':not (statuses and all('tentative' in s.casefold() for s in statuses)),
            'products':[{'brand':p.get('brand_name'),'ingredients':p.get('active_ingredients'),'form':p.get('dosage_form'),'route':p.get('route'),
                'marketing_status':p.get('marketing_status')} for p in products[:6]],
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


def indication_headings(text,brands):
    """Numbered indication subsection titles (1.1, 1.2 ...) from the full prescribing information, for any label layout."""
    names=sorted({b for b in brands if isinstance(b,str) and b.strip()},key=len,reverse=True)
    stop=re.compile(r'\s(?:'+''.join(re.escape(n)+'|' for n in names)+r'[A-Z]{4,}(?:\s+[A-Z]{3,})*\s*[®™]?\s*(?:,|is\b|in\b|as\b|for\b|\()|•|(?:is|are)\s+indicated\b|indicated\s+for\b|in combination\b|for the treatment\b|as a single agent\b)')
    found={}
    for match in re.finditer(r'(?<![\d.])1\.(\d{1,2})\s+(?=[A-Z])',text):
        segment=' '+text[match.end():match.end()+220]
        end=stop.search(segment)
        title=(segment[:end.start()] if end else segment[:140]).strip(' ,;:-')
        if 3<=len(title)<=160 and not re.fullmatch(r'INDICATIONS AND USAGE',title,re.I) and match[1] not in found:
            found[match[1]]=title
    return [found[k] for k in sorted(found,key=int)][:50]


def indication_statements(text):
    """Bulleted or sentence-listed indications for labels without numbered subsections."""
    start=re.search(r'\bindicated\b\s*(?:for|:)?',text)
    if not start:return []
    rest=text[start.end():]
    second=re.search(r'\b(?:is|are)\s+[^.]{0,220}?\bindicated\b|\(\s*1\s*\)',rest)
    block=rest[:second.start()] if second else rest[:3000]
    parts=block.split('•') if '•' in block else re.split(r'\.\s+(?=(?:to|as|for|in|To|As|For|In)\b)',block)
    statements=[]
    for part in parts:
        part=re.sub(r'\.\s+[A-Z][A-Z0-9 ®™-]{2,}$','',part.strip(' .;:•'))
        if len(part)>=15:statements.append(part[:300])
    return list(dict.fromkeys(statements))[:20]


async def labels(call,client):
    result,_=await openfda_first(client,'https://api.fda.gov/drug/label.json',('openfda.brand_name','openfda.generic_name','openfda.substance_name'),
        drug_terms(call.query),{'limit':3,'sort':'effective_time:desc'})
    if not isinstance(result.get('results'),list):raise ValueError('Invalid label response')
    rows=[]
    for label in result['results'][:3]:
        identifier=label.get('set_id','')
        if not re.fullmatch(r'[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}',identifier):continue
        facts={'sections':{},'boxed_warning_present':bool(label.get('boxed_warning'))}
        for name in ('indications_and_usage','boxed_warning','dosage_and_administration','warnings_and_cautions','contraindications'):
            value=label.get(name)
            if not isinstance(value,list):continue
            full=clean_text(' '.join(v for v in value if isinstance(v,str)),100000)
            # Choose representative passages from the entire section, not a prefix presented as complete.
            limit=28000 if name=='indications_and_usage' else 6000 if name=='dosage_and_administration' else 5000
            facts[name]=full if len(full)<=limit else full[:limit//2]+' … [middle omitted] … '+full[-limit//2:]
            facts['sections'][name]={'characters':len(full),'complete':len(full)<=limit}
            if name=='indications_and_usage':
                brands=[*(label.get('openfda') or {}).get('brand_name',[]),*(label.get('openfda') or {}).get('generic_name',[])]
                facts['indication_headings']=indication_headings(full,[b.upper() for b in brands]+brands)
                if not facts['indication_headings']:facts['indication_statements']=indication_statements(full)
            if name=='boxed_warning':
                heading=re.match(r'\s*(WARNING[^•]{0,160}?)(?=\s+(?:•|[A-Z][a-z])|$)',full)
                facts['boxed_warning_title']=(heading[1] if heading else full[:160]).strip(' :.-')
        facts['label_version']=label.get('version');facts['brand_names']=(label.get('openfda') or {}).get('brand_name',[])
        facts['generic_names']=(label.get('openfda') or {}).get('generic_name',[])
        rows.append(row(', '.join(facts['brand_names']) or 'FDA-submitted label','https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid='+identifier,
            'drug_label',facts,date=label.get('effective_time'),date_meaning='Label effective time as recorded'))
    return rows,'Up to three FDA-submitted labeling records. Section completeness and full character counts are explicit; omitted text must not be described as a complete list of main indications. A missing boxed-warning section is not a boxed warning. Read the linked full label; label availability alone does not establish FDA approval or suitability for an individual patient.'


async def orange_book(call,client):
    value=re.sub(r'[^\w .+/-]',' ',call.query,flags=re.UNICODE).strip()[:160]
    if not value:raise ValueError('Empty Orange Book term')
    url='https://api.fda.gov/drug/orangebook.json';fields=('products.active_ingredients.name','products.brand_name')
    if re.fullmatch(r'(?:NDA|ANDA)?\s?\d{6}',value,re.I):
        terms=None;search='products.application_number:'+value[-6:]
    else:
        # Resolve multi-word wording once on innovator listings, then reuse the same product terms for generics.
        terms=drug_terms(call.query)
        if len(terms)>1:_,terms=await openfda_first(client,url,fields,terms,{'limit':1},suffix=' AND products.application_type:N')
        elif not terms:raise ValueError('Empty Orange Book term')
        search=' OR '.join(field+':"'+term.replace('"','')+'"' for term in terms for field in fields)
    found=await asyncio.gather(*(data(client,url,params={'search':'('+search+') AND products.application_type:'+kind,'limit':6}) for kind in ('N','A')))
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


async def recalls(call,client):
    """Structured FDA drug enforcement (recall) reports, newest report first."""
    url='https://api.fda.gov/drug/enforcement.json'
    terms=drug_terms(call.query)
    if not terms:raise ValueError('Empty recall term')
    search='('+' OR '.join(field+':"'+term.replace('"','')+'"' for term in terms[:4] for field in ('openfda.generic_name','openfda.brand_name','product_description'))+')'
    result=await data(client,url,params={'search':search,'sort':'report_date:desc','limit':10},headers=fda_headers())
    if not isinstance(result.get('results'),list):raise ValueError('Invalid FDA enforcement response')
    rows=[]
    for raw in result['results'][:10]:
        identifier=raw.get('recall_number')
        if not isinstance(identifier,str) or not re.fullmatch(r'[A-Z]-\d{3,5}-\d{4}',identifier):continue
        reported=iso_date(raw.get('report_date'))
        facts=compact({'recall_number':identifier,'classification':raw.get('classification'),'status':raw.get('status'),
            'report_date':reported,'recall_initiation_date':iso_date(raw.get('recall_initiation_date')),
            'reason':clean_text(raw.get('reason_for_recall'),600),'recalling_firm':clean_text(raw.get('recalling_firm'),160),
            'voluntary_or_mandated':raw.get('voluntary_mandated'),'distribution':clean_text(raw.get('distribution_pattern'),240),
            'product_quantity':clean_text(raw.get('product_quantity'),160),'lots_or_codes':clean_text(raw.get('code_info'),300)})
        rows.append(row(clean_text(raw.get('product_description'),220) or identifier,
            url+'?search=recall_number:%22'+identifier+'%22','fda_recall',facts,clean_text(raw.get('reason_for_recall'),600),
            reported,'FDA enforcement report date'))
    total=(result.get('meta') or {}).get('results',{}).get('total')
    return rows,f'{call.query}: {total if isinstance(total,int) else len(rows)} FDA drug enforcement (recall) reports matched; up to ten most recent retrieved by report date. Report dates differ from recall-initiation dates; a recall of specific lots does not establish a product-wide safety problem.'


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


EXECUTORS={'drug_history':drug_history,'trials':trials,'fda':fda,'literature':literature,'labels':labels,'orange_book':orange_book,'recalls':recalls,'official_search':official_search}


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
