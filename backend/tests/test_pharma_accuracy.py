"""Regression cases from the live analyst review of 14 October 2026; source shapes mirror real FDA/registry records."""
import json
from unittest.mock import AsyncMock
import httpx
import pytest
from src.services import pharma_research as research, pharma_research_tools as tools
from src.services.pharma_quality import check_absence, check_claims, check_dates, check_numbers, publication_item, strip_bibliography
from src.services.pharma_events import impact
from src.services.pharma_catalog import mentioned_drugs
from src.services.pharma_updates import tentative_submission
from src.services.llm_runtime import LLMProviderError

TODAY='2026-10-14'
CHECKMATE={'kind':'trial_record','citation':1,'url':'https://clinicaltrials.gov/study/NCT02998528','title':'CheckMate 816','facts':{
    'study_id':'NCT02998528','acronym':'CheckMate 816','primary_completion':{'date':'2021-09-08','type':'ACTUAL'},
    'completion':{'date':'2024-12-06','type':'ACTUAL'},'results_posted':{'date':'2022-09-28'},'results_present':True}}


def test_actual_dates_cannot_be_called_estimated_or_future_and_dates_must_be_sourced():
    for text in ['The full completion date is estimated to be December 6, 2024 [1].',
                 'CheckMate 816 is expected to complete on 2024-12-06 [1].',
                 'Results were posted on March 3, 2023 [1].']:
        with pytest.raises(LLMProviderError):check_dates(text,[CHECKMATE],TODAY)
    assert check_dates('CheckMate 816 completed on 6 December 2024 and results were posted in September 2022 [1].',[CHECKMATE],TODAY)
    upcoming={**CHECKMATE,'facts':{**CHECKMATE['facts'],'completion':{'date':'2027-09-28','type':'ESTIMATED'}}}
    with pytest.raises(LLMProviderError):check_dates('The study was completed on 2027-09-28 [1].',[upcoming],TODAY)
    assert check_dates('Study completion is expected on 2027-09-28 [1].',[upcoming],TODAY)
    assert check_dates('Completion was expected in December 2024 and occurred then [1].',[CHECKMATE],TODAY)


def test_decimals_and_percentages_must_come_from_evidence():
    evidence=[{'facts':{'values':[{'group':'Tirzepatide','value':'-2.37'},{'group':'Semaglutide','value':'-1.86'}],'share':'around 55% share'}}]
    assert check_numbers('HbA1c fell by -2.37 versus -1.86 [1]; Novo reported about 55% share [2].',evidence)
    with pytest.raises(LLMProviderError):check_numbers('The difference was 0.51 [1].',evidence)
    with pytest.raises(LLMProviderError):check_numbers('Tirzepatide reduced HbA1c 27% more [1].',evidence)
    assert check_numbers('In 2 Phase 3 trials and 12 records [1].',evidence)


def test_absence_needs_the_right_source_and_bibliographies_are_removed():
    with pytest.raises(LLMProviderError):check_absence('No recent FDA recalls were identified [1].',{'fda'})
    assert check_absence('No recent FDA recalls were identified [1].',{'recalls'})
    with pytest.raises(LLMProviderError):check_absence('No listed patents were found [1].',{'fda','labels'})
    text='Finding [1].\n\n#### References\n\n1. Smith J. A paper. 2026 [1].\n2. Jones K. Another. [2]'
    assert strip_bibliography(text)=='Finding [1].'
    assert strip_bibliography('Finding [1].\n\n[1], [2], [3]')=='Finding [1].'


def test_label_and_trial_facts_are_not_mistaken_for_prescribing_advice():
    for allowed in ['The label states that patients can use the pen at any time of day [1].',
                    'In MEDALIST, patients could switch to open-label treatment after progression [1].',
                    'Per the label, patients should take the tablet once daily [1].']:
        assert check_claims(allowed,[])
    for advice in ['Clinicians should consider a higher dose of semaglutide [1].','Doctors may consider higher doses [1].',
                   'Patients should consider switching to tirzepatide [1].']:
        with pytest.raises(LLMProviderError):check_claims(advice,[])
    present=[{'kind':'drug_label','facts':{'brand_names':['OZEMPIC'],'boxed_warning_present':True}}]
    with pytest.raises(LLMProviderError):check_claims('OZEMPIC does not have a boxed warning [1].',present)


def test_planner_wording_is_normalised_into_searchable_product_terms():
    assert tools.drug_terms('Mounjaro (tirzepatide)')[:2]==['Mounjaro','tirzepatide']
    assert tools.drug_terms('Mounjaro recent FDA approvals')==['Mounjaro']
    assert tools.drug_terms('insulin glargine')[0]=='insulin glargine'


@pytest.mark.asyncio
async def test_fda_search_falls_back_to_separate_terms_and_flags_tentative_products():
    application={'application_number':'ANDA218832','sponsor_name':'ANNORA','products':[{'brand_name':'PITOLISANT','marketing_status':'None (Tentative Approval)',
        'active_ingredients':[{'name':'PITOLISANT'}]}],'submissions':[{'submission_type':'ORIG','submission_number':'1','submission_status':'AP','submission_status_date':'20261008'}]}
    searches=[]
    def respond(request):
        searches.append(request.url.params['search'])
        return httpx.Response(200,json={'results':[application] if len(searches)>1 else []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        rows,_=await tools.fda(tools.ToolCall(tool='fda',query='Wakix generic (pitolisant)'),client)
    assert len(searches)==2 and '"pitolisant"' in searches[1]
    facts=rows[0]['facts']
    assert facts['marketing_authorised'] is False and facts['approved_submissions']==[] and facts['tentative_submissions'][0]['number']=='1'
    assert tentative_submission(application['submissions'][0],application['products'])
    assert not tentative_submission({'submission_type':'SUPPL','submission_status':'AP'},application['products'])


def test_label_indications_are_parsed_for_any_layout_with_the_boxed_warning_title():
    opdivo=('1 INDICATIONS AND USAGE OPDIVO is a PD-1 blocking antibody indicated for: Melanoma • adult patients (1.1) '
            '1.1 Unresectable or Metastatic Melanoma OPDIVO, as a single agent, is indicated. 1.5 Metastatic Non-Small Cell Lung Cancer • OPDIVO, in combination '
            '1.14 Gastric Cancer, Gastroesophageal Junction Cancer, and Esophageal Adenocarcinoma OPDIVO is indicated.')
    assert tools.indication_headings(opdivo,['OPDIVO'])==['Unresectable or Metastatic Melanoma','Metastatic Non-Small Cell Lung Cancer',
        'Gastric Cancer, Gastroesophageal Junction Cancer, and Esophageal Adenocarcinoma']
    jardiance=('1 INDICATIONS AND USAGE JARDIANCE is indicated: to reduce the risk of cardiovascular death and hospitalization for heart failure in adults with heart failure. '
               'as an adjunct to diet and exercise to improve glycemic control in adults with type 2 diabetes mellitus. JARDIANCE is a sodium-glucose co-transporter 2 (SGLT2) inhibitor indicated: To reduce ( 1 )')
    assert tools.indication_statements(jardiance)==['to reduce the risk of cardiovascular death and hospitalization for heart failure in adults with heart failure',
        'as an adjunct to diet and exercise to improve glycemic control in adults with type 2 diabetes mellitus']


@pytest.mark.asyncio
async def test_boxed_warning_title_is_reported_for_a_present_section():
    payload={'results':[{'set_id':'12345678-abcd-abcd-abcd-123456789abc','openfda':{'brand_name':['OZEMPIC']},
        'boxed_warning':['WARNING: RISK OF THYROID C-CELL TUMORS • In rodents, semaglutide causes thyroid C-cell tumors.'],
        'indications_and_usage':['1 INDICATIONS AND USAGE OZEMPIC is indicated: • as an adjunct to diet and exercise to improve glycemic control in adults. OZEMPIC is a GLP-1 receptor agonist indicated: ( 1 )']}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload))) as client:
        rows,_=await tools.labels(tools.ToolCall(tool='labels',query='Ozempic'),client)
    rows[0]['citation']=1
    summary=research.label_summary(rows)
    assert 'WARNING: RISK OF THYROID C-CELL TUMORS' in summary and 'as an adjunct to diet and exercise' in summary


def study(nct,arms,interventions,results=None,study_type='INTERVENTIONAL',allocation='RANDOMIZED'):
    return {'protocolSection':{'identificationModule':{'nctId':nct,'briefTitle':nct},'statusModule':{'overallStatus':'COMPLETED',
        'completionDateStruct':{'date':'2024-12-06','type':'ACTUAL'},'lastUpdatePostDateStruct':{'date':'2026-01-01'}},
        'designModule':{'phases':['PHASE3'],'studyType':study_type,'designInfo':{'allocation':allocation}},
        'armsInterventionsModule':{'armGroups':[{'label':label,'interventionNames':names} for label,names in arms],
            'interventions':[{'name':name,'type':'DRUG','armGroupLabels':[label for label,names in arms if 'Drug: '+name in names]} for name in interventions]}},
        **({'resultsSection':results} if results else {})}


RESULTS={'outcomeMeasuresModule':{'outcomeMeasures':[{'type':'PRIMARY','title':'Change in HbA1c','timeFrame':'Week 40','paramType':'LEAST_SQUARES_MEAN',
    'unitOfMeasure':'Percentage of HbA1c','groups':[{'id':'OG000','title':'Tirzepatide'},{'id':'OG001','title':'Semaglutide'}],
    'classes':[{'categories':[{'measurements':[{'groupId':'OG000','value':'-2.37','spread':'0.048'},{'groupId':'OG001','value':'-1.86','spread':'0.048'}]}]}],
    'analyses':[{'groupIds':['OG000','OG001'],'paramType':'LS Mean Difference','paramValue':'-0.51','ciPctValue':'95','ciLowerLimit':'-0.64','ciUpperLimit':'-0.38','pValue':'<0.001'}]}]}}


@pytest.mark.asyncio
async def test_direct_comparison_needs_separate_single_drug_arms_and_posted_results_are_read():
    studies=[
        study('NCT00000001',[('Combination','Drug: Cagrilintide|Drug: Semaglutide'.split('|')),('Tirzepatide',['Drug: Tirzepatide'])],['Cagrilintide','Semaglutide','Tirzepatide']),
        study('NCT00000002',[('Tirzepatide',['Drug: Tirzepatide','Drug: Metformin']),('Semaglutide',['Drug: Semaglutide','Drug: Metformin'])],['Tirzepatide','Semaglutide','Metformin'],RESULTS),
        study('NCT00000003',[('Tirzepatide cohort',['Drug: Tirzepatide']),('Semaglutide cohort',['Drug: Semaglutide'])],['Tirzepatide','Semaglutide'],study_type='OBSERVATIONAL',allocation=None)]
    def respond(request):
        if 'clinicaltrials.gov' in str(request.url):return httpx.Response(200,json={'studies':studies,'totalCount':3})
        return httpx.Response(200,json={'results':[]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        rows,coverage=await tools.trials(tools.ToolCall(tool='trials',query='tirzepatide',compare_with='semaglutide'),client)
    designs={r['facts']['study_id']:r['facts']['comparison_design'] for r in rows}
    assert designs['NCT00000002']['direct_comparison'] and designs['NCT00000002']['randomized_trial']
    assert designs['NCT00000001']['direct_comparison'] is False
    assert designs['NCT00000003']['direct_comparison'] and not designs['NCT00000003']['randomized_trial']
    assert rows[0]['facts']['study_id']=='NCT00000002' and 'values were read for 1' in coverage
    for row,citation in zip(rows,(1,2,3)):row['citation']=citation
    text=research.trial_comparison(rows,[])
    assert 'Randomized head-to-head trials in this sample' in text and 'observational or non-randomized' in text
    assert 'Tirzepatide: -2.37 ± 0.048' in text and 'LS Mean Difference -0.51 (95% CI -0.64 to -0.38), p <0.001' in text.replace('\\','')
    assert research.verified_answer(text,rows,[{}]*3,deterministic=True)


@pytest.mark.asyncio
async def test_company_therapy_area_and_recalls_reach_the_right_sources():
    seen=[]
    def respond(request):
        seen.append(request.url)
        if 'enforcement' in str(request.url):
            return httpx.Response(200,json={'meta':{'results':{'total':91}},'results':[{'recall_number':'D-0412-2025','classification':'Class II','status':'Ongoing',
                'report_date':'20250416','recall_initiation_date':'20250310','reason_for_recall':'CGMP Deviations','recalling_firm':'Glenmark','product_description':'Metformin ER 1000 mg'}]})
        return httpx.Response(200,json={'studies':[],'totalCount':0})
    plan=research.explicit_plan('What has Novartis announced recently about its cardiovascular pipeline?')
    assert plan.calls[0].search_by=='sponsor' and plan.calls[0].condition=='cardiovascular'
    recall_plan=research.explicit_plan('Were there any recent FDA recalls or safety alerts for metformin?')
    assert recall_plan.calls[0].tool=='recalls' and recall_plan.calls[0].query=='metformin'
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await tools.trials(plan.calls[0],client)
        rows,coverage=await tools.recalls(recall_plan.calls[0],client)
    assert '"heart failure"' in seen[0].params['query.cond'] and 'StudyType]INTERVENTIONAL' in seen[0].params['filter.advanced']
    assert rows[0]['facts']['report_date']=='2025-04-16' and '91 FDA drug enforcement' in coverage
    rows[0]['citation']=1
    summary=research.recall_summary(rows,[{'coverage':coverage}])
    assert '| 2025-04-16 [1] | Class II |' in summary and 'not recall-initiation dates' in summary


def test_direct_comparison_wording_without_head_to_head_uses_a_joint_search():
    chosen=research.explicit_plan('Which Phase 3 trials directly compare zanubrutinib and ibrutinib, and have results been posted?')
    assert chosen.calls[0].compare_with=='ibrutinib' and chosen.calls[0].phase=='PHASE3'
    chosen=research.explicit_plan('Is there a trial comparing tirzepatide with semaglutide?')
    assert chosen.calls[0].query=='tirzepatide' and chosen.calls[0].compare_with=='semaglutide'
    # A program comparison stays separate.
    chosen=research.explicit_plan('Compare Phase 3 luspatercept vs imetelstat in lower-risk MDS')
    assert [c.compare_with for c in chosen.calls]==[None,None]


def test_planner_formatting_is_repaired_but_unsafe_tools_are_still_dropped():
    plan=research.parse_plan('Here is the plan: {"intent":"research","calls":[{"tool":"clinical_trials","query":"donanemab","phase":"Phase 3"},'
        '{"tool":"fda","query":"donanemab","scope":"applications"},{"tool":"shell","query":"ls"}],"clarification":""} Done.')
    assert [(c.tool,c.phase,c.scope) for c in plan.calls]==[('trials','PHASE3','regulatory'),('fda',None,'regulatory')]
    assert research.parse_plan('{"intent":"record","calls":[{"tool":"fda","query":"olanzapine"}]}').intent=='research'
    with pytest.raises(ValueError):research.parse_plan('{"intent":"research","calls":[{"tool":"shell","query":"ls"}]}')


@pytest.mark.asyncio
async def test_invalid_plans_are_retried_once_then_follow_ups_use_the_conversation(monkeypatch):
    model=AsyncMock(return_value={'text':'not json','model':'amazon.nova-pro-v1:0'})
    monkeypatch.setattr(research,'complete',model)
    history=[{'role':'user','content':'List donanemab Phase 3 trials'},{'role':'assistant','content':'NCT04437511 posted results [1].'}]
    chosen=await research.plan('Which of those posted results most recently?',history,None)
    assert chosen.intent=='conversation' and model.await_count==2
    chosen=await research.plan('Tell me something',[],None)
    assert chosen.intent=='clarify'


def test_feed_rules_for_setbacks_refusals_formulations_registrations_and_publications():
    setback=impact({'kind':'press_release'},{'title':'Company X Phase 3 trial did not meet its primary endpoint'})
    assert setback['rating']=='Material' and 'setback' in setback['rationale'] and 'positive' not in setback['rationale']
    refusal=impact({'kind':'fda_announcement'},{'title':'FDA declines approval of drug X with a complete response letter'})
    assert refusal['rating']=='Material' and 'refusal' in refusal['rationale']
    assert impact({'kind':'fda_original_approval'},{'summary':'Teva. Application NDA219007, submission ORIG 1. Type 5 - New Formulation or New Manufacturer',
        'details':{'application':'NDA219007'}})['rating']=='Watch'
    assert impact({'kind':'fda_original_approval'},{'summary':'Type 1 - New Molecular Entity','details':{'application':'NDA219999'}})['rating']=='Material'
    assert impact({'kind':'trial_registered'},{'evidence':{'phases':['PHASE1'],'sponsor_class':'OTHER'}})['rating']=='None'
    assert impact({'kind':'trial_registered'},{'evidence':{'phases':['PHASE3'],'sponsor_class':'OTHER'}})['rating']=='Watch'
    for title in ['Notable Approvals | Drugs | FDA','Fast Track Approvals | FDA','Oncology (Cancer)/Hematologic Malignancies Approval Notifications | FDA']:
        assert publication_item({'source':'fda_updates','title':title,'summary':'x'}) is None
    assert publication_item({'source':'fda_updates','title':'FDA Approves First Gene Therapy for Sanfilippo','summary':'x'})
    for summary in ['product. Further, preclinical results do not guarantee safe and effective performance of product candidates',
                    'Amgen Logo Amgen Logo Overview Research & Development','launch dates, as well as the possibility of unfavorable new clinical data']:
        assert publication_item({'source':'company','title':'Positive Phase 3','summary':summary})['summary']==''
    aliases={'rimegepant':'rimegepant-id','dupilumab':'dupilumab-id'}
    assert mentioned_drugs({'details':{'interventions':['Rimegepant 75 mg ODT']}},aliases)==['rimegepant-id']


def test_selected_record_and_application_with_one_url_get_separate_references():
    url='https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo=218832'
    selected={'title':'PITOLISANT','url':url,'kind':'selected_record','facts':{'event':'x'},'excerpt':''}
    application=tools.row('ANDA218832','https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo=218832','fda_application',{'application':'ANDA218832'})
    evidence,sources=research.assemble([{'records':[application]}],selected)
    assert [r['citation'] for r in evidence]==[1,2] and len(sources)==2


@pytest.mark.asyncio
@pytest.mark.parametrize('summary_ok',[True,False])
async def test_source_rendered_answers_get_a_verified_key_answer_or_none(monkeypatch,summary_ok):
    row=tools.row('SURPASS-2','https://clinicaltrials.gov/study/NCT03987919','trial_record',{'study_id':'NCT03987919','acronym':'SURPASS-2',
        'phases':['PHASE3'],'status':'COMPLETED','results_posted':{'date':'2022-02-14'},'results_present':True,
        'completion':{'date':'2021-02-15','type':'ACTUAL'},'primary_results':[{'measure':'Change in HbA1c','values':[{'group':'Tirzepatide','value':'-2.37'}]}]})
    monkeypatch.setattr(research,'plan',AsyncMock(return_value=research.Plan(intent='research',calls=[tools.ToolCall(tool='trials',query='SURPASS-2')])))
    monkeypatch.setattr(research,'execute',AsyncMock(return_value={'tool':'trials','label':'Trials','status':'available','records':[row],'coverage':'Sample.'}))
    good='SURPASS-2 completed on 2021-02-15 and posted an HbA1c change of -2.37 for tirzepatide [1].'
    bad='SURPASS-2 showed a 0.9 point advantage and will complete on 2021-02-15 [1].'
    model=AsyncMock(return_value={'text':good if summary_ok else bad,'model':'amazon.nova-pro-v1:0'})
    monkeypatch.setattr(research,'complete',model)
    events=[json.loads(e[6:]) async for e in research.research_stream('What happened in SURPASS-2?',[])]
    answer=next(e['content'] for e in events if e['type']=='token')
    assert events[-1]['type']=='done' and 'Posted primary results' in answer
    assert ('### Key answer' in answer)==summary_ok and '0.9 point' not in answer
    assert model.await_count==(1 if summary_ok else 2)


@pytest.mark.asyncio
async def test_unavailable_interpretation_shows_verified_source_facts_instead_of_an_error(monkeypatch):
    row=tools.row('ANDA218832','https://www.fda.gov/drugs/example','fda_application',{'application':'ANDA218832','marketing_authorised':False,'approved_submissions':[]})
    monkeypatch.setattr(research,'plan',AsyncMock(return_value=research.Plan(intent='research',calls=[tools.ToolCall(tool='fda',query='pitolisant')])))
    monkeypatch.setattr(research,'execute',AsyncMock(return_value={'tool':'fda','label':'FDA','status':'available','records':[row],'coverage':'Sample.'}))
    monkeypatch.setattr(research,'complete',AsyncMock(side_effect=LLMProviderError('The Pharma analysis could not be completed. Please retry shortly.')))
    events=[json.loads(e[6:]) async for e in research.research_stream('Is pitolisant generic approved?',[])]
    answer=next(e['content'] for e in events if e['type']=='token')
    assert events[-1]['type']=='done' and 'tentative approval' in answer and not any(e['type']=='error' for e in events)
