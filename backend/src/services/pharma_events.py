"""Detect dated pharma events from source facts and immutable record versions."""
import hashlib
import json
import re
from datetime import date

RULE_VERSION = "events-1"
STOPPED = {"TERMINATED", "WITHDRAWN", "SUSPENDED"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def posted_date(value):
    if isinstance(value, dict):
        value = value.get("date")
    try:
        return date.fromisoformat(value).isoformat() if isinstance(value, str) else None
    except ValueError:
        return None


def study_facts(study):
    """Preserve partial completion dates and estimated/actual qualifiers verbatim."""
    protocol = study.get("protocolSection") or {}
    status = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    sponsor = (protocol.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}
    identification = protocol.get("identificationModule") or {}
    nct = identification.get("nctId")
    if not isinstance(nct, str) or not re.fullmatch(r"NCT\d{8}", nct):
        raise ValueError("Invalid trial identifier")
    if status.get("whyStopped") is not None and (not isinstance(status["whyStopped"],str) or len(status["whyStopped"])>2000):
        raise ValueError("Invalid stop reason")
    dates = {name: status.get(name) or {} for name in ("primaryCompletionDateStruct", "completionDateStruct")}
    for value in dates.values():
        if not isinstance(value, dict) or value.get("date") and not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", str(value["date"])):
            raise ValueError("Invalid completion date")
        if value.get("date"):
            parts=str(value["date"]).split("-")
            date.fromisoformat("-".join(parts+["01"]*(3-len(parts))))
    return {"study_id": nct, "status": status.get("overallStatus"), "why_stopped": status.get("whyStopped"),
        "first_posted": posted_date(status.get("studyFirstPostDateStruct")),
        "results_posted": posted_date(status.get("resultsFirstPostDateStruct")),
        "updated": posted_date(status.get("lastUpdatePostDateStruct")),
        "phases": design.get("phases") or [], "sponsor_class": sponsor.get("class"),
        "primary_completion": dates["primaryCompletionDateStruct"], "completion": dates["completionDateStruct"],
        "results_available": bool(study.get("resultsSection")),
        "results_version": digest(study["resultsSection"]) if study.get("resultsSection") else None}


def trial_events(current, previous=None):
    facts = study_facts(current)
    before = study_facts(previous) if previous else None
    if before and before["study_id"] != facts["study_id"]:
        raise ValueError("Cannot compare different studies")
    events = []
    def add(kind, label, when, meaning, changes=None, reason=None):
        if when:
            events.append({"kind": kind, "label": label, "date": when, "date_label": meaning,
                "changes": changes or [], "reason": reason, "baseline": before is None})
    if before is None:
        add("record_observed", "First recorded snapshot", facts["updated"], "Record update posted")
    if facts["first_posted"] and (not before or not before["first_posted"]):
        add("trial_registered", "New trial registered", facts["first_posted"], "First registry posting")
    elif before and before["first_posted"] != facts["first_posted"]:
        add("registration_date_corrected", "Registry posting date corrected", facts["updated"], "Correction posted",
            [{"field":"first_posted","before":before["first_posted"],"after":facts["first_posted"]}])
    if facts["results_posted"] and (not before or not before["results_posted"]):
        add("results_posted", "Results posted", facts["results_posted"], "First results posting")
    elif before and before["results_posted"] != facts["results_posted"]:
        add("results_date_corrected", "Results posting date corrected", facts["updated"], "Correction posted",
            [{"field":"results_posted","before":before["results_posted"],"after":facts["results_posted"]}])
    elif before and facts["results_available"] and before["results_version"] and facts["results_version"] != before["results_version"]:
        add("results_updated", "Results updated", facts["updated"], "Results update posted")
    if before and facts["status"] != before["status"]:
        change = [{"field": "status", "before": before["status"], "after": facts["status"]}]
        if facts["status"] in STOPPED:
            add("trial_stopped", "Trial " + facts["status"].lower(), facts["updated"], "Status change posted", change, facts["why_stopped"])
        elif facts["status"] == "COMPLETED":
            add("trial_completed", "Trial completed", facts["updated"], "Completion status posted", change)
        else:
            add("status_changed", "Trial status changed", facts["updated"], "Status change posted", change)
    if before:
        for field, label in (("primary_completion", "Primary completion date moved"), ("completion", "Study completion date moved")):
            old, new = before[field].get("date"), facts[field].get("date")
            if old and new and old != new:
                add("completion_date_moved", label, facts["updated"], "Date change posted",
                    [{"field": field, "before": before[field], "after": facts[field]}])
    if not events:
        add("record_observed" if before is None else "record_updated",
            "First recorded snapshot" if before is None else "Record updated", facts["updated"], "Record update posted")
    return events


def impact(event, item):
    """Material means potential forecast relevance, never a positive/negative outcome."""
    kind = event["kind"]
    evidence = item.get("evidence") or {}
    late_stage = bool(set(evidence.get("phases") or []) & {"PHASE2", "PHASE3"})
    industrial = evidence.get("sponsor_class") == "INDUSTRY"
    rating, rationale = "Watch", "Review the source before changing forecast assumptions."
    if kind in {"record_observed", "record_updated"}:
        rating, rationale = "None", "No verified clinical or regulatory milestone is established by this record update."
    elif kind in {"results_posted", "results_updated", "trial_stopped"}:
        if late_stage and industrial:
            rating = "Material"
        rationale = "A study outcome or pipeline-risk event warrants review; efficacy and commercial impact are not inferred."
    elif kind == "trial_completed":
        rationale = "Completion is a milestone; it does not establish positive results or an approval."
    elif kind == "completion_date_moved":
        rationale = "The reported timeline changed; assess implications for timing without assuming a launch date."
    elif kind in {"fda_original_approval", "ema_authorisation"}:
        rating, rationale = "Material", "A verified regulatory authorisation warrants assessment of market assumptions."
    elif kind == "safety_alert":
        rating, rationale = "Material", "An official safety action warrants review; applicability and severity must be checked."
    elif kind == "fda_generic_approval":
        rationale = "A generic approval warrants review; first-generic status, exclusivity and launch are not established."
    return {"rating": rating, "rationale": rationale, "policy_version": RULE_VERSION, "basis": "source_rules"}


def annotate(item, events, version):
    """Select the strongest in-window event, retaining all source changes for review."""
    order = {"Material": 0, "Watch": 1, "None": 2}
    enriched = [{**event, "impact": impact(event, item)} for event in events]
    enriched.sort(key=lambda e: (order[e["impact"]["rating"]], e["date"]), reverse=False)
    selected = enriched[0]
    return {**item, "version": version, "events": enriched, "event": selected,
        "impact": selected["impact"], "date": selected["date"], "date_label": selected["date_label"]}
