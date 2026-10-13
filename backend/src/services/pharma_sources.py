"""Bounded official/public source adapters. Sources never invent missing dates."""
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import httpx
from src.config.settings import settings
from src.services.pharma_catalog import COMPANIES, TRADE_DOMAINS
from src.services.pharma_events import digest, posted_date, study_facts
from src.services.pharma_updates import clean_text, iso_date, normalize_fda, normalize_trials

FDA_DRUGS_RSS="https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/drugs/rss.xml"
FDA_SAFETY_RSS="https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/medwatch/rss.xml"
EMA_JSON="https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json"
TRADE_FEEDS=("https://pharmatimes.com/feed/","https://www.fiercebiotech.com/rss/xml")
FDA_URL="https://api.fda.gov/drug/drugsfda.json"
TRIALS_URL="https://clinicaltrials.gov/api/v2/studies"
USER_AGENT="Corten-Pharma/1.0 (public scientific metadata; bounded periodic ingestion)"


def safe_source_url(value,domains=None):
    if not isinstance(value,str) or len(value)>2048:return None
    try:
        parsed=urlsplit(value)
        if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):return None
        if domains and not any(parsed.hostname==d or parsed.hostname.endswith("."+d) for d in domains):return None
        return value
    except ValueError:return None


def publication_date(value):
    if not isinstance(value,str):return None
    direct=iso_date(value)
    if direct:return direct
    try:
        when=parsedate_to_datetime(value)
        return when.astimezone(timezone.utc).date().isoformat() if when.tzinfo else None
    except (ValueError,TypeError,OverflowError):return None


def ema_date(value):
    # The official medicine export uses day/month/year (verified against the live dataset).
    direct=publication_date(value)
    if direct:return direct
    try:return datetime.strptime(value,"%d/%m/%Y").date().isoformat() if isinstance(value,str) else None
    except ValueError:return None


async def read_response(response,limit=2_000_000):
    response.raise_for_status();body=bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body)>limit:raise ValueError("Pharma source response exceeds size limit")
    return bytes(body)


async def get_json(client,url,limit=2_000_000,**kwargs):
    async with client.stream("GET",url,headers={"User-Agent":USER_AGENT,"Accept":"application/json"},**kwargs) as response:
        if response.status_code==404 and url==FDA_URL:
            body=await response.aread()
            if len(body)<=10000 and json.loads(body).get("error",{}).get("code")=="NOT_FOUND":return {"results":[]}
        return json.loads(await read_response(response,limit))


def rss_records(body,source,domains,since,until):
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():raise ValueError("Unsafe XML source")
    class SafeBuilder(ET.TreeBuilder):
        def doctype(self,*args):raise ValueError("XML document types are not accepted")
    try:root=ET.fromstring(body,parser=ET.XMLParser(target=SafeBuilder()))
    except ET.ParseError as exc:raise ValueError("Invalid publisher feed") from exc
    rows=[];undated=0
    for item in root.findall(".//item")[:200]:
        title=clean_text(item.findtext("title"),500)
        url=safe_source_url(item.findtext("link"),domains)
        when=publication_date(item.findtext("pubDate"))
        if not when:undated+=1;continue
        if not url or not title or not since<=when<=until:continue
        description=clean_text(item.findtext("description"),500)
        if source=="fda_safety" and not any(word in (title+" "+description+" "+url).casefold()
            for word in ("drug","medicine","tablet","capsule","injection","pharmaceutical","biologic")):
            continue
        issuer="FDA" if source.startswith("fda_") else urlsplit(url).hostname.replace("www.","")
        kind="safety_alert" if source=="fda_safety" else "fda_announcement" if source=="fda_updates" else "trade_report"
        record={"id":source+":"+digest(url),"source":source,"title":title,"summary":description,
            "date":when,"date_label":"Published","organization":issuer,"category":"Safety" if source=="fda_safety" else "Regulatory" if source=="fda_updates" else "Industry news",
            "url":url,"tags":["Official FDA publication" if source.startswith("fda_") else "Trade reporting"],
            "details":{"publisher":issuer},"evidence":{"publication_date":when,"coverage":"Publisher headline and short summary"}}
        event={"kind":kind,"label":"FDA safety alert" if source=="fda_safety" else "FDA announcement" if source=="fda_updates" else "Trade report",
            "date":when,"date_label":"Published","changes":[],"baseline":True,"reason":None}
        rows.append((record,{"title":title,"url":url,"published":when,"summary":description},[event]))
    return rows,{"undated_excluded":undated,"limited":True,"method":"publisher_rss",
        "coverage":"Current publisher feed; earlier publications may be absent"}


async def clinical_records(client,since,until,cursor=None):
    params={"pageSize":50,"sort":"LastUpdatePostDate:desc",
        "filter.advanced":f"AREA[LastUpdatePostDate]RANGE[{since},{until}] AND AREA[StudyType]INTERVENTIONAL AND (AREA[InterventionType]DRUG OR AREA[InterventionType]BIOLOGICAL)"}
    if cursor:params["pageToken"]=cursor
    data=await get_json(client,TRIALS_URL,limit=8_000_000,params=params)
    if not isinstance(data,dict) or not isinstance(data.get("studies"),list):raise ValueError("Invalid registry response")
    rows=[];rejected=0
    for raw in data["studies"]:
        try:
            normalized=normalize_trials({"studies":[raw]},since,until)
            if not normalized:continue
            item=normalized[0];facts=study_facts(raw)
            if len(json.dumps(raw).encode())>512_000:raise ValueError("Study exceeds snapshot limit")
            protocol=raw.get("protocolSection") or {};status=protocol.get("statusModule") or {}
            details=item["details"]
            for label,value in (("registered",facts["first_posted"]),("results_posted",facts["results_posted"]),
                ("sponsor_class",facts["sponsor_class"]),("why_stopped",facts["why_stopped"])):
                if value:details[label]=str(value)[:240]
            for label,field in (("primary_completion",facts["primary_completion"]),("study_completion",facts["completion"])):
                if field.get("date"):details[label]=field["date"]+(" · "+field["type"].lower() if field.get("type") else "")
            item["evidence"]=facts
            # Contacts/location people are not needed for this public forecasting archive.
            scientific={"protocolSection":{k:v for k,v in protocol.items() if k not in ("contactsLocationsModule","ipdSharingStatementModule")}}
            if raw.get("resultsSection"):scientific["resultsSection"]=raw["resultsSection"]
            rows.append((item,scientific,None))
        except (ValueError,TypeError,KeyError):rejected+=1
    return rows,{"next_cursor":data.get("nextPageToken"),"rejected_records":rejected,
        "limited":bool(data.get("nextPageToken")) or bool(rejected),"method":"registry_api_v2"}


async def fda_records(client,since,until):
    params={"search":f'submissions.submission_status:"AP" AND submissions.submission_status_date:[{since.replace("-","")} TO {until.replace("-","")}]',
        "sort":"submissions.submission_status_date:desc","limit":100}
    auth=httpx.BasicAuth(settings.OPENFDA_API_KEY,"") if settings.OPENFDA_API_KEY else None
    data=await get_json(client,FDA_URL,limit=8_000_000,params=params,auth=auth)
    if not isinstance(data,dict) or not isinstance(data.get("results"),list):raise ValueError("Invalid FDA response")
    rows=[]
    for application in data["results"]:
        normalized=normalize_fda({"results":[application]},since,until)
        for item in normalized:
            brands=[clean_text(p.get("brand_name"),120) for p in application.get("products",[]) if p.get("brand_name")]
            item["details"]["brands"]=list(dict.fromkeys(brands))[:8]
            application_id,kind,number=item["id"].split(":")[1:]
            submission=next(s for s in application["submissions"] if str(s.get("submission_type",""))==kind and str(s.get("submission_number",""))==number)
            event_kind="fda_generic_approval" if application_id.startswith("ANDA") and kind=="ORIG" else "fda_original_approval" if kind=="ORIG" else "fda_supplemental_approval"
            if event_kind=="fda_generic_approval":
                item["title"]=item["title"].replace("FDA original approval","FDA generic approval")
                item["details"]["action"]="FDA generic approval"
            event={"kind":event_kind,"label":item["details"]["action"],"date":item["date"],"date_label":"FDA action date", "changes":[],"baseline":True,"reason":None}
            raw={"application_number":application_id,"sponsor_name":application.get("sponsor_name"),"products":application.get("products",[]),"submission":submission}
            rows.append((item,raw,[event]))
    return rows,{"limited":data.get("meta",{}).get("results",{}).get("total",0)>100,
        "source_updated_at":iso_date(data.get("meta",{}).get("last_updated")),"method":"openfda"}


def ema_records(data,since,until):
    records=data if isinstance(data,list) else next((v for v in data.values() if isinstance(v,list)),[]) if isinstance(data,dict) else []
    if not records:raise ValueError("Invalid EMA medicine dataset")
    rows=[];aliases=[]
    for raw in records:
        if not isinstance(raw,dict) or str(raw.get("category","")).casefold() not in ("human","human medicines"):continue
        name=raw.get("name_of_medicine");number=raw.get("ema_product_number");url=safe_source_url(raw.get("medicine_url"),("ema.europa.eu",))
        substance=raw.get("international_non_proprietary_name_common_name") or raw.get("active_substance")
        if not name or not number or not url or not isinstance(substance,str):continue
        ingredients=[clean_text(v,160) for v in substance.split(";") if v.strip()]
        if ingredients:aliases.append((clean_text(name,240),ingredients,[clean_text(name,240)],url))
        decision=ema_date(raw.get("european_commission_decision_date"))
        opinion=ema_date(raw.get("opinion_adopted_date"))
        initial_authorisation=ema_date(raw.get("marketing_authorisation_date"))
        authorised=str(raw.get("medicine_status","")).casefold() in ("authorised","authorized")
        when=decision if authorised and decision else opinion
        if not when or not since<=when<=until:continue
        # Commission decision dates can be later variations to a long-approved medicine.
        # The dataset's current Authorised status alone does not establish a new approval.
        kind="ema_authorisation" if authorised and decision and decision==initial_authorisation else "ema_post_authorisation_decision" if authorised and decision and initial_authorisation and decision>initial_authorisation else "ema_decision" if authorised and decision else "ema_opinion"
        details={"ema_product_number":str(number),"medicine_status":str(raw.get("medicine_status","")),
            "opinion_status":str(raw.get("opinion_status","")),"ingredients":ingredients[:8],"brands":[clean_text(name,240)]}
        if initial_authorisation:details["initial_authorisation_date"]=initial_authorisation
        if raw.get("latest_procedure_affecting_product_information"):details["latest_procedure"]=str(raw["latest_procedure_affecting_product_information"])[:240]
        for label,field in (("therapeutic_area","therapeutic_area_mesh"),("indication","therapeutic_indication")):
            if raw.get(field):details[label]=clean_text(raw[field],240)
        label="EU authorisation" if kind=="ema_authorisation" else "Post-authorisation decision" if kind=="ema_post_authorisation_decision" else "Commission decision" if kind=="ema_decision" else "EMA opinion"
        item={"id":"ema:"+str(number),"source":"ema","title":clean_text(name,240)+" · "+label,
            "summary":clean_text(raw.get("therapeutic_indication"),500),"date":when,"date_label":"EMA opinion date" if kind=="ema_opinion" else "European Commission decision",
            "organization":clean_text(raw.get("marketing_authorisation_developer_applicant_holder"),240),"url":url,"category":"Regulatory","tags":["EU centralised procedure"],"details":details,
            "evidence":{"decision_date":decision,"opinion_date":opinion,"initial_authorisation_date":initial_authorisation,"medicine_status":raw.get("medicine_status"),"opinion_status":raw.get("opinion_status")}}
        event={"kind":kind,"label":label, "date":when,"date_label":item["date_label"],"changes":[],"baseline":True,"reason":None}
        rows.append((item,raw,[event]))
    return rows,aliases,{"limited":False,"method":"official_ema_json","coverage":"Centralised human medicines only"}


async def indexed_news(client,source,since,until):
    if not settings.TAVILY_API_KEY:raise ValueError("Indexed news provider not configured")
    domains=list(COMPANIES) if source=="company" else list(TRADE_DOMAINS)
    query='drug clinical trial regulatory pharmaceutical press release' if source=='company' else 'pharmaceutical biotechnology clinical trial regulatory news'
    async with client.stream("POST","https://api.tavily.com/search",headers={"Authorization":"Bearer "+settings.TAVILY_API_KEY},
        json={"query":query,"search_depth":"basic","max_results":15,"include_domains":domains,
            "start_date":since,"end_date":until,"include_published_date":True,"include_answer":False,"include_raw_content":False}) as response:
        data=json.loads(await read_response(response,2_000_000))
    if not isinstance(data,dict) or not isinstance(data.get("results"),list):raise ValueError("Invalid indexed source response")
    rows=[];undated=0
    for entry in data["results"]:
        when=publication_date(entry.get("published_date"));url=safe_source_url(entry.get("url"),domains)
        if not when:undated+=1;continue
        if not url or not since<=when<=until:continue
        if source=="company" and not any(marker in urlsplit(url).path.casefold()
            for marker in ("press-release","press_releases","media-releases","/news/details/")):
            continue
        host=urlsplit(url).hostname
        issuer=next((name for domain,name in COMPANIES.items() if host==domain or host.endswith('.'+domain)),host.replace('www.',''))
        title=clean_text(entry.get("title"),500);summary=clean_text(entry.get("content"),500)
        if not title:continue
        kind="press_release" if source=="company" else "trade_report"
        item={"id":source+":"+digest(url),"source":source,"title":title,"summary":summary,"date":when,
            "date_label":"Indexed publication date","organization":issuer,"url":url,"category":"Company news" if source=="company" else "Industry news",
            "tags":["Official company source" if source=="company" else "Trade reporting"],"details":{"publisher":issuer},
            "evidence":{"coverage":"Search-index headline and short excerpt; original page not fully retrieved","publication_date":when}}
        event={"kind":kind,"label":"Company publication" if source=="company" else "Trade report","date":when,"date_label":item["date_label"],"changes":[],"baseline":True,"reason":None}
        rows.append((item,{"title":title,"summary":summary,"url":url,"published_date":when},[event]))
    return rows,{"limited":len(data["results"])>=15 or bool(undated),"undated_excluded":undated,"method":"domain_restricted_search_index","monitored_domains":domains}
