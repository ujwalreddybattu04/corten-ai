"""Follow-up retrieval and the observed EMA chronology failure."""
import pytest
from unittest.mock import AsyncMock
from src.services import pharma_research as research
from src.services.pharma_quality import check_regulatory_history
from src.services.pharma_bedrock_analysis import validate_answer
from src.services.llm_runtime import LLMProviderError

def selected():
    return {'title':'Revatio · Post-authorisation decision','url':'https://www.ema.europa.eu/en/medicines/human/EPAR/revatio','facts':{'details':{
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
