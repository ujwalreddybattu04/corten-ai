"""Deterministic checks for source coverage and recurring Pharma factual failures."""
import json
import re
from difflib import SequenceMatcher
from datetime import date, datetime, timezone
from src.services.llm_runtime import LLMProviderError


def citations(text):
    def expand(match):
        body=match[1]
        if re.fullmatch(r'\d+\s*[-–]\s*\d+',body):
            first,last=map(int,re.split(r'\s*[-–]\s*',body))
            if not 1<=first<=last<=20:raise LLMProviderError('The answer used an invalid reference range.')
            values=range(first,last+1)
        else:values=[int(v) for v in re.split(r'\s*,\s*',body)]
        return ''.join('['+str(v)+']' for v in values)
    return re.sub(r'\[(\d+(?:\s*[,–-]\s*\d+)*)\](?!\()',expand,text)


def strip_bibliography(text):
    """Source pills own attribution; a model-appended reference list repeats them and can drift."""
    text=re.sub(r'\n\s*#{0,6}\s*\**(?:references|sources|bibliography|citations|works cited)\**:?\s*\n(?:\s*(?:[-*]|\d+\.|\[\d+\])[^\n]*\n?)+\s*$','',text,flags=re.I)
    text=re.sub(r'(?:\n\s*(?:\[\d+\][,;\s]*)+)+\s*$','',text)
    return text.rstrip()


MONTHS={name:number for number,names in enumerate((('jan','january'),('feb','february'),('mar','march'),('apr','april'),('may',),('jun','june'),
    ('jul','july'),('aug','august'),('sep','sept','september'),('oct','october'),('nov','november'),('dec','december')),1) for name in names}
MONTH=r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?'


def month_number(token):
    token=token.casefold().rstrip('.')
    return MONTHS.get(token) or MONTHS.get(token[:3])


def _valid(year,month,day=None):
    try:
        date(int(year),int(month),int(day or 1))
        return True
    except ValueError:
        return False


def dates_in(text):
    """(iso, precision, start, end) for full or month-precision dates written in common analyst formats."""
    found=[];taken=[]
    def add(iso,precision,match):
        if any(s<match.end() and match.start()<e for s,e in taken):return
        taken.append((match.start(),match.end()));found.append((iso,precision,match.start(),match.end()))
    for match in re.finditer(r'\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b',text):
        if _valid(*match.groups()):add('-'.join(match.groups()),'day',match)
    for match in re.finditer(r'(?<![\d-])((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)',text):
        if _valid(*match.groups()):add('-'.join(match.groups()),'day',match)
    for match in re.finditer(r'\b'+MONTH+r'\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b',text,re.I):
        month=month_number(match[1])
        if month and _valid(match[3],month,match[2]):add(f'{match[3]}-{month:02d}-{int(match[2]):02d}','day',match)
    for match in re.finditer(r'\b(\d{1,2})\s+'+MONTH+r',?\s+((?:19|20)\d{2})\b',text,re.I):
        month=month_number(match[2])
        if month and _valid(match[3],month,match[1]):add(f'{match[3]}-{month:02d}-{int(match[1]):02d}','day',match)
    for match in re.finditer(r'\b((?:19|20)\d{2})-(\d{2})\b(?!-\d)',text):
        if _valid(match[1],match[2]):add(f'{match[1]}-{match[2]}','month',match)
    for match in re.finditer(r'\b'+MONTH+r',?\s+((?:19|20)\d{2})\b',text,re.I):
        month=month_number(match[1])
        if month:add(f'{match[2]}-{month:02d}','month',match)
    return sorted(found,key=lambda d:d[2])


def evidence_dates(evidence):
    text=json.dumps(evidence,ensure_ascii=False)
    return {iso for iso,_,_,_ in dates_in(text)}


def _grounded(iso,precision,known,today):
    if precision=='day':return iso in known or iso==today
    return any(k.startswith(iso) for k in known) or today.startswith(iso)


FUTURE_BEFORE=re.compile(r'(?<!was )(?<!were )(?<!had been )(?<!originally )\b(?:will(?: be)?|is expected|are expected|expected to|is anticipated|are anticipated|anticipated to|is scheduled|are scheduled|scheduled to|is projected|projected to|is planned|planned for|upcoming|forthcoming)\b[^.;]{0,45}$',re.I)
FUTURE_AFTER=re.compile(r'^[^.;]{0,25}\b(?:in the future|still ahead|has yet to|have yet to|is upcoming)\b',re.I)
ESTIMATE_NEAR=re.compile(r'\b(?:estimat\w*|expected|anticipated|projected|planned|scheduled)\b',re.I)
COMPLETED_BEFORE=re.compile(r'\b(?:completed|was completed|finished|ended|concluded|completion occurred)\b[^.;]{0,30}$',re.I)


def check_dates(text,evidence,today=None):
    """Every specific date must come from the evidence, keep its qualifier and keep its chronology."""
    today=today or datetime.now(timezone.utc).date().isoformat()
    known=evidence_dates(evidence)
    actual=set();estimated=set();primary_only=set();study=set()
    for row in evidence:
        if row.get('kind')!='trial_record':continue
        for field in ('primary_completion','completion'):
            value=(row.get('facts') or {}).get(field) or {}
            if isinstance(value,dict) and value.get('date'):
                (actual if value.get('type')=='ACTUAL' else estimated if value.get('type')=='ESTIMATED' else set()).add(str(value['date']))
                (primary_only if field=='primary_completion' else study).add(str(value['date']))
    primary_only-=study
    for iso,precision,start,end in dates_in(text):
        if not _grounded(iso,precision,known,today):
            raise LLMProviderError('The draft contained a date that is not in the retrieved evidence.')
        before=text[max(0,start-70):start];after=text[end:end+40]
        past=iso<today[:len(iso)]
        if past and (FUTURE_BEFORE.search(before) or FUTURE_AFTER.search(after)):
            raise LLMProviderError('The draft described a date that has already passed as a future event.')
        if iso in actual and iso not in estimated and ESTIMATE_NEAR.search(before[-45:]+' '+after[:20]):
            raise LLMProviderError('The draft called an actual registry date estimated.')
        if iso in estimated and iso not in actual and not past and COMPLETED_BEFORE.search(before):
            raise LLMProviderError('The draft described an estimated future date as completed.')
        # A primary-completion date is not the date the whole study completed.
        if iso in primary_only and COMPLETED_BEFORE.search(before) and not re.search(r'\bprimary\b',before[-60:],re.I):
            raise LLMProviderError('The draft called a primary-completion date the study completion date.')
    return text


def check_numbers(text,evidence,query=''):
    """Decimals and percentages are copied from sources, never computed or remembered by the model."""
    known=json.dumps(evidence,ensure_ascii=False)+' '+query
    body=re.sub(r'\[\d+\]|\bNCT\d{8}\b|\b(?:ANDA|NDA|BLA)\s?\d+\b','',text)
    for iso,_,start,end in reversed(dates_in(body)):body=body[:start]+' '+body[end:]
    for match in re.finditer(r'(?<![\w.])[-−–]?(\d+(?:\.\d+)?)(?=\s?%)|(?<![\w.])[-−–]?(\d+\.\d+)(?![\w.])',body):
        number=match[1] or match[2]
        variants={number,number.rstrip('0').rstrip('.') if '.' in number else number}
        if not any(re.search(r'(?<![\d.])'+re.escape(v)+r'(?![\d])',known) for v in variants if v):
            raise LLMProviderError('The draft contained a number that is not in the retrieved evidence.')
    return text


ABSENCE_RULES=[
    (re.compile(r'\bno\b[^.]{0,60}\b(?:recalls?|enforcement reports?|safety alerts?)\b|\b(?:recalls?|safety alerts?)\b[^.]{0,40}\b(?:were|was|have been|has been)\s+not\s+(?:identified|found|reported|retrieved)',re.I),'recalls',
     'Recall absence can only be stated after the FDA recall source was searched.'),
    (re.compile(r'\bno\b[^.]{0,60}\b(?:listed patents?|patents?|exclusivit\w*)\b|\b(?:patents?|exclusivit\w*)\b[^.]{0,40}\b(?:were|was)\s+not\s+(?:identified|found|listed)',re.I),'orange_book',
     'Patent or exclusivity absence can only be stated after the Orange Book was searched.'),
]


def check_absence(text,tools):
    for sentence in re.split(r'(?<=[.!?])\s+|\n',text):
        for pattern,tool,message in ABSENCE_RULES:
            if pattern.search(sentence) and tool not in tools:raise LLMProviderError(message)
    return text


ADVICE=re.compile(r'\b(?:clinicians?|physicians?|doctors?|prescribers?|healthcare (?:providers?|professionals?))\b[^.]{0,30}\b(?:should|may want to|might want to|could|may|can)\s+(?:consider|increase|prescribe|switch|escalate|start|initiate|favou?r|prefer|choose|select|use)\b'
    r'|\bpatients?\b[^.]{0,30}\b(?:should|may want to|might want to)\s+(?:consider|use|increase|take|switch|escalate|start|ask)\b'
    r'|\b(?:consider|recommend\w*)\s+(?:a\s+|using\s+)?(?:higher|increased|maximum|lower)\s+doses?',re.I)
ATTRIBUTED=re.compile(r'\b(?:label(?:ing)?|prescribing information|according to|per the|the trial|this trial|the study|this study|protocol|arms?|randomi[sz]ed|participants|enrolled)\b',re.I)


def check_claims(text,evidence):
    """Conservative vetoes supplement citations; they are not a general truth oracle."""
    labels=[r['facts'] for r in evidence if r.get('kind')=='drug_label']
    for sentence in re.split(r'(?<=[.!?])\s+|\n',text):
        # Label instructions and trial design are facts; recommendations to treat are not analyst research.
        if ADVICE.search(sentence) and not ATTRIBUTED.search(sentence):
            raise LLMProviderError('The draft inferred prescribing advice. Analyst research must describe evidence rather than recommend treatment.')
        if re.search(r'\b(?:searched|queried|search of|searching)\s+(?:the\s+)?PubMed\b',sentence,re.I):
            raise LLMProviderError('PubMed was not queried directly; the publication tool uses Europe PMC.')
        # Patent, exclusivity and approval dates never establish when a generic or product can launch.
        if (re.search(r'\b(?:generics?|biosimilars?|launch\w*|market entry|enter(?:s|ing)? the market)\b',sentence,re.I)
                and re.search(r'\b(?:could|can|may|might|will|would|expected to|able to)\s+(?:\w+\s+){0,3}(?:launch|enter|be launched|become available|reach the market)\b|\blaunch(?:es|ed)?\s+(?:after|once|on|in|by)\b|\b(?:entry|launch) (?:date|timing) (?:is|would be|will be)\b',sentence,re.I)
                and not re.search(r'\b(?:not|no|cannot|can\'t|does not|do not|doesn.t|is not|are not|unknown|unclear|not established)\b',sentence,re.I)):
            raise LLMProviderError('Listed patent, exclusivity or approval dates do not establish a launch date.')
        if re.search(r'\b(?:the|these|all) studies are observational\b|\bthis study is observational\b',sentence,re.I):
            cited={int(n) for n in re.findall(r'\[(\d+)\]',sentence)}
            if any(r.get('citation') in cited and r.get('kind')=='publication' and r.get('facts',{}).get('evidence_type')=='review' for r in evidence):
                raise LLMProviderError('A review article must not be classified as an observational cohort study.')
        if labels and re.search(r'\bboxed\s+warning\b',sentence,re.I):
            negative=re.search(r'\b(?:no|none|not|without|absent|missing|doesn.t|does not)\b',sentence,re.I)
            matched=[label for label in labels if any(name and name.casefold() in sentence.casefold() for name in [*label.get('brand_names',[]),*label.get('generic_names',[])])]
            relevant=matched or labels
            if not negative and not all(label.get('boxed_warning_present',bool(label.get('boxed_warning'))) for label in relevant):
                raise LLMProviderError('The supplied labels do not contain a boxed-warning section.')
            if negative and matched and all(label.get('boxed_warning_present') for label in matched):
                raise LLMProviderError('The supplied label contains a boxed-warning section.')
        for row in evidence:
            if row.get('kind')!='trial_record':continue
            facts=row['facts'];names=[facts.get('study_id'),facts.get('acronym')]
            if any(name and re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',sentence,re.I) for name in names):
                if (facts.get('results_present') is True or facts.get('results_posted')) and re.search(r'\b(?:no results|results?\s+(?:are |is |have |has )?(?:not|not yet)|results?.*\bnot\s+(?:yet\s+)?posted)',sentence,re.I):
                    raise LLMProviderError('The cited trial has posted registry results.')
                if re.search(r'\b(?:earliest|most imminent|soonest|next to complete)\b',sentence,re.I):
                    field='primary_completion' if 'primary' in sentence.casefold() else 'completion'
                    current=(facts.get(field) or {}).get('date')
                    today=datetime.now(timezone.utc).date().isoformat()
                    dates=[(r.get('facts',{}).get(field) or {}).get('date','') for r in evidence if r.get('kind')=='trial_record']
                    if current and any(today<=other<current for other in dates):
                        raise LLMProviderError('The claimed earliest completion contradicts an earlier date in the retrieved records.')
    return text


def check_drug_spelling(text,names):
    tokens=set(re.findall(r'\b[A-Za-z][A-Za-z-]{7,}\b',text.casefold()))
    for name in names:
        name=name.casefold()
        if not re.fullmatch(r'[a-z-]{8,}',name):continue
        for token in tokens:
            # A single substituted character in a supplied long asset name is not a new drug.
            if token!=name and len(token)==len(name) and sum(a!=b for a,b in zip(token,name))==1 and SequenceMatcher(None,token,name).ratio()>.85:
                raise LLMProviderError('The draft changed the spelling of a supplied drug name.')
    return text


LISTING_PAGE=re.compile(r'\bnovel drug approvals?\b|\b(?:approvals|notifications)\b|\bdrug approvals and databases\b',re.I)
ACTION_VERB=re.compile(r'\b(?:approves?|approved|grants?|granted|announces?|authori[sz]es?|clears?|declines?|rejects?|issues?|warns?|requires?|launch(?:es)?)\b',re.I)
BOILERPLATE=re.compile(r'forward[- ]looking statements?|safe harbor|private securities litigation reform act|except as required by law|no obligation to update'
    r'|results do not guarantee|do not guarantee (?:safe|future)|actual results (?:may|could) differ|risks and uncertainties|could impact the future development'
    r'|possibility of unfavorable|may be contingent upon|subject to (?:substantial )?risks|cautionary (?:note|statement)|\blogo\b|cookie',re.I)


def publication_item(item):
    if item.get('source') not in {'news','company','fda_updates','fda_safety'}:return item
    title=item.get('title','')
    if re.search(r'^\s*[A-Z]{1,6}\s*[-–]\s*\d{1,2}/\d{1,2}/\d{4}\s*[-–]\s*EX\.?\s*99\b',title,re.I):return None
    # Index and list pages are navigation, not dated announcements.
    if item.get('source')=='fda_updates' and LISTING_PAGE.search(title) and not ACTION_VERB.search(title):return None
    if not title.strip():return None
    summary=item.get('summary','')
    legal=BOILERPLATE.search(summary)
    if legal:summary=summary[:legal.start()].strip(' .:;-')
    # A snippet that starts mid-sentence before boilerplate is a tail of legal text, not a summary.
    if re.match(r'^\s*(?:legal (?:notice|disclaimer)|cautionary (?:note|statement)|copyright\b)',summary,re.I) or (legal and (len(summary)<60 or re.match(r'^[a-z]',summary))):summary=''
    return {**item,'summary':summary}


def publication_key(item):
    if item.get('source') not in {'news','company','fda_updates','fda_safety'}:return item['id']
    # Same issuer/day/headline is one publication even when its tracking URL differs.
    title=re.sub(r'\s*[|–—-]\s*(?:Pfizer|Amgen|Novartis|Bristol Myers Squibb|AstraZeneca).*$', '',item.get('title',''),flags=re.I)
    return (item.get('organization','').casefold(),item['date'],re.sub(r'\W+','',title.casefold()))
