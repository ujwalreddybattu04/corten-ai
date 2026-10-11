"""Public pharma intelligence. Source dates and cached failures are explicit.

No LLM-generated events, patient records, or changes to forecast assumptions.
The bounded memory cache works without the optional local Redis service.
"""

import asyncio
import copy
import hashlib
import logging
import re
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from time import monotonic
from typing import Literal
from urllib.parse import urlparse

import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)
Topic = Literal["all", "oncology", "rare-disease", "immunology", "cns", "cardiometabolic"]
TOPICS = {
    "all": "",
    "oncology": "cancer",
    "rare-disease": "rare disease",
    "immunology": "immune system diseases",
    "cns": "nervous system diseases",
    "cardiometabolic": "cardiovascular diseases",
}
FDA_URL = "https://api.fda.gov/drug/drugsfda.json"
TRIALS_URL = "https://clinicaltrials.gov/api/v2/studies"
NEWS_URL = "https://content.guardianapis.com/search"
CACHE_SECONDS = 3600
SOURCES = {
    "fda": {"name": "FDA · Drugs@FDA", "url": "https://open.fda.gov/apis/drug/drugsfda/", "cadence": "Source updated on weekdays", "scope": "US regulatory records; all therapy areas"},
    "trials": {"name": "ClinicalTrials.gov", "url": "https://clinicaltrials.gov/data-api/api", "cadence": "Study records update as posted", "scope": "Global drug and biologic studies"},
    "news": {"name": "The Guardian", "url": "https://www.theguardian.com", "cadence": "Articles as published", "scope": "Pharma and biotechnology reporting"},
}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_text(value, limit=600):
    parser = PlainText()
    parser.feed(str(value or ""))
    return " ".join(" ".join(parser.parts).split())[:limit]


def iso_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        try:
            return datetime.strptime(value, "%Y%m%d").date().isoformat()
        except ValueError:
            return None


def public_url(value):
    parsed = urlparse(str(value or ""))
    return str(value) if parsed.scheme in ("https", "http") and parsed.hostname else None


def normalize_fda(payload, since, until):
    """Inspect each submission; an application's other submissions may be older."""
    output = []
    for application in payload.get("results", []):
        app_id = application.get("application_number", "")
        if not re.fullmatch(r"(?:NDA|ANDA|BLA)\d{6}", app_id):
            continue
        brands = list(dict.fromkeys(clean_text(p.get("brand_name"), 100) for p in application.get("products", []) if p.get("brand_name")))
        sponsor = clean_text(application.get("sponsor_name"), 160)
        for submission in application.get("submissions", []):
            action_date = iso_date(submission.get("submission_status_date"))
            if submission.get("submission_status") != "AP" or not action_date or not since <= action_date <= until:
                continue
            kind = submission.get("submission_type", "")
            label = "FDA original approval" if kind == "ORIG" else "FDA supplemental approval" if kind == "SUPPL" else "FDA approval update"
            number = str(submission.get("submission_number", ""))
            output.append({
                "id": f"fda:{app_id}:{kind}:{number}", "source": "fda", "category": "Regulatory",
                "title": f"{', '.join(brands[:3]) or app_id} · {label}",
                "summary": f"{sponsor or 'Sponsor not listed'}. Application {app_id}, submission {kind} {number}. {clean_text(submission.get('submission_class_code_description'), 220)}".strip(),
                "date": action_date, "date_label": "FDA action date", "organization": sponsor,
                "url": f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_id[-6:]}",
                "tags": [label, app_id],
            })
    return output


def normalize_trials(payload, since, until):
    output = []
    for study in payload.get("studies", []):
        p = study.get("protocolSection", {})
        identification = p.get("identificationModule", {})
        status = p.get("statusModule", {})
        nct = identification.get("nctId", "")
        updated = iso_date(status.get("lastUpdatePostDateStruct", {}).get("date"))
        if not re.fullmatch(r"NCT\d{8}", nct) or not updated or not since <= updated <= until:
            continue
        interventions = p.get("armsInterventionsModule", {}).get("interventions", [])
        if not any(i.get("type") in ("DRUG", "BIOLOGICAL") for i in interventions):
            continue
        phases = p.get("designModule", {}).get("phases", [])
        sponsor = clean_text(p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"), 160)
        conditions = p.get("conditionsModule", {}).get("conditions", [])
        trial_status = clean_text(status.get("overallStatus", "Status not listed").replace("_", " ").title(), 80)
        output.append({
            "id": f"trial:{nct}", "source": "trials", "category": "Clinical trials",
            "title": clean_text(identification.get("briefTitle") or nct, 240),
            "summary": clean_text(f"{sponsor or 'Sponsor not listed'}. {trial_status}. Conditions: {', '.join(conditions[:3])}.", 500),
            "date": updated, "date_label": "Record updated", "organization": sponsor,
            "url": f"https://clinicaltrials.gov/study/{nct}",
            "tags": [nct, trial_status, *[phase.replace("PHASE", "Phase ") for phase in phases]],
        })
    return output


def normalize_news(payload, since, until):
    output = []
    for article in payload.get("response", {}).get("results", []):
        published = iso_date(article.get("webPublicationDate"))
        url = public_url(article.get("webUrl"))
        if not published or not since <= published <= until or not url:
            continue
        title = clean_text(article.get("webTitle"), 240)
        if not title:
            continue
        output.append({
            "id": "news:" + hashlib.sha256(url.encode()).hexdigest()[:20], "source": "news", "category": "Industry news",
            "title": title, "summary": clean_text(article.get("fields", {}).get("trailText"), 450),
            "date": published, "date_label": "Published", "organization": "The Guardian",
            "url": url, "tags": ["Industry reporting"],
        })
    return output


class PharmaUpdatesService:
    def __init__(self, client_factory=httpx.AsyncClient):
        self._client_factory = client_factory
        self._cache = {}
        self._locks = {}

    async def _source(self, client, source, topic, since, until):
        if source == "news" and not settings.GUARDIAN_API_KEY:
            return {"id": source, **SOURCES[source], "status": "unconfigured", "items": [], "checked_at": None, "source_updated_at": None}
        source_updated = None
        if source == "fda":
            params = {"search": f'submissions.submission_status:"AP" AND submissions.submission_status_date:[{since.replace("-", "")} TO {until.replace("-", "")}]', "sort": "submissions.submission_status_date:desc", "limit": 50}
            auth = httpx.BasicAuth(settings.OPENFDA_API_KEY, "") if settings.OPENFDA_API_KEY else None
            response = await client.get(FDA_URL, params=params, auth=auth)
            if response.status_code == 404 and response.json().get("error", {}).get("code") == "NOT_FOUND":
                payload = {"results": []}
            else:
                response.raise_for_status()
                payload = response.json()
            items = normalize_fda(payload, since, until)
            source_updated = iso_date(payload.get("meta", {}).get("last_updated"))
        elif source == "trials":
            params = {"pageSize": 20, "sort": "LastUpdatePostDate:desc", "fields": "NCTId,BriefTitle,LastUpdatePostDate,OverallStatus,Phase,LeadSponsorName,Condition,InterventionName,InterventionType", "filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{since},{until}] AND AREA[StudyType]INTERVENTIONAL AND (AREA[InterventionType]DRUG OR AREA[InterventionType]BIOLOGICAL)"}
            if TOPICS[topic]:
                params["query.cond"] = TOPICS[topic]
            response = await client.get(TRIALS_URL, params=params)
            response.raise_for_status()
            items = normalize_trials(response.json(), since, until)
        else:
            query = 'pharmaceutical OR biotech OR "drug approval" OR "clinical trial"'
            if TOPICS[topic]:
                query = f"({query}) AND ({TOPICS[topic]})"
            response = await client.get(NEWS_URL, params={"api-key": settings.GUARDIAN_API_KEY, "q": query, "from-date": since, "to-date": until, "order-by": "newest", "page-size": 20, "show-fields": "trailText"})
            response.raise_for_status()
            items = normalize_news(response.json(), since, until)
        unique = {item["id"]: item for item in items}
        items = sorted(unique.values(), key=lambda i: (i["date"], i["id"]), reverse=True)[:20]
        return {"id": source, **SOURCES[source], "status": "available" if items else "empty", "items": items, "checked_at": datetime.now(timezone.utc).isoformat(), "source_updated_at": source_updated}

    async def get_feed(self, topic: Topic = "all", days: Literal[7, 30, 90] = 7):
        today = datetime.now(timezone.utc).date()
        since = (today - timedelta(days=days - 1)).isoformat()
        until = today.isoformat()
        key = (topic, days)
        async with self._locks.setdefault(key, asyncio.Lock()):
            previous = self._cache.get(key)
            if previous and previous[0] > monotonic() and previous[1]["until"] == until:
                return copy.deepcopy(previous[1])
            async with self._client_factory(timeout=httpx.Timeout(12.0)) as client:
                results = await asyncio.gather(*(self._source(client, source, topic, since, until) for source in SOURCES), return_exceptions=True)
            sources = []
            for source, result in zip(SOURCES, results):
                if isinstance(result, Exception):
                    # Never log exception URLs: providers can include credentials there.
                    logger.warning("Pharma source %s failed (%s)", source, type(result).__name__)
                    authentication_required = isinstance(result, httpx.HTTPStatusError) and result.response.status_code in (401, 403)
                    old = next((s for s in previous[1]["sources"] if s["id"] == source), None) if previous else None
                    old_time = datetime.fromisoformat(old["checked_at"]) if old and old.get("checked_at") else None
                    if old and old_time and datetime.now(timezone.utc) - old_time < timedelta(hours=24):
                        result = {**old, "status": "stale", "items": [i for i in old["items"] if since <= i["date"] <= until]}
                    else:
                        result = {"id": source, **SOURCES[source], "status": "authentication_required" if authentication_required else "unavailable", "items": [], "checked_at": None, "source_updated_at": None}
                sources.append(result)
            items = sorted((item for source in sources for item in source["items"]), key=lambda i: (i["date"], i["id"]), reverse=True)
            checked_at = datetime.now(timezone.utc)
            successful = any(s["status"] in ("available", "empty") for s in sources)
            ttl = CACHE_SECONDS if successful else 60
            feed = {"topic": topic, "days": days, "since": since, "until": until, "checked_at": checked_at.isoformat(), "next_check_at": (checked_at + timedelta(seconds=ttl)).isoformat(), "items": items, "sources": sources}
            self._cache[key] = (monotonic() + ttl, feed)
            return copy.deepcopy(feed)


pharma_updates_service = PharmaUpdatesService()
