"""Follow-up retrieval and the observed EMA chronology failure."""
import pytest
from unittest.mock import AsyncMock
from src.services import pharma_research as research
from src.services.pharma_quality import check_regulatory_history
from src.services.pharma_bedrock_analysis import validate_answer
from src.services.llm_runtime import LLMProviderError

def selected():
    return {'title':'Revatio · Post-authorisation decision','date':'2026-10-13','url':'https://www.ema.europa.eu/en/medicines/human/EPAR/revatio','kind':'selected_record','citation':1,'facts':{'event':{'kind':'ema_post_authorisation_decision'},'details':{
        'ema_product_number':'EMEA/H/C/000638','ingredients':['sildenafil'],'latest_procedure':'VR/0000386049',
        'initial_authorisation_date':'2005-10-28','indication':'Current treatment of adults and children.'}}}

@pytest.mark.parametrize('question,tool,term',[
    ('Find EMA assessment documents for Revatio, procedure VR/0000386049.','official_search','VR/0000386049'),
    ('Find current EMA product information for Revatio.','official_search','EMA'),
    ('Find current FDA labeling for sildenafil.','labels','sildenafil'),
    ('Find registered clinical trials for sildenafil.','trials','sildenafil'),
    ('Find published clinical evidence for sildenafil.','literature','sildenafil'),
    ('Show the verified regulatory timeline for sildenafil.','drug_history','sildenafil'),
])
@pytest.mark.asyncio
async def test_clear_follow_up_runs_the_right_tool_without_a_planner_call(monkeypatch,question,tool,term):
    model=AsyncMock();monkeypatch.setattr(research,'complete',model)
    plan=await research.plan(question,[],selected())
    assert plan.intent=='research' and plan.calls[0].tool==tool and term in plan.calls[0].query
    assert model.await_count==0

def test_compound_and_other_drug_questions_are_left_to_the_contextual_planner():
    assert research.record_lookup_plan('Find current labeling and clinical evidence for sildenafil.',selected()) is None
    assert research.record_lookup_plan('Find current labeling for Keytruda.',selected()) is None
    assert research.record_lookup_plan('What does the original regulatory record establish?',selected()) is None


@pytest.mark.asyncio
async def test_historical_population_question_stays_attached_to_source_not_prior_assistant(monkeypatch):
    model=AsyncMock();monkeypatch.setattr(research,'complete',model)
    plan=await research.plan('Does the current indication establish patients covered by the original authorisation?',
        [{'role':'assistant','content':'Unverified original population claim'}],selected())
    assert plan.intent=='record' and model.await_count==0
    answer=research.regulatory_record_answer('Does the current indication establish patients covered by the original authorisation?',plan,[selected()],[])
    assert '**No.**' in answer and '2005-10-28' in answer


def test_original_record_answer_leads_with_selected_event_not_old_indications():
    answer=research.regulatory_record_answer('What does the original regulatory record establish?',research.Plan(intent='record'),[selected()],[])
    assert '2026-10-13' in answer and 'VR/0000386049' in answer and 'later decision' in answer
    assert '2005' not in answer and 'children' not in answer


@pytest.mark.parametrize('status',['available','empty','unavailable'])
def test_document_lookup_reports_search_outcome_instead_of_repeating_record_summary(status):
    lookup=research.Plan(intent='research',calls=[research.ToolCall(tool='official_search',query='Revatio EMA procedure VR/0000386049',scope='regulatory')])
    unrelated={'kind':'indexed_regulatory','citation':2,'title':'Mysildecard assessment','url':'https://www.ema.europa.eu/en/documents/assessment-report/mysildecard.pdf','excerpt':'The reference product is Revatio.'}
    answer=research.regulatory_record_answer('Find EMA assessment documents for Revatio, procedure VR/0000386049.',lookup,[selected(),unrelated],[{'tool':'official_search','status':status}])
    assert ('did not locate' in answer if status!='unavailable' else 'unavailable' in answer)
    assert 'Mysildecard' not in answer and 'children' not in answer


def test_exact_document_match_stays_an_excerpt_not_a_claim_to_have_read_the_document():
    lookup=research.record_lookup_plan('Find EMA assessment documents for Revatio.',selected())
    matching={'kind':'indexed_regulatory','citation':2,'title':'Revatio procedure VR/0000386049','url':'https://www.ema.europa.eu/en/documents/assessment-report/revatio.pdf','excerpt':'VR/0000386049'}
    answer=research.regulatory_record_answer('Find EMA assessment documents for Revatio.',lookup,[selected(),matching],[{'tool':'official_search','status':'available'}])
    assert 'explicitly mention' in answer and 'full procedure documents have not been reviewed' in answer and '[2]' in answer


@pytest.mark.parametrize('draft',[
    'This decision updates the product information for Revatio [1].',
    'This decision updates the product information, but the specific changes are not detailed in this snapshot [1].',
])
def test_later_decision_does_not_prove_a_product_information_update(draft):
    with pytest.raises(LLMProviderError):
        check_regulatory_history(draft,[selected()])
    valid='The procedure does not establish the exact changes to product information [1].'
    assert check_regulatory_history(valid,[selected()])==valid
    qualified='It is unclear whether the decision updates product information [1].'
    assert check_regulatory_history(qualified,[selected()])==qualified

def test_failed_planner_never_pretends_an_external_lookup_was_a_local_summary():
    plan=research.fallback_plan('Find the latest competitor patent settlements.',[],selected())
    assert plan.intent=='clarify'
    plan=research.fallback_plan('Find the current product information for this medicine.',[],selected())
    assert plan.intent=='research'

@pytest.mark.parametrize('text',[
    'Revatio was initially authorised on October 28, 2005 for the treatment of adults and children [1].',
    'The original authorisation established its use in adults and children [1].',
])
def test_current_indication_cannot_be_projected_back_to_initial_approval(text):
    evidence=[{'kind':'selected_record','facts':selected()['facts']}]
    with pytest.raises(LLMProviderError):check_regulatory_history(text,evidence)
    item={'details':selected()['facts']['details']}
    with pytest.raises(LLMProviderError):validate_answer(text,item,'question')
    with pytest.raises(LLMProviderError):check_regulatory_history(text,[*evidence,{'kind':'publication','facts':{}}])

@pytest.mark.parametrize('text',[
    'The initial authorisation date is October 28, 2005 [1]. The current indication lists adults and children [1].',
    'The current indication does not establish which populations were covered by the original authorisation [1].',
    'The selected event is a post-authorisation decision; the specific change is not detailed in this record [1].',
])
def test_qualified_current_vs_historical_descriptions_remain_valid(text):
    assert check_regulatory_history(text,[{'kind':'selected_record','facts':selected()['facts']}])==text
