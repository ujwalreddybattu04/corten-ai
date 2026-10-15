"""Quote provenance, source coverage, and claim-level evidence checks for Deep research."""
import hashlib,json,re
from urllib.parse import urlsplit
from src.services.pharma_quality import check_dates,check_numbers,check_claims,check_absence,dates_in,evidence_dates
from src.services.llm_runtime import LLMProviderError
from src.services.pharma_deep_plan import TOPICS

def normalized(value):return re.sub(r'\s+',' ',value).strip()
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def source_id(state,row,topic):
    key=row['url']
    existing=next((s for s in state['sources'] if s['url']==key),None)
    if existing:
        if topic not in existing['topics']:existing['topics'].append(topic)
        return existing['id']
    if len(state['sources'])>=40:return None
    identifier=len(state['sources'])+1
    state['sources'].append({'id':identifier,'title':row['title'],'url':key,'date':row.get('date'),
        'date_meaning':row.get('date_meaning'),'retrieved_at':row['retrieved_at'],'topics':[topic],
        'read_status':'search_excerpt' if row['kind'].startswith('indexed_') else 'api_record'})
    return identifier

def add_quote(state,source,topic,text,method,*,field=None,proof=None):
    text=normalized(text)
    if not text or len(text)>1800:return
    identifier='Q'+hashlib.sha256((str(source)+'|'+text).encode()).hexdigest()[:12]
    existing=next((q for q in state['quotes'] if q['id']==identifier),None)
    if existing:
        if existing['method']=='search_excerpt' and method!='search_excerpt':existing.update(method=method,field=field,proof=proof)
        return
    if len(state['quotes'])>=140 or sum(q['topic']==topic for q in state['quotes'])>=24:return
    state['quotes'].append({'id':identifier,'source':source,'topic':topic,'text':text,'method':method,'field':field,'proof':proof})

def structured_quotes(state,row,topic,source,query):
    """Values are copied verbatim from the parsed API record; field names preserve their context."""
    facts=row.get('facts') or {}
    priority=('primary_results','results_present','results_posted','comparison_design','primary_completion','completion','status','phases','boxed_warning_present','boxed_warning','warnings_and_cautions','contraindications','indication_headings','indication_statements','indications_and_usage','approved_submissions','tentative_submissions','patents','exclusivity','abstract','reason')
    metadata={'identifier','source','doi','authors','journal','publication_types','abstract_complete','evidence_type','sections','label_version'}
    context={key:facts[key] for key in ('study_id','acronym','brand_names','generic_names','application','sponsor') if facts.get(key)}
    ordered=sorted(facts,key=lambda k:priority.index(k) if k in priority else len(priority))
    initial=len(state['quotes'])
    for key in ordered:
        if key in metadata or len(state['quotes'])-initial>=8:continue
        value=facts[key]
        if value is None or value in ('',[],{}):continue
        rendered=json.dumps({**context,key:value},ensure_ascii=False,sort_keys=True)
        if len(rendered)<=1700:
            add_quote(state,source,topic,rendered,'api_record',field=key);continue
        # Never splice a number or JSON object. Split arrays at complete member boundaries.
        if isinstance(value,list):
            for element in value[:8]:
                rendered=json.dumps({**context,key:element},ensure_ascii=False,sort_keys=True)
                if len(rendered)<=1700:add_quote(state,source,topic,rendered,'api_record',field=key)
        elif isinstance(value,str):
            from src.services.pharma_documents import relevant_quotes
            for quote in relevant_quotes(value,query+' '+TOPICS[topic][0],limit=4,word_budget=350):
                add_quote(state,source,topic,quote,'api_section',field=key)
    if row.get('date'):
        add_quote(state,source,topic,json.dumps({'date':row['date'],'meaning':row.get('date_meaning')},ensure_ascii=False),'api_record',field='record_date')

def add_records(state,result,topic,query):
    kept=0
    for record in result.get('records',[]):
        row={**record,'topic':topic};identity=fingerprint({k:row.get(k) for k in ('url','kind','facts','excerpt')})
        if identity in state['record_hashes']:continue
        source=source_id(state,row,topic)
        if source is None or len(state['records'])>=60:continue
        state['record_hashes'].append(identity);row['citation']=source;state['records'].append(row);kept+=1
        if not row['kind'].startswith('indexed_'):structured_quotes(state,row,topic,source,query)
        elif row.get('excerpt'):
            from src.services.pharma_documents import relevant_quotes
            for quote in relevant_quotes(row['excerpt'],query,limit=2,word_budget=120):
                add_quote(state,source,topic,quote,'search_excerpt')
    return kept

def coverage(state,topics):
    rows=[]
    for topic in topics:
        calls=[c for c in state['searches'] if c['topic']==topic]
        quotes=[q for q in state['quotes'] if q['topic']==topic]
        complete=[q for q in quotes if q['method']!='search_excerpt']
        sources={q['source'] for q in quotes}
        status='covered' if complete else 'partial' if quotes else 'unavailable' if calls and all(c['status']=='unavailable' for c in calls) else 'missing'
        detail='Usable API fields or document passages retrieved; coverage is limited to this sample.' if complete else 'Only indexed excerpts are available; the full source was not verified.' if quotes else 'No usable evidence retrieved for this checklist item; absence is not proof that none exists.'
        limitations=list(dict.fromkeys(c.get('coverage','') for c in calls if c.get('coverage')))
        if limitations:detail+=' '+' '.join(limitations)[:1000]
        rows.append({'topic':topic,'label':TOPICS[topic][0],'status':status,'sources':len(sources),'quotes':len(quotes),'detail':detail})
    return rows

def conflicts(state):
    """Flag differing observations of the same identified fact; never merge them as one current fact."""
    seen={};output=[]
    for row in state['records']:
        facts=row.get('facts') or {};identity=facts.get('study_id') or facts.get('application') or facts.get('label_id')
        if not identity:continue
        for field in ('status','completion','primary_completion','boxed_warning_present','marketing_authorised'):
            if field not in facts:continue
            key=(row['kind'],identity,field);value=json.dumps(facts[field],sort_keys=True)
            if key in seen and seen[key][0]!=value:
                output.append({'topic':row['topic'],'reason':'Different observations of '+str(identity)+' / '+field+' need reconciliation; source dates and versions may differ.','sources':[seen[key][1],row['citation']]})
            seen[key]=(value,row['citation'])
    return output[:12]

def verified_claim(claim,quotes,records,tools):
    if not isinstance(claim,dict) or set(claim)-{'id','text','quote_ids'}:raise ValueError('Invalid claim schema')
    text=claim.get('text','');identifiers=claim.get('quote_ids',[])
    if not isinstance(text,str) or not 10<=len(text)<=1500 or not isinstance(identifiers,list) or not 1<=len(identifiers)<=5:raise ValueError('A finding needs supporting quotations')
    selected=[q for q in quotes if q['id'] in identifiers]
    if len(selected)!=len(set(identifiers)) or len(identifiers)!=len(set(identifiers)):raise ValueError('Unknown or duplicate quote references')
    if re.search(r'https?://|\[\d+\]|\bQ[a-f0-9]{12}\b',text):raise ValueError('Source references must use the evidence fields')
    evidence=[{'kind':'quoted_source','facts':{'text':q['text']}} for q in selected]
    quote_text=' '.join(q['text'] for q in selected)
    check_dates(text,evidence);check_numbers(text,evidence)
    known_dates=evidence_dates(evidence)
    for date,precision,_,_ in dates_in(text):
        if not (date in known_dates if precision=='day' else any(d.startswith(date) for d in known_dates)):raise ValueError('The date is absent from the supporting quotes')
    # Unlike the fast answer check, Deep research checks integers too, against only the cited quotes.
    numeric_text=text
    for _,_,start,end in reversed(dates_in(text)):numeric_text=numeric_text[:start]+' '+numeric_text[end:]
    for number in re.findall(r'(?<!\w)\d+(?:[.,]\d+)*(?:\s?%)?',numeric_text):
        value=number.replace(',','').replace(' ','')
        known=quote_text.replace(',','').replace(' ','')
        if not re.search(r'(?<!\d)'+re.escape(value)+r'(?!\d)',known):raise ValueError('A number is absent from the supporting quote')
    for identifier in re.findall(r'\b(?:NCT\d{8}|(?:ANDA|NDA|BLA)\d{5,8}|(?:EMEA|EMA)/H/C/\d+|VR/\d+)\b',text):
        if identifier not in quote_text:raise ValueError('An identifier is absent from the supporting quote')
    scoped=[r for r in records if r['citation'] in {q['source'] for q in selected}]
    approval_assertion=re.search(r'\b(?:is|was|has been|received|granted)\b[^.;]{0,35}\b(?:accelerated approval|approved under accelerated)\b|\bFDA granted accelerated approval\b',text,re.I)
    if approval_assertion:
        if not re.search(r'\bfor\b',text,re.I):raise ValueError('Accelerated approval must identify the specific indication, not the whole product')
        primary_action=any(r['kind']=='fda_application' or (urlsplit(r['url']).hostname or '').endswith('fda.gov') and r['kind']!='drug_label' for r in scoped)
        if not primary_action and not re.search(r'\b(?:publication|paper|article|authors|company)\b.{0,40}\b(?:reports?|states?|describes?|reported)\b',text,re.I):raise ValueError('An unqualified accelerated-approval conclusion needs a primary FDA action source')
    # Formulations sharing an ingredient must not inherit each other's administration route.
    for row in scoped:
        facts=row.get('facts') or {}
        for product in facts.get('products',[]) if row['kind']=='fda_application' else []:
            name=product.get('brand') or ''
            routes=product.get('route') or ''
            if isinstance(routes,list):routes=' '.join(routes)
            if not name or not re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',text,re.I):continue
            asserted=re.findall(r'\bfor\s+(intravenous|subcutaneous|oral|intramuscular)\s+(?:use|administration)\b',text,re.I)
            if routes and any(route.casefold() not in routes.casefold() for route in asserted):raise ValueError('The administration route contradicts the named FDA product')
        if row['kind']=='fda_application' and facts.get('marketing_authorised') is True:
            if re.search(r'\b(?:is|it is|but it is)\s+not\s+(?:yet\s+)?marketing\s+authori[sz]ed\b',text,re.I):raise ValueError('A historical tentative action does not negate current FDA authorisation')
    check_dates(text,scoped or evidence)  # Apply typed actual/estimated and primary/full-study qualifiers too.
    check_claims(text,scoped)
    check_absence(text,tools)
    if re.search(r'\b(?:no trials? (?:exist|exists)|there (?:are|is) no trials?|only (?:one|1) trial exists)\b',text,re.I):raise ValueError('A limited search cannot establish universal trial absence')
    historic=r'\b(?:initially (?:authori[sz]ed|approved)|(?:original|initial) (?:approval|authori[sz]ation))\b'
    population=r'\b(?:adults?|children|paediatric|pediatric|patients?|population|indication)\b'
    if re.search(historic,text,re.I) and re.search(population,text,re.I) and not re.search(r'does not establish|not established|unknown|cannot establish',text,re.I):
        if not any(re.search(historic+r'.{0,220}'+population,q['text'],re.I) for q in selected):raise ValueError('The original approved population needs explicit contemporaneous evidence')
    if re.search(r'\b(?:earliest|most imminent|highest|lowest)\b',text,re.I):
        if not any(re.search(r'\b(?:earliest|most imminent|highest|lowest)\b',q['text'],re.I) for q in selected):raise ValueError('A superlative is not established by a single retrieved measurement or date')
    return {**claim,'quote_ids':identifiers,'sources':sorted({q['source'] for q in selected})}

def source_links(state,source):
    return next((s for s in state['sources'] if s['id']==source),None)
