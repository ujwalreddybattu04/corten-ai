"""Source-built tables and report assembly; the model never calculates report data."""
import json,re
from datetime import datetime,timezone
from src.services.pharma_research import source_text
from src.services.pharma_deep_plan import TOPICS

def value(item):
    if item is None or item=='':return 'Not supplied'
    return json.dumps(item,ensure_ascii=False) if isinstance(item,(dict,list)) else str(item)

def milestone(item):
    if not isinstance(item,dict) or not item.get('date'):return 'Not supplied'
    return str(item['date'])+' ('+{'ACTUAL':'actual','ESTIMATED':'estimated'}.get(item.get('type'),'qualifier not supplied')+')'

def tables_from(records):
    tables=[];trials=[];outcomes=[];approvals=[];patents=[];recalls=[]
    for row in records:
        facts=row.get('facts') or {};ref=row['citation'];kind=row['kind']
        if kind=='trial_record':
            trials.append([facts.get('study_id'),facts.get('acronym') or row['title'],', '.join(str(p).replace('PHASE','Phase ') for p in facts.get('phases',[])),str(facts.get('status') or 'Not supplied').replace('_',' ').capitalize(),', '.join(facts.get('conditions') or []),
                milestone(facts.get('primary_completion')),milestone(facts.get('completion')),
                'Posted' if facts.get('results_present') is True else 'Not posted in retrieved record' if facts.get('results_present') is False else 'Not established',ref])
            for outcome in facts.get('primary_results',[]):
                for measure in outcome.get('values',[]):
                    outcomes.append([facts.get('study_id'),outcome.get('measure'),outcome.get('time_frame'),measure.get('group'),measure.get('value'),outcome.get('unit'),
                        measure.get('spread'),measure.get('lower'),measure.get('upper'),ref])
        elif kind=='fda_application':
            for submission in facts.get('approved_submissions',[]):
                approvals.append([facts.get('application'),facts.get('sponsor'),submission.get('type'),submission.get('number'),submission.get('classification'),submission.get('date'),'Approved',ref])
            for submission in facts.get('tentative_submissions',[]):
                approvals.append([facts.get('application'),facts.get('sponsor'),submission.get('type'),submission.get('number'),submission.get('classification'),submission.get('date'),'Tentative; marketing not authorised by this action',ref])
        elif kind=='orange_book':
            products=facts.get('products') or [];application=products[0].get('application_number') if products else None
            for listing in facts.get('patents',[]):patents.append([application, 'Patent',listing.get('patent_no') or listing.get('patent_number'),listing.get('expiration_date') or listing.get('patent_expire_date_text') or listing.get('patent_expiration_date'), 'Listing does not establish enforceability or a launch date',ref])
            for listing in facts.get('exclusivity',[]):patents.append([application,'Exclusivity',listing.get('code') or listing.get('exclusivity_code'),listing.get('exclusivity_expiration_date') or listing.get('expiration_date') or listing.get('exclusivity_date'),'Listing does not establish market-entry timing',ref])
        elif kind=='fda_recall':
            recalls.append([facts.get('recall_number'),facts.get('recalling_firm'),facts.get('classification'),facts.get('recall_initiation_date'),facts.get('status'),facts.get('reason'),ref])
    def add(heading,columns,rows):
        if rows:
            unique={json.dumps(row,ensure_ascii=False):row for row in rows}
            tables.append({'heading':heading,'columns':columns,'rows':[[value(v) for v in row] for row in unique.values()]})
    add('Retrieved trials',['Study ID','Study / acronym','Phase','Status','Registered conditions','Primary completion','Study completion','Registry results','Source'],trials)
    add('Posted primary outcome values',['Study ID','Outcome','Time frame','Group','Value','Unit','Spread','Lower','Upper','Source'],outcomes)
    add('FDA application actions',['Application','Sponsor','Submission','Number','Classification','Action date','Status','Source'],approvals)
    add('Patent and exclusivity listings',['Application','Listing','Identifier / code','Listed expiry','Interpretation limit','Source'],patents)
    add('FDA recalls',['Recall','Firm','Classification','Initiated','Status','Reason','Source'],recalls)
    return tables

def timeline_from(records):
    items=[]
    for row in records:
        facts=row.get('facts') or {}
        if row.get('date'):items.append({'date':str(row['date']),'event':row['title'],'meaning':row.get('date_meaning') or 'Source date; event meaning not supplied','source':row['citation']})
        if row['kind']=='trial_record':
            for key,label in [('primary_completion','Primary completion'),('completion','Study completion')]:
                detail=facts.get(key) or {}
                if isinstance(detail,dict) and detail.get('date'):items.append({'date':detail['date'],'event':str(facts.get('study_id'))+' — '+label,'meaning':detail.get('type') or 'Qualifier not supplied','source':row['citation']})
        if row['kind']=='fda_application':
            for key,label in [('approved_submissions','FDA approved submission'),('tentative_submissions','FDA tentative approval; not marketing authorisation')]:
                for submission in facts.get(key,[]):
                    if submission.get('date'):items.append({'date':str(submission['date']),'event':str(facts.get('application'))+' — '+str(submission.get('classification') or submission.get('type') or 'Submission'),'meaning':label,'source':row['citation']})
    unique={json.dumps(row,sort_keys=True):row for row in items}
    def sortable(item):
        from src.services.pharma_quality import dates_in
        found=dates_in(item['date'])
        return found[0][0] if found else item['date']
    return sorted(unique.values(),key=sortable)[:80]

def claim_text(claim):return claim['text']+' '+''.join('['+str(n)+']' for n in claim['sources'])
def markdown_table(table):
    def cell(value):return source_text(value).replace('\n',' ')
    return '\n'.join(['| '+' | '.join(table['columns'])+' |','| '+' | '.join('---' for _ in table['columns'])+' |',
        *['| '+' | '.join(cell(v) if i<len(row)-1 else '['+str(v)+']' for i,v in enumerate(row))+' |' for row in table['rows']]])

def build_report(query,plan,state):
    tables=tables_from(state['records']);timeline=timeline_from(state['records'])
    unknown=[{'topic':c['label'],'reason':c['detail']} for c in state['coverage'] if c['status']!='covered']
    unknown.extend({'topic':TOPICS[c['topic']][0],'reason':c['reason']} for c in state['conflicts'])
    unknown.extend({'topic':'Research limit','reason':reason} for reason in state['limits'])
    sections=[{'heading':s['heading'],'claims':s['claims']} for s in state['sections'] if s['claims']]
    if not sections:unknown.append({'topic':'Written interpretation','reason':'No model-written finding passed all checks. The retrieved source tables and exact passages remain available for review.'})
    checks=[]
    for gap in unknown[:6]:checks.append('Verify '+gap['topic'].lower()+' against the original primary records before changing an assumption.')
    if not checks:checks=['Review the original sources and reconcile dates, populations and endpoints before changing forecast assumptions.']
    report={'version':1,'title':'Pharma deep research','query':query,'generated_at':datetime.now(timezone.utc).isoformat(),
        'plan':plan.model_dump(),'sections':sections,'tables':tables,'timeline':timeline,'unknown':unknown,'next_checks':checks,
        'not_verified':state['not_verified'],'coverage':state['coverage'],'sources':state['sources'],'quotes':state['quotes'],
        'records':state['records'],'metrics':{k:state.get(k,0) for k in ('round','search_count','documents_read','model_calls','verified_claims')},
        'limits':{'rounds':plan.max_rounds,'searches':30,'documents':12,'model_calls':12,'monthly_model_budget':'Existing shared Pharma budget; no increase'},
        'sample_notice':'This is a bounded research sample. Search excerpts, retrieved API fields and full-document passages are identified separately. Absence from this report is not proof that evidence does not exist.'}
    pieces=[]
    for section in sections:
        pieces+=['## '+section['heading'],'',*sum(([claim_text(c),''] for c in section['claims']),[])]
    if not sections:pieces+=['## Key answer','','The written interpretation could not be verified. Review the retrieved evidence below.','']
    for table in tables:
        pieces+=['## '+table['heading'],'',markdown_table({**table,'rows':table['rows'][:20]}),'']
        if len(table['rows'])>20:pieces+=['Showing 20 of '+str(len(table['rows']))+' retrieved rows. The full table is included in the Word, PDF and Excel downloads.','']
    if timeline:
        pieces+=['## Timeline','',markdown_table({'columns':['Date','Record / milestone','Date meaning','Source'],'rows':[[t['date'],t['event'],t['meaning'],str(t['source'])] for t in timeline]}),'']
    pieces+=['## What remains unknown','']
    pieces.extend('- **'+source_text(g['topic'])+':** '+source_text(g['reason']) for g in unknown)
    if not unknown:pieces.append('The selected checklist has evidence for each topic. This does not establish exhaustive coverage.')
    if state['not_verified']:
        pieces+=['','## Not verified','',*['- '+source_text(n['section'])+': '+source_text(n['reason']) for n in state['not_verified']]]
    pieces+=['','## Next checks','',*['- '+source_text(c) for c in checks],'',report['sample_notice']]
    report['markdown']='\n'.join(pieces)
    return report
