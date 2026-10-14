"""Regression cases from the analyst accuracy review; no live providers or patient data."""
import asyncio
import json
from unittest.mock import AsyncMock
import httpx
import pytest
from src.services import pharma_research as research, pharma_research_tools as tools
from src.services.pharma_quality import check_claims, check_drug_spelling, publication_item, publication_key
from src.services.pharma_events import impact
from src.services.pharma_catalog import mentioned_drugs
from src.services.pharma_sources import fda_records
from src.services.llm_runtime import LLMProviderError


def trial(nct,acronym,completion,posted=None):
    return {'kind':'trial_record','title':acronym,'url':'https://clinicaltrials.gov/study/'+nct,'facts':{
        'study_id':nct,'acronym':acronym,'completion':{'date':completion,'type':'ESTIMATED'},
        'results_posted':{'date':posted} if posted else None,'results_present':bool(posted)},'citation':1}


def test_valid_group_citations_and_head_to_head_sentence_are_not_rejected():
    rows=[trial('NCT12345678','Example','2027-09-01')]
    sources=[{'url':'https://clinicaltrials.gov/study/NCT12345678'}]*2
    answer=research.verified_answer('There is no head-to-head comparison between the two drugs in these retrieved records. [1, 2]',rows,sources)
    assert answer.endswith('[1][2]')
    # This checker catches unsupported absence of studies, not every English "there is no".
    assert research.verified_answer('There is no head-to-head comparison between the two drugs. [1]',rows,sources)
    with pytest.raises(LLMProviderError):research.verified_answer('A fact [1, 99]',rows,sources)


def test_same_drug_different_phase_or_comparator_is_a_distinct_search():
    calls=[{'tool':'trials','query':'Example','phase':phase} for phase in ('PHASE2','PHASE3')]
    assert len(research.Plan(intent='research',calls=calls).calls)==2
    with pytest.raises(ValueError):research.Plan(intent='research',calls=[calls[0],calls[0]])


def test_head_to_head_and_patent_plans_cannot_omit_the_critical_tool():
    chosen=research.Plan(intent='research',calls=[{'tool':'trials','query':q} for q in ('tirzepatide','semaglutide')])
    refined=research.refine_plan('tirzepatide vs semaglutide head-to-head',chosen)
    assert len(refined.calls)==1 and refined.calls[0].compare_with=='semaglutide'
    chosen=research.Plan(intent='research',calls=[{'tool':'fda','query':'apixaban'}])
    assert research.refine_plan('generic apixaban and patents',chosen).calls[0].tool=='orange_book'


def test_false_warning_prescribing_provenance_results_and_chronology_are_blocked():
    labels=[{'kind':'drug_label','facts':{'brand_names':['KEYTRUDA'],'boxed_warning_present':False}}]
    with pytest.raises(LLMProviderError):check_claims('KEYTRUDA has a boxed warning. [1]',labels)
    assert check_claims('KEYTRUDA has no boxed warning in the retrieved label. [1]',labels)
    for text in ['Doctors may consider higher doses. [1]','We searched PubMed. [1]']:
        with pytest.raises(LLMProviderError):check_claims(text,[])
    rows=[trial('NCT12345678','COMMANDS','2027-09-01','2024-02-01'),trial('NCT12345679','Other','2027-01-01')]
    with pytest.raises(LLMProviderError):check_claims('COMMANDS results are not yet posted. [1]',rows)
    with pytest.raises(LLMProviderError):check_claims('COMMANDS has the most imminent completion. [1]',rows)
    assert check_claims('COMMANDS has posted results. [1]',rows)
    with pytest.raises(LLMProviderError):check_drug_spelling('PITILISANT', ['pitolisant'])


@pytest.mark.asyncio
async def test_joint_comparator_and_broad_mds_condition_reach_registry():
    requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(200,json={'studies':[],'totalCount':0})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await tools.trials(tools.ToolCall(tool='trials',query='tirzepatide',compare_with='semaglutide',phase='PHASE3'),client)
        await tools.trials(tools.ToolCall(tool='trials',query='imetelstat',search_by='intervention',condition='lower-risk MDS'),client)
    assert requests[0].url.params['query.intr']=='"tirzepatide" AND "semaglutide"'
    assert requests[0].url.params['sort']=='@relevance'
    assert requests[1].url.params['query.cond']=='myelodysplastic syndromes'


def test_one_drug_cannot_fill_the_entire_comparison_or_hide_posted_results():
    def row(n):return tools.row('Study '+str(n),'https://clinicaltrials.gov/study/NCT'+str(n).zfill(8),'trial_record',{
        'study_id':'NCT'+str(n).zfill(8),'acronym':'Study'+str(n),'completion':{'date':'2027-01-01' if n==20 else '2027-09-01','type':'ESTIMATED'},
        'interventions':[],'results_present':n==20,'results_posted':{'date':'2024-01-01'} if n==20 else None})
    evidence,sources=research.assemble([{'records':[row(n) for n in range(1,13)]},{'records':[row(20)]}])
    answer=research.trial_comparison(evidence,[])
    assert 'NCT00000020' in answer and 'Posted 2024-01-01' in answer
    assert evidence[1]['facts']['study_id']=='NCT00000020'
    assert answer.index('NCT00000020')<answer.index('2027-01-01')


@pytest.mark.asyncio
async def test_label_retains_full_indications_and_late_heading_with_absent_boxed_warning():
    section='1 INDICATIONS AND USAGE 1.1 Melanoma KEYTRUDA is indicated. '+('Details of approved populations. '*700)+' 1.21 Ovarian Cancer KEYTRUDA is indicated for a defined population.'
    payload={'results':[{'set_id':'12345678-abcd-abcd-abcd-123456789abc','openfda':{'brand_name':['KEYTRUDA']},'indications_and_usage':[section]}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload))) as client:
        rows,_=await tools.labels(tools.ToolCall(tool='labels',query='KEYTRUDA'),client)
    facts=rows[0]['facts']
    assert len(facts['indications_and_usage'])>20000 and facts['sections']['indications_and_usage']['complete']
    assert facts['boxed_warning_present'] is False and 'Ovarian Cancer' in facts['indication_headings']
    rows[0]['citation']=1
    assert 'Ovarian Cancer' in research.label_summary(rows)


@pytest.mark.asyncio
async def test_orange_book_prioritises_innovator_patents_and_keeps_generic_products_separate():
    requests=[]
    def respond(request):
        requests.append(request)
        innovative='application_type:N' in request.url.params['search']
        return httpx.Response(200,json={'meta':{'last_updated':'2026-10-13','results':{'total':1}},'results':[{
            'product_number':'001','products':[{'application_number':'202155' if innovative else '210180','application_type':'N' if innovative else 'A','brand_name':'ELIQUIS' if innovative else 'APIXABAN'}],
            'patents':[{'patent_number':'1234567','expiration_date':'2031-01-01'}] if innovative else [],
            'exclusivity':[{'exclusivity_code':'NCE','exclusivity_expiration_date':'2017-01-01'}] if innovative else []}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        rows,coverage=await tools.orange_book(tools.ToolCall(tool='orange_book',query='apixaban'),client)
    assert len(requests)==2 and len(rows)==2
    assert rows[0]['facts']['patents'][0]['expiration_date']=='2031-01-01'
    assert rows[0]['facts']['launch_date_established'] is False
    assert 'no launch date is established' in coverage


def test_impact_prioritises_class_i_recall_and_positive_phase3_but_not_routine_class_ii():
    assert impact({'kind':'safety_alert'},{'details':{'classification':'Class II','recall_number':'D-1'}})['rating']=='Watch'
    assert impact({'kind':'safety_alert'},{'details':{'classification':'Class I','recall_number':'D-1'}})['rating']=='Material'
    assert impact({'kind':'press_release'},{'title':'Amgen reports positive Phase 3 results'})['rating']=='Material'
    assert impact({'kind':'press_release'},{'title':'Amgen announces Phase 3 trial initiation'})['rating']=='Watch'


def test_subject_links_do_not_follow_another_drug_in_the_indication_and_junk_is_filtered():
    aliases={'sunitinib':'sunitinib-id','imatinib':'imatinib-id','paroxetine':'paroxetine-id'}
    item={'source':'ema','title':'Sunitinib Accord','summary':'For patients treated with imatinib','details':{'ingredients':['sunitinib']}}
    assert mentioned_drugs(item,aliases)==['sunitinib-id']
    assert mentioned_drugs({'title':'Paroxetine update'},aliases)==['paroxetine-id']
    for title in ['Novel Drug Approvals for 2026','PFE - 6/28/2026 - EX. 99']:
        assert publication_item({'source':'fda_updates','title':title}) is None
    item={'id':'one','source':'company','date':'2026-10-14','organization':'Amgen','title':'Positive Phase 3 results','summary':'Forward-looking statements: Private Securities Litigation Reform Act'}
    assert publication_item(item)['summary']==''
    assert publication_key(item)==publication_key({**item,'id':'two'})


@pytest.mark.asyncio
async def test_tentative_approval_never_becomes_a_marketable_generic_approval():
    record={'application_number':'ANDA123456','products':[{'brand_name':'PITOLISANT','active_ingredients':[{'name':'PITOLISANT'}]}],
        'submissions':[{'submission_type':'ORIG','submission_number':'1','submission_status':'AP','submission_public_notes':'Tentative Approval','submission_status_date':'20261014'}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'results':[record]}))) as client:
        rows,_=await fda_records(client,'2026-10-01','2026-10-14')
    assert rows[0][2][0]['kind']=='fda_tentative_approval'
    assert 'marketing not authorised' in rows[0][0]['title']


@pytest.mark.asyncio
async def test_full_research_capacity_is_reported_as_busy_not_query_timeout(monkeypatch):
    class Full:
        async def acquire(self):raise TimeoutError()
        def release(self):raise AssertionError('An unacquired slot must not be released')
    monkeypatch.setattr(research,'slots',Full())
    events=[json.loads(e[6:]) async for e in research.research_stream('Pfizer obesity pipeline',[])]
    assert events[0]['code']=='pharma_busy' and 'busy' in events[0]['message']
    assert 'narrow' not in events[0]['message']
