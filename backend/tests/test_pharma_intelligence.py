"""Evidence, cost and source trust boundaries for the shared intelligence path."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import pytest
from src.services.pharma_catalog import AliasMatcher, drug_identity, unique_aliases, mentioned_drugs
from src.services.pharma_sources import rss_records, ema_records, safe_source_url, publication_date, publisher_feed, drug_recalls, fda_records
from src.services.pharma_bedrock_analysis import evidence_messages, validate_answer
from src.services.llm_runtime import LLMProviderError
from src.services.pharma_bedrock_analysis import source_summary

spec=importlib.util.spec_from_file_location("bedrock_gateway",Path(__file__).resolve().parents[2]/"deploy/aws/bedrock-gateway.py")
gateway=importlib.util.module_from_spec(spec);spec.loader.exec_module(gateway)

def test_verified_alias_and_ambiguous_names_and_combinations():
    drug=drug_identity(["luspatercept"])
    assert drug_identity(["luspatercept-aamt"])==drug
    assert drug_identity(["luspatercept","aspirin"])!=drug
    aliases=unique_aliases([("Reblozyl",drug),("common",drug),("common","other")])
    assert "common" not in aliases
    assert mentioned_drugs({"title":"Reblozyl update"},aliases)==[drug]
    assert mentioned_drugs({"title":"Reblozylous update"},aliases)==[]


def test_literal_matcher_preserves_overlaps_unicode_and_word_boundaries():
    aliases={"example":"single","example acetate":"salt","药物":"chinese","x.y":"literal"}
    matcher=AliasMatcher(aliases)
    assert matcher.match("example acetate / 药物 / x.y")==["chinese","literal","salt","single"]
    assert matcher.match("examples / xay / 药物名 / _example")==[]
    assert mentioned_drugs({"title":"ＥＸＡＭＰＬＥ   acetate"},aliases,matcher)==["salt","single"]

def test_source_dates_urls_and_xml_fail_closed():
    assert not publication_date("unknown")
    assert not safe_source_url("https://fda.gov.evil.example/news",("fda.gov",))
    assert not safe_source_url("https://user@fda.gov/news",("fda.gov",))
    with pytest.raises(ValueError):rss_records(b'<!DOCTYPE x [<!ENTITY y "bad">]><rss/>',"news",(),"2026-01-01","2026-12-31")
    xml=b'<rss><channel><item><title>Drug update</title><link>https://www.fda.gov/drugs/news</link><pubDate>Wed, 14 Oct 2026 00:00:00 GMT</pubDate><description>Tablet recall</description></item><item><title>Undated</title></item></channel></rss>'
    rows,meta=rss_records(xml,"fda_safety",("fda.gov",),"2026-10-01","2026-10-14")
    assert len(rows)==1 and rows[0][2][0]["kind"]=="safety_alert" and meta["undated_excluded"]==1


@pytest.mark.asyncio
async def test_publisher_redirects_stay_on_verified_hosts_and_reject_abuse_pages():
    import httpx
    requests=[]
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(302,headers={'Location':'/apology_objects/abuse-detection-apology.html'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):await publisher_feed(client,'https://www.fda.gov/rss.xml',('fda.gov',))
    assert len(requests)==1


@pytest.mark.asyncio
async def test_drug_recall_report_date_is_not_initiation_and_devices_are_excluded():
    import httpx
    record={'product_type':'Drugs','recall_number':'D-0001-2026','report_date':'20261014','recall_initiation_date':'20260912','classification':'Class II','status':'Ongoing','product_description':'Example tablets','reason_for_recall':'Incorrect label','recalling_firm':'Example'}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'results':[record,{**record,'product_type':'Devices','recall_number':'Z-0001-2026'}]}))) as client:
        rows,meta=await drug_recalls(client,'2026-10-01','2026-10-14')
    assert len(rows)==1 and rows[0][0]['date']=='2026-10-14' and rows[0][0]['details']['recall_initiation_date']=='2026-09-12'
    assert rows[0][0]['date_label']=='FDA enforcement report date' and meta['method']=='openfda_drug_enforcement'


@pytest.mark.asyncio
async def test_generic_supplement_does_not_become_an_original_generic_approval():
    import httpx
    record={'application_number':'ANDA123456','products':[{'brand_name':'Example','active_ingredients':[{'name':'Example ingredient'}]}],
            'submissions':[{'submission_type':kind,'submission_number':str(n),'submission_status':'AP','submission_status_date':'20261014'} for n,kind in enumerate(['ORIG','SUPPL'])]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'results':[record]}))) as client:
        rows,_=await fda_records(client,'2026-10-01','2026-10-14')
    assert [r[2][0]['kind'] for r in rows]==['fda_generic_approval','fda_supplemental_approval']
    assert 'FDA generic approval' in rows[0][0]['title']

def test_ema_positive_opinion_is_not_authorisation():
    record={"category":"human","name_of_medicine":"Example","ema_product_number":"EMEA/H/C/123",
        "medicine_url":"https://www.ema.europa.eu/en/medicines/human/EPAR/example","active_substance":"example substance",
        "medicine_status":"Opinion","opinion_status":"Positive","opinion_adopted_date":"2026-10-10"}
    rows,aliases,_=ema_records([record],"2026-10-01","2026-10-14")
    assert rows[0][2][0]["kind"]=="ema_opinion" and aliases
    record.update(medicine_status="Authorised",european_commission_decision_date="2026-10-12",marketing_authorisation_date="12/10/2026")
    assert ema_records([record],"2026-10-01","2026-10-14")[0][0][2][0]["kind"]=="ema_authorisation"
    record.update(marketing_authorisation_date="28/10/2005",european_commission_decision_date="13/10/2026")
    assert ema_records([record],"2026-10-01","2026-10-14")[0][0][2][0]["kind"]=="ema_post_authorisation_decision"

def test_durable_budget_concurrency_and_settlement(tmp_path):
    ledger=gateway.Ledger(tmp_path/"ledger.sqlite3",limit=150_000_000)
    def reserve(_):
        try:return ledger.reserve(30_000_000,"2026-10")
        except gateway.BudgetExceeded:return None
    with ThreadPoolExecutor(max_workers=12) as pool:ids=list(pool.map(reserve,range(12)))
    assert len([i for i in ids if i])==3
    saved=next(i for i in ids if i);ledger.settle(saved,10_000_000);ledger.settle(saved,0)
    with ledger.connect() as db:assert db.execute("SELECT charge FROM requests WHERE id=?",(saved,)).fetchone()[0]==10_000_000
    assert ledger.reserve(30_000_000,"2026-11")
    with pytest.raises(ValueError):ledger.settle(next(i for i in ids if i!=saved and i),40_000_000)

def test_gateway_restricts_models_tools_and_partial_answers(tmp_path,monkeypatch):
    request={"modelId":"amazon.nova-pro-v1:0","system":[{"text":"Source only"}],"messages":[{"role":"user","content":[{"text":"Question"}]}],"inferenceConfig":{"maxTokens":512}}
    assert gateway.validated_request(request)["inferenceConfig"]["temperature"]==.1
    with pytest.raises(ValueError):gateway.validated_request({**request,"toolConfig":{}})
    with pytest.raises(ValueError):gateway.validated_request({**request,"modelId":"global.anthropic.claude"})
    def fake(operation,body,timeout):
        if operation=="count-tokens":return {"inputTokens":100}
        return {"stopReason":"max_tokens","usage":{"inputTokens":100,"outputTokens":512},"output":{"message":{"content":[{"text":"cut off"}]}}}
    monkeypatch.setattr(gateway,"aws",fake)
    with pytest.raises(ValueError):gateway.complete(request,gateway.Ledger(tmp_path/"ledger.sqlite3"))

def test_shared_brief_prompt_excludes_caller_question_history_and_mode():
    item={"id":"event:one","title":"Baseline","summary":"Existing study","url":"https://clinicaltrials.gov/study/NCT12345678","event":{"kind":"record_observed"},"impact":{"rating":"None"},"tags":["ACTIVE_NOT_RECRUITING"]}
    source={"name":"ClinicalTrials.gov","status":"available"}
    one=evidence_messages(item,source,{"protocolSection":{}},"private question",[{"role":"user","content":"private history"}],"brief","pro")
    two=evidence_messages(item,source,{"protocolSection":{}},"another",[],"brief","think")
    assert one==two and "private question" not in json.dumps(one) and "private history" not in json.dumps(one)
    assert "ACTIVE_NOT_RECRUITING" not in one[1]["content"]
    invalid="Existing trial. [1]\n### Why it matters\nRecruitment has ended.\n### Forecast impact\n**None** [1]\n### What to watch\n- Check results."
    with pytest.raises(LLMProviderError):validate_answer(invalid,item,"brief")
    with pytest.raises(LLMProviderError):validate_answer("Wrong NCT87654321 [99]",item,"question")


def test_source_summary_preserves_stop_reason_and_exact_rule_rating():
    item={"title":"Example study","date":"2026-10-14","date_label":"Status change posted","event":{"kind":"trial_stopped","label":"Trial terminated","reason":"Enrollment target could not be met.","changes":[]},
        "impact":{"rating":"Material","rationale":"Review the pipeline-risk event."}}
    answer=source_summary(item)
    assert "Enrollment target could not be met." in answer and "**Material**" in answer
    assert "demand" not in answer and "efficacy" not in answer


@pytest.mark.asyncio
async def test_archived_record_analysis_is_not_limited_to_the_recent_feed(monkeypatch):
    from fastapi import FastAPI
    import httpx
    from unittest.mock import AsyncMock
    from src.api.v1 import pharma
    from src.api.deps import get_current_user_id
    from src.services.pharma_analysis import record_fingerprint
    app=FastAPI();app.include_router(pharma.router,prefix="/pharma")
    app.dependency_overrides[get_current_user_id]=lambda:"owner"
    item={"id":"event:archived","version":"a"*64}
    monkeypatch.setattr(pharma.settings,"PHARMA_INTELLIGENCE_ENABLED",True)
    monkeypatch.setattr(pharma.pharma_repository,"get_record",AsyncMock(return_value={"item":item,"source":{"name":"Registry"}}))
    feed=AsyncMock(side_effect=AssertionError("Archive must not reload the feed"))
    monkeypatch.setattr(pharma.pharma_updates_service,"get_feed",feed)
    async def stream(*args):yield 'data: {"type":"done"}\n\n'
    monkeypatch.setattr(pharma,"stream_analysis",stream)
    body={"record_id":item["id"],"record_fingerprint":json.dumps(record_fingerprint(item)),"kind":"brief","query":"Brief"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        assert (await client.post("/pharma/analysis/stream",json=body)).status_code==200
        assert (await client.post("/pharma/analysis/stream",json={**body,"record_fingerprint":"[]"})).status_code==409
    feed.assert_not_awaited()
