"""Public pharma intelligence. Source dates and cached failures are explicit.

No LLM-generated events, patient records, or changes to forecast assumptions.
The bounded memory cache works without the optional local Redis service.
"""

import asyncio
import copy
import hashlib
import json
import logging
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urlparse

import httpx

from src.config.settings import settings
from src.services.pharma_cache import PharmaSharedCache

logger = logging.getLogger(__name__)
Topic = Literal["all", "oncology", "rare-disease", "immunology", "cns", "cardiometabolic"]
TOPICS = {
    "all": "",
    "oncology": "cancer",
    "rare-disease": "rare disease",
    "immunology": "immune system diseases",
    "cns": "nervous system diseases",
    "cardiometabolic": "cardiovascular diseases OR metabolic diseases OR diabetes",
}
FDA_URL = "https://api.fda.gov/drug/drugsfda.json"
TRIALS_URL = "https://clinicaltrials.gov/api/v2/studies"
NEWS_URL = "https://content.guardianapis.com/search"
CACHE_SECONDS = 3600
ERROR_SECONDS = 300
MAX_STALE_SECONDS = 24 * 3600
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
    try:
        parsed = urlparse(str(value or ""))
        return str(value) if parsed.scheme in ("https", "http") and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        return None


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
                "details": {"application": app_id, "action": label, "ingredients": list(dict.fromkeys(clean_text(i.get("name"), 100) for p in application.get("products", []) for i in p.get("active_ingredients", []) if i.get("name")))[:8]},
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
            "details": {"study_id": nct, "status": trial_status, "phases": phases, "conditions": [clean_text(c, 140) for c in conditions[:8]], "interventions": list(dict.fromkeys(clean_text(i.get("name"), 140) for i in interventions if i.get("type") in ("DRUG", "BIOLOGICAL") and i.get("name")))[:8]},
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
        fields = article.get("fields") if isinstance(article.get("fields"), dict) else {}
        thumbnail = fields.get("thumbnail")
        try:
            image = urlparse(thumbnail) if isinstance(thumbnail, str) and len(thumbnail) <= 2048 else None
            thumbnail = thumbnail if image and image.scheme == "https" and image.hostname == "i.guim.co.uk" and not image.username and not image.password and image.port in (None, 443) else None
        except ValueError:
            thumbnail = None
        output.append({
            "id": "news:" + hashlib.sha256(url.encode()).hexdigest()[:20], "source": "news", "category": "Industry news",
            "title": title, "summary": clean_text(fields.get("trailText"), 450),
            "date": published, "date_label": "Published", "organization": "The Guardian",
            "url": url, "tags": ["Industry reporting"],
            **({"thumbnail": thumbnail} if thumbnail else {}),
        })
    return output


class PharmaUpdatesService:
    def __init__(self, client_factory=httpx.AsyncClient, shared_cache=None):
        self._client_factory = client_factory
        self._shared = shared_cache
        self._cache = {}
        self._pending = {}
        self._cooldowns = {}
        self._slots = asyncio.Semaphore(4)

    @staticmethod
    async def _json(client, url, **kwargs):
        # Bound bytes while reading, including decompressed transfer chunks.
        async with client.stream("GET", url, **kwargs) as response:
            if response.status_code != 404 or url != FDA_URL:
                response.raise_for_status()
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 2_000_000:
                    raise ValueError("Provider response exceeds the pharma feed limit")
                chunks.append(chunk)
            return response, json.loads(b"".join(chunks))

    async def _source(self, client, source, topic, since, until):
        if source == "news" and not settings.GUARDIAN_API_KEY:
            return {"id": source, **SOURCES[source], "status": "unconfigured", "items": [], "checked_at": None, "source_updated_at": None}
        source_updated = None
        limited = False
        if source == "fda":
            params = {"search": f'submissions.submission_status:"AP" AND submissions.submission_status_date:[{since.replace("-", "")} TO {until.replace("-", "")}]', "sort": "submissions.submission_status_date:desc", "limit": 50}
            auth = httpx.BasicAuth(settings.OPENFDA_API_KEY, "") if settings.OPENFDA_API_KEY else None
            response, payload = await self._json(client, FDA_URL, params=params, auth=auth)
            if response.status_code == 404 and isinstance(payload, dict) and payload.get("error", {}).get("code") == "NOT_FOUND":
                payload = {"results": []}
            else:
                response.raise_for_status()
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise ValueError("Invalid FDA response")
            items = normalize_fda(payload, since, until)
            source_updated = iso_date(payload.get("meta", {}).get("last_updated"))
            limited = payload.get("meta", {}).get("results", {}).get("total", 0) > 50 or len(items) > 20
        elif source == "trials":
            params = {"pageSize": 20, "sort": "LastUpdatePostDate:desc", "fields": "NCTId,BriefTitle,LastUpdatePostDate,OverallStatus,Phase,LeadSponsorName,Condition,InterventionName,InterventionType", "filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{since},{until}] AND AREA[StudyType]INTERVENTIONAL AND (AREA[InterventionType]DRUG OR AREA[InterventionType]BIOLOGICAL)"}
            if TOPICS[topic]:
                params["query.cond"] = TOPICS[topic]
            response, payload = await self._json(client, TRIALS_URL, params=params)
            if not isinstance(payload, dict) or not isinstance(payload.get("studies"), list):
                raise ValueError("Invalid trial response")
            items = normalize_trials(payload, since, until)
            limited = bool(payload.get("nextPageToken"))
        else:
            query = 'pharmaceutical OR biotech OR "drug approval" OR "clinical trial"'
            if TOPICS[topic]:
                query = f"({query}) AND ({TOPICS[topic]})"
            response, payload = await self._json(client, NEWS_URL, params={"api-key": settings.GUARDIAN_API_KEY, "q": query, "from-date": since, "to-date": until, "order-by": "newest", "page-size": 20, "show-fields": "trailText,thumbnail"})
            if not isinstance(payload, dict) or not isinstance(payload.get("response", {}).get("results"), list):
                raise ValueError("Invalid news response")
            items = normalize_news(payload, since, until)
            limited = payload["response"].get("total", 0) > 20
        unique = {item["id"]: item for item in items}
        items = sorted(unique.values(), key=lambda i: (i["date"], i["id"]), reverse=True)[:20]
        return {"id": source, **SOURCES[source], "status": "available" if items else "empty", "items": items, "checked_at": datetime.now(timezone.utc).isoformat(), "source_updated_at": source_updated, "limited": limited}

    def _key(self, source, topic, days):
        credential = settings.OPENFDA_API_KEY if source == "fda" else settings.GUARDIAN_API_KEY if source == "news" else "public"
        fingerprint = hashlib.sha256(credential.encode()).hexdigest()[:12]
        return f"pharma:v2:{source}:{'all' if source == 'fda' else topic}:{days}:{fingerprint}"

    @staticmethod
    def _valid_cache(value, source):
        if not isinstance(value, dict) or not isinstance(value.get("value"), dict):
            return False
        result = value["value"]
        try:
            return result.get("id") == source and isinstance(result.get("items"), list) and len(result["items"]) <= 20 and all(isinstance(i, dict) and i.get("source") == source and iso_date(i.get("date")) for i in result["items"]) and datetime.fromisoformat(value["retry_at"]).tzinfo is not None
        except (ValueError, TypeError, KeyError):
            return False

    @staticmethod
    def _fresh(value, until):
        return bool(value and value.get("until") == until and datetime.fromisoformat(value["retry_at"]) > datetime.now(timezone.utc))

    @staticmethod
    def _fallback(source, previous, since, until, status="unavailable"):
        now = datetime.now(timezone.utc)
        old = previous.get("value") if previous else None
        try:
            age = (now - datetime.fromisoformat(old["checked_at"])).total_seconds() if old and old.get("checked_at") else None
        except (ValueError, TypeError):
            age = None
        if age is not None and 0 <= age <= MAX_STALE_SECONDS:
            return {**old, "status": "stale", "items": [i for i in old["items"] if since <= i["date"] <= until]}
        return {"id": source, **SOURCES[source], "status": status, "items": [], "checked_at": None, "source_updated_at": None, "limited": False}

    async def _load(self, source, topic, days, since, until, key, previous):
        lease_key, token, lease = key + ":lease", secrets.token_hex(16), None
        if self._shared:
            remote = await self._shared.get(key)
            if self._valid_cache(remote, source):
                previous = remote
                if self._fresh(remote, until):
                    self._cache[(source, topic, days)] = remote
                    return remote
            lease = await self._shared.acquire(lease_key, token)
            if lease is False:
                # Warm readers do not wait on a provider. Cold readers wait for
                # the owner, without falling through to duplicate upstream work.
                if previous and previous["value"].get("checked_at"):
                    return {"value": self._fallback(source, previous, since, until), "retry_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(), "until": until}
                for _ in range(30):
                    await asyncio.sleep(0.4)
                    remote = await self._shared.get(key)
                    if self._valid_cache(remote, source) and self._fresh(remote, until):
                        self._cache[(source, topic, days)] = remote
                        return remote
                return {"value": self._fallback(source, previous, since, until), "retry_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(), "until": until}
        try:
            cooldown_key = key.split(":")[0:3] + [key.rsplit(":", 1)[1]]
            cooldown_key = ":".join(cooldown_key) + ":cooldown"
            cooldown = self._cooldowns.get(source)
            if self._shared:
                cooldown = await self._shared.get(cooldown_key) or cooldown
            try:
                cooldown_until = datetime.fromisoformat(cooldown["until"]) if cooldown else None
                if cooldown_until and (cooldown_until.tzinfo is None or cooldown.get("status") not in ("unavailable", "authentication_required")):
                    cooldown = None
            except (ValueError, TypeError, KeyError):
                cooldown = None
            ttl = CACHE_SECONDS
            if cooldown and cooldown.get("key") == cooldown_key and datetime.fromisoformat(cooldown["until"]) > datetime.now(timezone.utc):
                result = self._fallback(source, previous, since, until, cooldown["status"])
                ttl = min(CACHE_SECONDS, max(1, int((datetime.fromisoformat(cooldown["until"]) - datetime.now(timezone.utc)).total_seconds())))
            else:
                try:
                    async with asyncio.timeout(10):
                        async with self._slots:
                            async with self._client_factory(timeout=httpx.Timeout(6.0), follow_redirects=False) as client:
                                async with asyncio.timeout(8):
                                    result = await self._source(client, source, topic, since, until)
                except Exception as failure:
                    logger.warning("Pharma source %s failed (%s)", source, type(failure).__name__)
                    code = failure.response.status_code if isinstance(failure, httpx.HTTPStatusError) else None
                    status = "authentication_required" if code in (401, 403) else "unavailable"
                    ttl = CACHE_SECONDS if code in (401, 403) else ERROR_SECONDS
                    if code == 429:
                        header = failure.response.headers.get("Retry-After", str(ERROR_SECONDS))
                        try:
                            ttl = int(header) if header.isdigit() else int((parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError, OverflowError):
                            ttl = ERROR_SECONDS
                        # Longer provider cooldowns survive the hourly snapshot
                        # check rather than retrying earlier than requested.
                        ttl = min(MAX_STALE_SECONDS, max(ERROR_SECONDS, ttl))
                    result = self._fallback(source, previous, since, until, status)
                    cooldown = {"key": cooldown_key, "status": status, "until": (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()}
                    self._cooldowns[source] = cooldown
                    if self._shared:
                        await self._shared.set(cooldown_key, cooldown, ttl)
            if result["status"] == "unconfigured":
                ttl = CACHE_SECONDS
            if result["status"] == "stale":
                remaining = MAX_STALE_SECONDS - (datetime.now(timezone.utc) - datetime.fromisoformat(result["checked_at"])).total_seconds()
                ttl = max(1, min(ttl, int(remaining)))
            cached = {"value": result, "retry_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat(), "until": until, "key": key}
            self._cache[(source, topic, days)] = cached
            if self._shared:
                await self._shared.set(key, cached, MAX_STALE_SECONDS)
            return cached
        finally:
            if self._shared and lease:
                await self._shared.release(lease_key, token)

    async def _cached_source(self, source, topic, days, since, until):
        topic = "all" if source == "fda" else topic
        slot = (source, topic, days)
        key = self._key(source, topic, days)
        previous = self._cache.get(slot)
        # Credentials may be replaced at runtime by a deployment restart.
        if previous and previous.get("key", key) != key:
            previous = None
        if self._fresh(previous, until):
            return previous
        if slot not in self._pending:
            task = asyncio.create_task(self._load(source, topic, days, since, until, key, previous))
            self._pending[slot] = task
            task.add_done_callback(lambda done: self._pending.pop(slot, None))
        # A disconnected browser must not cancel the shared refresh for everyone.
        return await asyncio.shield(self._pending[slot])

    async def get_feed(self, topic: Topic = "all", days: Literal[7, 30, 90] = 7):
        if topic not in TOPICS or days not in (7,30,90):raise ValueError("Invalid pharma filters")
        if settings.PHARMA_INTELLIGENCE_ENABLED:
            slot=("archive",topic,days);key=f"pharma:archive:events-1:{topic}:{days}"
            now=datetime.now(timezone.utc)
            cached=self._cache.get(slot)
            if not cached or datetime.fromisoformat(cached["until"])<=now:
                if self._shared:cached=await self._shared.get(key)
            if cached and datetime.fromisoformat(cached["until"])>now:
                return copy.deepcopy(cached["value"])
            async def load_archive():
                from src.services.pharma_repository import get_feed
                value=await get_feed(topic,days)
                cached={"until":(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat(),"value":value}
                self._cache[slot]=cached
                if self._shared:await self._shared.set(key,cached,60)
                return value
            if slot not in self._pending:
                task=asyncio.create_task(load_archive());self._pending[slot]=task
                def cleanup(done):
                    self._pending.pop(slot,None)
                    if not done.cancelled():done.exception()
                task.add_done_callback(cleanup)
            return copy.deepcopy(await asyncio.shield(self._pending[slot]))
        today = datetime.now(timezone.utc).date()
        since = (today - timedelta(days=days - 1)).isoformat()
        until = today.isoformat()
        if topic not in TOPICS or days not in (7, 30, 90):
            raise ValueError("Invalid pharma filters")
        cached = await asyncio.gather(*(self._cached_source(source, topic, days, since, until) for source in SOURCES))
        sources = [record["value"] for record in cached]
        items = sorted((item for source in sources for item in source["items"]), key=lambda i: (i["date"], i["id"]), reverse=True)
        successful = any(s["status"] in ("available", "empty") for s in sources)
        feed = {"topic": topic, "days": days, "since": since, "until": until, "checked_at": datetime.now(timezone.utc).isoformat(), "next_check_at": min(record["retry_at"] for record in cached), "items": items, "sources": sources, "status": "available" if successful else "stale" if items else "unavailable", "partial": any(s["status"] not in ("available", "empty") for s in sources), "limit_per_source": 20}
        return copy.deepcopy(feed)


pharma_updates_service = PharmaUpdatesService(shared_cache=PharmaSharedCache())
