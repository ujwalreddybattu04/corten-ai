"""Clinical record updates must never become fabricated milestones."""
from copy import deepcopy
import pytest
from src.services.pharma_events import annotate, study_facts, trial_events

def study(status="RECRUITING"):
    return {"protocolSection":{"identificationModule":{"nctId":"NCT12345678"},
        "statusModule":{"overallStatus":status,"lastUpdatePostDateStruct":{"date":"2026-10-14"},
            "studyFirstPostDateStruct":{"date":"2020-01-01"},
            "primaryCompletionDateStruct":{"date":"2027-06","type":"ESTIMATED"}},
        "designModule":{"phases":["PHASE3"]},"sponsorCollaboratorsModule":{"leadSponsor":{"class":"INDUSTRY"}}}}

def test_first_snapshot_does_not_invent_completion_or_stopping():
    events=trial_events(study("TERMINATED"))
    assert all(e["kind"] not in {"trial_stopped","completion_date_moved","trial_completed","results_posted"} for e in events)
    assert any(e["kind"]=="trial_registered" and e["date"]=="2020-01-01" for e in events)
    assert events[0]["kind"]=="record_observed"

def test_routine_update_and_qualifier_change_are_not_date_moves():
    before=study();after=deepcopy(before)
    after["protocolSection"]["statusModule"]["primaryCompletionDateStruct"]["type"]="ACTUAL"
    events=trial_events(after,before)
    assert [e["kind"] for e in events]==["record_updated"]
    item=annotate({"evidence":study_facts(after)},events,"version")
    assert item["impact"]["rating"]=="None"

def test_stop_and_completion_change_preserve_reason_and_partial_dates():
    before=study();after=deepcopy(before)
    status=after["protocolSection"]["statusModule"]
    status.update(overallStatus="TERMINATED",whyStopped="Enrollment could not meet the required sample size.")
    status["primaryCompletionDateStruct"]={"date":"2028-01","type":"ESTIMATED"}
    events=trial_events(after,before)
    assert {e["kind"] for e in events}=={"trial_stopped","completion_date_moved"}
    stopped=next(e for e in events if e["kind"]=="trial_stopped")
    assert stopped["reason"]==status["whyStopped"] and stopped["date_label"]=="Status change posted"
    moved=next(e for e in events if e["kind"]=="completion_date_moved")
    assert moved["changes"][0]["before"]=={"date":"2027-06","type":"ESTIMATED"}
    assert annotate({"evidence":study_facts(after)},events,"hash")["impact"]["rating"]=="Material"

def test_completed_does_not_imply_success():
    before=study();after=study("COMPLETED")
    event=trial_events(after,before)[0]
    assert event["kind"]=="trial_completed"
    assert annotate({"evidence":study_facts(after)},[event],"hash")["impact"]["rating"]=="Watch"

def test_results_posted_once_and_changes_detected_separately():
    before=study();after=deepcopy(before)
    after["protocolSection"]["statusModule"]["resultsFirstPostDateStruct"]={"date":"2026-10-14"}
    after["resultsSection"]={"outcomeMeasuresModule":{"outcomeMeasures":[{"title":"Primary outcome"}]}}
    assert [e["kind"] for e in trial_events(after,before)]==["results_posted"]
    changed=deepcopy(after);changed["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]["title"]="Corrected outcome"
    assert [e["kind"] for e in trial_events(changed,after)]==["results_updated"]

def test_different_studies_cannot_be_compared():
    other=study();other["protocolSection"]["identificationModule"]["nctId"]="NCT87654321"
    with pytest.raises(ValueError):trial_events(study(),other)
