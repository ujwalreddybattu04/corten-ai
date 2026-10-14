"""Deterministic checks for source coverage and recurring Pharma factual failures."""
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
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


def check_claims(text,evidence):
    """Conservative vetoes supplement citations; they are not a general truth oracle."""
    labels=[r['facts'] for r in evidence if r.get('kind')=='drug_label']
    for sentence in re.split(r'(?<=[.!?])\s+|\n',text):
        if re.search(r'\b(?:doctors?|clinicians?|physicians?|patients?)\b.*\b(?:may|should|can|could)\s+(?:consider|use|increase|take|prescribe|switch|escalate)\b|\b(?:consider|recommend)\s+(?:a\s+)?higher\s+dose',sentence,re.I):
            raise LLMProviderError('The draft inferred prescribing advice. Analyst research must describe evidence rather than recommend treatment.')
        if re.search(r'\b(?:searched|queried|search of|searching)\s+(?:the\s+)?PubMed\b',sentence,re.I):
            raise LLMProviderError('PubMed was not queried directly; the publication tool uses Europe PMC.')
        if labels and re.search(r'\bboxed\s+warning\b',sentence,re.I):
            negative=re.search(r'\b(?:no|none|not|without|absent|missing|doesn.t|does not)\b',sentence,re.I)
            matched=[label for label in labels if any(name and name.casefold() in sentence.casefold() for name in [*label.get('brand_names',[]),*label.get('generic_names',[])])]
            relevant=matched or labels
            if not negative and not all(label.get('boxed_warning_present',bool(label.get('boxed_warning'))) for label in relevant):
                raise LLMProviderError('The supplied labels do not contain a boxed-warning section.')
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


def publication_item(item):
    if item.get('source') not in {'news','company','fda_updates','fda_safety'}:return item
    title=item.get('title','')
    if re.search(r'\bnovel drug approvals?\s+(?:for\s+)?20\d{2}\b|^\s*[A-Z]{1,6}\s*[-–]\s*\d{1,2}/\d{1,2}/\d{4}\s*[-–]\s*EX\.?\s*99\b',title,re.I):return None
    if not title.strip():return None
    summary=item.get('summary','')
    legal=re.search(r'\b(?:forward[- ]looking statements?|safe harbor|private securities litigation reform act|except as required by law|no obligation to update)\b',summary,re.I)
    if legal:summary=summary[:legal.start()].strip(' .:;-')
    if re.match(r'^\s*(?:legal (?:notice|disclaimer)|cautionary (?:note|statement)|copyright\b)',summary,re.I):summary=''
    return {**item,'summary':summary}


def publication_key(item):
    if item.get('source') not in {'news','company','fda_updates','fda_safety'}:return item['id']
    # Same issuer/day/headline is one publication even when its tracking URL differs.
    title=re.sub(r'\s*[|–—-]\s*(?:Pfizer|Amgen|Novartis|Bristol Myers Squibb|AstraZeneca).*$', '',item.get('title',''),flags=re.I)
    return (item.get('organization','').casefold(),item['date'],re.sub(r'\W+','',title.casefold()))
