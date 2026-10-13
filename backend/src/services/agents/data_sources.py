"""Live data for Space agents: market prices, exchange rates, economic indicators, clinical trials, biomedical and
scientific literature, and FDA approvals.

All sources are free public APIs that need no key. Every call is bounded by a timeout, retried once on a transient
failure, cached, validated on input and output, and reported with a citable source. Failures raise DataSourceError
with a message that is safe to show to the model and the user.
"""
import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx

from src.db.redis import cache_get, cache_set

logger = logging.getLogger(__name__)
TIMEOUT = httpx.Timeout(20, connect=6)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CortenResearch/1.0)"}


class DataSourceError(Exception):
    """A data source could not answer. The message is safe to show."""


CACHE_WAIT = 0.5


async def _cached(key: str):
    # The cache is an optimization: an unavailable Redis must never slow an answer down.
    try:
        return await asyncio.wait_for(cache_get(key), CACHE_WAIT)
    except asyncio.TimeoutError:
        return None


async def _store(key: str, value, ttl: int):
    try:
        await asyncio.wait_for(cache_set(key, value, ttl=ttl), CACHE_WAIT)
    except asyncio.TimeoutError:
        pass


async def _fetch(url: str, params: dict | None = None, *, as_json: bool = True, cache_ttl: int = 0,
                 timeout: httpx.Timeout = TIMEOUT, attempts: int = 2):
    """GET with a timeout, one retry on transient failures, and an optional shared cache."""
    host = urlsplit(url).hostname or "the data source"
    key = "agent-data:" + url + "?" + json.dumps(params or {}, sort_keys=True)
    if cache_ttl:
        cached = await _cached(key)
        if cached is not None:
            return cached
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=HEADERS, follow_redirects=True) as http:
                response = await http.get(url, params=params)
        except httpx.HTTPError:
            if attempt < attempts - 1:
                await asyncio.sleep(0.6)
                continue
            raise DataSourceError(f"{host} could not be reached. Try again shortly.") from None
        if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
            await asyncio.sleep(1.0)
            continue
        break
    if response.status_code == 404:
        raise DataSourceError("not found")
    if response.status_code == 429:
        raise DataSourceError(f"{host} is limiting requests right now. Try again in a minute.")
    if response.status_code >= 400:
        raise DataSourceError(f"{host} returned an error ({response.status_code}).")
    try:
        data = response.json() if as_json else response.text
    except ValueError:
        raise DataSourceError(f"{host} returned data that could not be read.") from None
    if cache_ttl:
        await _store(key, data, cache_ttl)
    return data


def _source(title: str, url: str, snippet: str = "") -> dict:
    domain = (urlsplit(url).hostname or "").removeprefix("www.")
    return {"title": title[:200], "url": url, "domain": domain, "snippet": snippet[:1500]}


def summarize_series(points: list[tuple[str, float]]) -> dict:
    """First, last, change and extremes of a time series, for reporting and chart headers."""
    first, last = points[0], points[-1]
    high = max(points, key=lambda point: point[1])
    low = min(points, key=lambda point: point[1])
    change = last[1] - first[1]
    return {"start": first[0], "end": last[0], "first": first[1], "last": last[1], "change": round(change, 4),
            "change_pct": round(change / first[1] * 100, 2) if first[1] else None,
            "high": high[1], "high_date": high[0], "low": low[1], "low_date": low[0], "count": len(points)}


# ── Stock prices (Yahoo Finance chart API; Stooq as a fallback for US tickers) ──────────────────────
PERIODS = {"1m": ("1mo", "1d"), "3m": ("3mo", "1d"), "6m": ("6mo", "1d"), "ytd": ("ytd", "1d"), "1y": ("1y", "1d"),
           "2y": ("2y", "1d"), "5y": ("5y", "1wk"), "10y": ("10y", "1mo"), "max": ("max", "1mo")}
TICKER = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$")


async def stock_history(ticker: str, period: str = "6m") -> dict:
    symbol = (ticker or "").strip().upper().replace(" ", "")
    if not TICKER.match(symbol):
        raise DataSourceError("Use an exchange ticker symbol such as AAPL, MSFT, NOVO-B.CO or ^GSPC.")
    period = period if period in PERIODS else "6m"
    range_, interval = PERIODS[period]
    try:
        data = await _fetch(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                            {"range": range_, "interval": interval, "includeAdjustedClose": "true"}, cache_ttl=600)
    except DataSourceError as error:
        if str(error) == "not found":
            raise DataSourceError(f"No price data found for {symbol}. Check the ticker symbol and exchange suffix "
                                  "(for example NOVO-B.CO for Copenhagen, 7203.T for Tokyo).") from None
        if "." not in symbol and "^" not in symbol and interval == "1d":
            return await _stooq_history(symbol, period)
        raise
    results = (data.get("chart") or {}).get("result") or []
    if not results:
        raise DataSourceError(f"No price data found for {symbol}.")
    result = results[0]
    meta = result.get("meta") or {}
    offset = int(meta.get("gmtoffset") or 0)
    stamps = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    points = [(datetime.fromtimestamp(stamp + offset, timezone.utc).date().isoformat(), round(float(close), 4))
              for stamp, close in zip(stamps, quotes) if isinstance(close, (int, float))]
    # Daily data can repeat the current session; keep one point per date.
    points = list(dict(points).items())
    if len(points) < 2:
        raise DataSourceError(f"Not enough price data for {symbol} in that period.")
    name = meta.get("longName") or meta.get("shortName") or symbol
    return {"symbol": symbol, "name": name, "currency": meta.get("currency") or "", "exchange": meta.get("fullExchangeName")
            or meta.get("exchangeName") or "", "interval": interval, "period": period, "points": points, "provider": "Yahoo Finance",
            "summary": summarize_series(points),
            "source": _source(f"{name} ({symbol}) price history", f"https://finance.yahoo.com/quote/{symbol}/history")}


async def _stooq_history(symbol: str, period: str) -> dict:
    text = await _fetch("https://stooq.com/q/d/l/", {"s": f"{symbol.lower()}.us", "i": "d"}, as_json=False, cache_ttl=600)
    rows = [line.split(",") for line in text.strip().splitlines()[1:]]
    days = {"1m": 31, "3m": 92, "6m": 183, "ytd": (date.today() - date(date.today().year, 1, 1)).days + 1,
            "1y": 366, "2y": 731}.get(period, 183)
    since = (date.today() - timedelta(days=days)).isoformat()
    points = [(row[0], round(float(row[4]), 4)) for row in rows if len(row) >= 5 and row[0] >= since and row[4] not in ("", "null")]
    if len(points) < 2:
        raise DataSourceError(f"No price data found for {symbol}.")
    return {"symbol": symbol, "name": symbol, "currency": "USD", "exchange": "US", "interval": "1d", "period": period,
            "points": points, "summary": summarize_series(points), "provider": "Stooq",
            "source": _source(f"{symbol} price history (Stooq)", f"https://stooq.com/q/d/?s={symbol.lower()}.us")}


# ── Exchange rates (European Central Bank reference rates via Frankfurter) ─────────────────────────
CURRENCY = re.compile(r"^[A-Z]{3}$")


async def exchange_rates(base: str, symbols: list[str], start: str | None = None, end: str | None = None) -> dict:
    base = (base or "").strip().upper()
    symbols = [s.strip().upper() for s in (symbols or []) if s and s.strip()][:6]
    if not CURRENCY.match(base) or not symbols or not all(CURRENCY.match(s) for s in symbols):
        raise DataSourceError("Use three-letter currency codes, for example base EUR and symbols USD, GBP.")
    params = {"from": base, "to": ",".join(s for s in symbols if s != base)}
    if not params["to"]:
        raise DataSourceError("Choose at least one currency different from the base currency.")
    try:
        if start:
            for value in (start, end):
                if value and not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                    raise DataSourceError("Dates must look like 2026-01-31.")
            data = await _fetch(f"https://api.frankfurter.app/{start}..{end or ''}", params, cache_ttl=3600)
        else:
            data = await _fetch("https://api.frankfurter.app/latest", params, cache_ttl=900)
    except DataSourceError as error:
        if str(error) == "not found":
            raise DataSourceError("Those currencies are not covered. Rates are the European Central Bank's reference "
                                  "rates for about 30 major currencies.") from None
        raise
    url = "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html"
    if start:
        series = {symbol: [(day, rates[symbol]) for day, rates in sorted((data.get("rates") or {}).items()) if symbol in rates]
                  for symbol in params["to"].split(",")}
        series = {symbol: points for symbol, points in series.items() if len(points) >= 2}
        if not series:
            raise DataSourceError("No exchange rates were published for that period.")
        return {"base": base, "series": series, "summaries": {s: summarize_series(p) for s, p in series.items()},
                "source": _source(f"ECB reference rates, {base} to {', '.join(series)}", url)}
    rates = data.get("rates") or {}
    if not rates:
        raise DataSourceError("No exchange rates were returned.")
    return {"base": base, "date": data.get("date"), "rates": rates,
            "source": _source(f"ECB reference rates on {data.get('date')}", url)}


# ── Economic indicators (IMF World Economic Outlook first, World Bank for the rest and as a fallback) ──
INDICATORS = {
    "gdp": ("NY.GDP.MKTP.CD", "GDP (current US$)", "US$"),
    "gdp_growth": ("NY.GDP.MKTP.KD.ZG", "GDP growth (annual %)", "%"),
    "gdp_per_capita": ("NY.GDP.PCAP.CD", "GDP per capita (current US$)", "US$"),
    "inflation": ("FP.CPI.TOTL.ZG", "Inflation, consumer prices (annual %)", "%"),
    "unemployment": ("SL.UEM.TOTL.ZS", "Unemployment (% of labour force)", "%"),
    "population": ("SP.POP.TOTL", "Population", ""),
    "health_spending": ("SH.XPD.CHEX.GD.ZS", "Current health expenditure (% of GDP)", "%"),
    "life_expectancy": ("SP.DYN.LE00.IN", "Life expectancy at birth (years)", "years"),
    "exports": ("NE.EXP.GNFS.ZS", "Exports of goods and services (% of GDP)", "%"),
    "government_debt": ("GC.DOD.TOTL.GD.ZS", "Central government debt (% of GDP)", "%"),
    "current_account": ("BN.CAB.XOKA.GD.ZS", "Current account balance (% of GDP)", "%"),
}
# The same measures in the IMF World Economic Outlook: faster, more current, and with IMF projections.
IMF_INDICATORS = {
    "gdp": ("NGDPD", "GDP, current prices (US$ billions)", "US$ bn"),
    "gdp_growth": ("NGDP_RPCH", "Real GDP growth (annual %)", "%"),
    "gdp_per_capita": ("NGDPDPC", "GDP per capita, current prices (US$)", "US$"),
    "inflation": ("PCPIPCH", "Inflation, average consumer prices (annual %)", "%"),
    "unemployment": ("LUR", "Unemployment rate (% of labour force)", "%"),
    "population": ("LP", "Population (millions)", "million"),
    "government_debt": ("GGXWDG_NGDP", "General government gross debt (% of GDP)", "%"),
    "current_account": ("BCA_NGDPD", "Current account balance (% of GDP)", "%"),
}
COUNTRY = re.compile(r"^[A-Z]{2,3}$")
# Two-letter codes the model often uses, for the IMF (which needs three letters). Others go to the World Bank.
ISO3 = dict(pair.split(":") for pair in (
    "US:USA CN:CHN JP:JPN DE:DEU IN:IND GB:GBR UK:GBR FR:FRA IT:ITA CA:CAN BR:BRA RU:RUS KR:KOR AU:AUS MX:MEX ES:ESP "
    "ID:IDN NL:NLD SA:SAU TR:TUR CH:CHE PL:POL BE:BEL SE:SWE AR:ARG NO:NOR AT:AUT IE:IRL IL:ISR AE:ARE TH:THA SG:SGP "
    "DK:DNK PH:PHL MY:MYS ZA:ZAF EG:EGY NG:NGA VN:VNM BD:BGD PK:PAK CL:CHL CO:COL FI:FIN PT:PRT CZ:CZE RO:ROU NZ:NZL "
    "GR:GRC HU:HUN PE:PER KE:KEN UA:UKR HK:HKG TW:TWN QA:QAT KW:KWT MA:MAR LK:LKA NP:NPL ET:ETH GH:GHA SK:SVK LU:LUX "
    "HR:HRV SI:SVN BG:BGR LT:LTU LV:LVA EE:EST IS:ISL CY:CYP MT:MLT").split())
IMF_API = "https://www.imf.org/external/datamapper/api/v1"


async def _imf_indicator(codes: list[str], indicator: str, start_year: int, end_year: int) -> dict:
    imf_code, label, unit = IMF_INDICATORS[indicator]
    iso3 = [ISO3.get(code, code) for code in codes]
    if not all(len(code) == 3 for code in iso3):
        raise DataSourceError("Unknown country code for the IMF.")
    # The API returns every country for an indicator; one cached download serves every question about it.
    values, names = await asyncio.gather(
        _fetch(f"{IMF_API}/{imf_code}", cache_ttl=21600, timeout=httpx.Timeout(12, connect=5), attempts=2),
        _fetch(f"{IMF_API}/countries", cache_ttl=86400, timeout=httpx.Timeout(12, connect=5), attempts=2))
    table = ((values or {}).get("values") or {}).get(imf_code) or {}
    labels = (names or {}).get("countries") or {}
    series = {}
    for code in iso3:
        points = [(year, round(float(value), 4)) for year, value in (table.get(code) or {}).items()
                  if value is not None and str(year).isdigit() and start_year <= int(year) <= end_year]
        if points:
            series[(labels.get(code) or {}).get("label") or code] = sorted(points)
    if not series:
        raise DataSourceError("The IMF has no data for those countries and years.")
    return {"indicator": indicator, "label": label, "unit": unit, "series": series, "provider": "IMF",
            "projections_from": date.today().year,
            "source": _source(f"IMF World Economic Outlook: {label}", f"https://www.imf.org/external/datamapper/{imf_code}")}


async def economic_indicator(countries: list[str], indicator: str, start_year: int, end_year: int) -> dict:
    if indicator not in INDICATORS:
        raise DataSourceError("Choose one of: " + ", ".join(INDICATORS))
    codes = [c.strip().upper() for c in (countries or []) if c and c.strip()][:6]
    if not codes or not all(COUNTRY.match(code) for code in codes):
        raise DataSourceError("Use ISO country codes such as DEU, FRA, USA or IND.")
    this_year = date.today().year
    try:
        start_year, end_year = int(start_year), int(end_year)
    except (TypeError, ValueError):
        raise DataSourceError("Give the start and end years as numbers, e.g. 2015 and 2025.") from None
    start_year = max(1960, start_year)
    if start_year > end_year:
        raise DataSourceError("The start year must be before the end year.")
    if indicator in IMF_INDICATORS:
        try:
            # The IMF also publishes projections a few years ahead; they are labelled as such.
            return await _imf_indicator(codes, indicator, start_year, min(end_year, this_year + 5))
        except DataSourceError as error:
            logger.info("[DataSources] IMF unavailable for %s, using the World Bank: %s", indicator, error)
    return await _world_bank_indicator(codes, indicator, start_year, min(end_year, this_year))


async def _world_bank_indicator(codes: list[str], indicator: str, start_year: int, end_year: int) -> dict:
    if start_year > end_year:
        raise DataSourceError("The World Bank only publishes past years.")
    code, label, unit = INDICATORS[indicator]
    params = {"format": "json", "date": f"{start_year}:{end_year}", "per_page": 1000}
    url = "https://api.worldbank.org/v2/country/{}/indicator/" + code
    try:
        # The combined request is usually fast but sometimes stalls; then ask for each country in parallel.
        data = await _fetch(url.format(";".join(codes)), params, cache_ttl=86400, timeout=httpx.Timeout(12, connect=5), attempts=1)
        rows = data[1] if isinstance(data, list) and len(data) > 1 and data[1] else []
    except DataSourceError:
        parts = await asyncio.gather(*(_fetch(url.format(c), params, cache_ttl=86400, timeout=httpx.Timeout(15, connect=5),
                                              attempts=1) for c in codes), return_exceptions=True)
        if all(isinstance(part, BaseException) for part in parts):
            raise DataSourceError("The World Bank is not responding right now. Try again shortly.") from None
        rows = [row for part in parts if isinstance(part, list) and len(part) > 1 and part[1] for row in part[1]]
    if not rows:
        raise DataSourceError("The World Bank has no data for those countries and years. Check the ISO country codes.")
    series: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        if row.get("value") is None:
            continue
        name = (row.get("country") or {}).get("value") or row.get("countryiso3code") or "?"
        series.setdefault(name, []).append((str(row.get("date")), round(float(row["value"]), 4)))
    series = {name: sorted(points) for name, points in series.items() if points}
    if not series:
        raise DataSourceError("The World Bank has not published values for those years yet.")
    return {"indicator": indicator, "label": label, "unit": unit, "series": series, "provider": "World Bank",
            "projections_from": None,
            "source": _source(f"World Bank: {label}", f"https://data.worldbank.org/indicator/{code}")}


# ── Clinical trials (ClinicalTrials.gov API v2) ───────────────────────────────────────────────────
TRIAL_STATUSES = {"recruiting": "RECRUITING", "active": "ACTIVE_NOT_RECRUITING", "completed": "COMPLETED",
                  "not_yet_recruiting": "NOT_YET_RECRUITING", "terminated": "TERMINATED"}
TRIAL_PHASES = {"1": "PHASE1", "2": "PHASE2", "3": "PHASE3", "4": "PHASE4"}


DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


async def clinical_trials(query: str | None = None, sponsor: str | None = None, status: str | None = None,
                          phase: str | None = None, started_after: str | None = None, started_before: str | None = None,
                          limit: int = 8) -> dict:
    query, sponsor = (query or "").strip()[:200], (sponsor or "").strip()[:120]
    if not query and not sponsor:
        raise DataSourceError("Give a condition, drug or intervention, or a sponsor company.")
    for value in (started_after, started_before):
        if value and not DAY.match(value):
            raise DataSourceError("Dates must look like 2026-01-31.")
    filters = []
    phase_digit = re.search(r"[1-4]", str(phase or ""))  # "3", "Phase 3", "PHASE3"
    if phase_digit:
        filters.append(f"AREA[Phase]{TRIAL_PHASES[phase_digit.group()]}")
    if started_after or started_before:
        filters.append(f"AREA[StartDate]RANGE[{started_after or 'MIN'},{started_before or 'MAX'}]")
    params = {"pageSize": max(1, min(int(limit or 8), 15)), "countTotal": "true",
              "sort": "StartDate:desc" if (started_after or started_before) else "LastUpdatePostDate:desc",
              "fields": "NCTId,BriefTitle,OverallStatus,Phase,LeadSponsorName,StartDate,PrimaryCompletionDate,Condition,"
                        "InterventionName,EnrollmentCount"}
    if query:
        params["query.term"] = query
    if sponsor:
        params["query.spons"] = sponsor
    if status and status in TRIAL_STATUSES:
        params["filter.overallStatus"] = TRIAL_STATUSES[status]
    if filters:
        params["filter.advanced"] = " AND ".join(filters)
    data = await _fetch("https://clinicaltrials.gov/api/v2/studies", params, cache_ttl=3600)
    trials = []
    for study in data.get("studies") or []:
        section = study.get("protocolSection") or {}
        ident = section.get("identificationModule") or {}
        nct = ident.get("nctId")
        if not nct:
            continue
        status_module = section.get("statusModule") or {}
        design = section.get("designModule") or {}
        trials.append({
            "nct_id": nct, "title": ident.get("briefTitle", ""),
            "status": (status_module.get("overallStatus") or "").replace("_", " ").lower(),
            "phase": ", ".join(p.replace("PHASE", "Phase ").replace("EARLY_", "Early ") for p in design.get("phases") or []) or "n/a",
            "sponsor": ((section.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name", ""),
            "start": (status_module.get("startDateStruct") or {}).get("date", ""),
            "primary_completion": (status_module.get("primaryCompletionDateStruct") or {}).get("date", ""),
            "conditions": (section.get("conditionsModule") or {}).get("conditions", [])[:4],
            "interventions": [i.get("name") for i in (section.get("armsInterventionsModule") or {}).get("interventions", [])][:4],
            "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
        })
    return {"total": data.get("totalCount", len(trials)), "trials": trials,
            "sources": [_source(f"{t['nct_id']}: {t['title']}", f"https://clinicaltrials.gov/study/{t['nct_id']}",
                                f"{t['phase']} · {t['status']} · {t['sponsor']} · start {t['start']}") for t in trials]}


# ── PubMed (NCBI E-utilities) ─────────────────────────────────────────────────────────────────────
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


async def pubmed(query: str, limit: int = 6, newest_first: bool = False, since_year: int | None = None) -> dict:
    query = (query or "").strip()[:300]
    if not query:
        raise DataSourceError("Describe what to search for.")
    limit = max(1, min(int(limit or 6), 10))
    params = {"db": "pubmed", "term": query, "retmax": limit, "retmode": "json",
              "sort": "pub_date" if newest_first else "relevance"}
    if since_year and 1900 < int(since_year) <= date.today().year:
        # A date filter, so the model never has to write PubMed's [dp] syntax (which it combines incorrectly).
        params.update(datetype="pdat", mindate=str(int(since_year)), maxdate=str(date.today().year))
    found = await _fetch(f"{EUTILS}/esearch.fcgi", params, cache_ttl=3600)
    ids = ((found.get("esearchresult") or {}).get("idlist") or [])[:limit]
    total = int((found.get("esearchresult") or {}).get("count") or 0)
    if not ids:
        return {"total": total, "articles": [], "sources": []}
    summary, abstracts = await asyncio.gather(
        _fetch(f"{EUTILS}/esummary.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}, cache_ttl=86400),
        _fetch(f"{EUTILS}/efetch.fcgi", {"db": "pubmed", "id": ",".join(ids), "rettype": "abstract", "retmode": "xml"},
               as_json=False, cache_ttl=86400))
    texts = _pubmed_abstracts(abstracts)
    articles = []
    for pmid in ids:
        item = (summary.get("result") or {}).get(pmid) or {}
        if not item.get("title"):
            continue
        authors = [a.get("name") for a in item.get("authors") or [] if a.get("name")]
        articles.append({"pmid": pmid, "title": item["title"].rstrip("."), "journal": item.get("fulljournalname") or item.get("source", ""),
                         "date": item.get("pubdate", ""), "authors": (", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")),
                         "types": [t for t in item.get("pubtype") or []][:3], "abstract": texts.get(pmid, "")[:1200]})
    return {"total": total, "articles": articles,
            "sources": [_source(a["title"], f"https://pubmed.ncbi.nlm.nih.gov/{a['pmid']}/",
                                f"{a['journal']} ({a['date']}). {a['abstract']}") for a in articles]}


def _pubmed_abstracts(xml_text: str) -> dict[str, str]:
    abstracts = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return abstracts
    for article in root.iter("PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        parts = []
        for node in article.iter("AbstractText"):
            text = " ".join("".join(node.itertext()).split())
            label = node.get("Label")
            category = (node.get("NlmCategory") or label or "").upper()
            if text:
                parts.append((ABSTRACT_ORDER.get(category, 3), f"{label}: {text}" if label else text))
        if pmid and parts:
            # Findings first: abstracts are shortened for the model, and the numbers live in results and conclusions.
            abstracts[pmid] = " ".join(text for _, text in sorted(parts, key=lambda part: part[0]))
    return abstracts


ABSTRACT_ORDER = {"CONCLUSIONS": 0, "CONCLUSION": 0, "INTERPRETATION": 0, "RESULTS": 1, "FINDINGS": 1,
                  "METHODS": 2, "DESIGN": 2, "PARTICIPANTS": 2}


# ── FDA approvals (openFDA Drugs@FDA) ─────────────────────────────────────────────────────────────
async def fda_approvals(drug: str | None = None, approved_since: str | None = None, limit: int = 6) -> dict:
    """A drug's application and approval history, or recent original approvals of new drugs and biologics."""
    limit = max(1, min(int(limit or 6), 10))
    if drug:
        name = re.sub(r"[^A-Za-z0-9 \-]", "", drug).strip().upper()[:80]
        if not name:
            raise DataSourceError("Give a brand or generic drug name, or a sponsor.")
        search = f'openfda.brand_name:"{name}" openfda.generic_name:"{name}" sponsor_name:"{name}"'
        try:
            data = await _fetch("https://api.fda.gov/drug/drugsfda.json", {"search": search, "limit": limit}, cache_ttl=21600)
        except DataSourceError as error:
            if str(error) == "not found":
                return {"applications": [], "sources": [], "note": f"No FDA application found for {drug}."}
            raise
        applications = [_fda_application(item) for item in data.get("results") or []]
    else:
        try:
            since = datetime.strptime(approved_since or "", "%Y-%m-%d").date()
        except ValueError:
            since = date.today() - timedelta(days=30)
        window = f"[{since:%Y%m%d} TO {date.today():%Y%m%d}]"
        search = (f'submissions.submission_type:"ORIG" AND submissions.submission_status:"AP" AND '
                  f'submissions.submission_status_date:{window} AND (application_number:NDA* OR application_number:BLA*)')
        try:
            data = await _fetch("https://api.fda.gov/drug/drugsfda.json", {"search": search, "limit": 100}, cache_ttl=21600)
        except DataSourceError as error:
            if str(error) == "not found":
                return {"applications": [], "sources": [], "note": f"No new NDA or BLA approvals since {since}."}
            raise
        applications = []
        for item in data.get("results") or []:
            application = _fda_application(item)
            # Keep only applications whose original approval falls in the window (not later supplements).
            if application["original_approval"] and application["original_approval"] >= since.isoformat():
                applications.append(application)
        applications.sort(key=lambda a: a["original_approval"], reverse=True)
        applications = applications[:limit]
        if not applications:
            return {"applications": [], "sources": [], "note": f"No new NDA or BLA approvals since {since} in openFDA yet. "
                    "openFDA is updated weekly and can lag recent approvals; check FDA's Novel Drug Approvals page with web search."}
    return {"applications": applications, "lag_note": "openFDA is updated weekly and can lag the most recent approvals by days or weeks.",
            "sources": [_source(f"Drugs@FDA: {a['brand'] or a['generic']} ({a['application']})", a["url"],
                                f"{a['sponsor']}. Original approval {a['original_approval'] or 'n/a'}. "
                                f"{a['ingredients']}") for a in applications]}


def _fda_application(item: dict) -> dict:
    number = item.get("application_number", "")
    openfda = item.get("openfda") or {}
    products = item.get("products") or []
    ingredients = sorted({f"{i.get('name', '').title()} {i.get('strength', '')}".strip()
                          for p in products for i in p.get("active_ingredients") or []})
    approvals = sorted((s for s in item.get("submissions") or [] if s.get("submission_status") == "AP"),
                       key=lambda s: s.get("submission_status_date", ""))
    iso = lambda value: f"{value[:4]}-{value[4:6]}-{value[6:8]}" if value and len(value) == 8 else ""
    original = next((iso(s.get("submission_status_date")) for s in approvals if s.get("submission_type") == "ORIG"), "")
    recent = [f"{iso(s.get('submission_status_date'))} {s.get('submission_class_code_description') or s.get('submission_type', '')}".strip()
              for s in approvals[-4:]]
    digits = re.sub(r"\D", "", number)
    return {"application": number, "sponsor": item.get("sponsor_name", "").title(),
            "brand": ", ".join(sorted({(p.get("brand_name") or "").title() for p in products if p.get("brand_name")}))
            or ", ".join(openfda.get("brand_name") or []).title(),
            "generic": ", ".join(openfda.get("generic_name") or []).title(), "ingredients": "; ".join(ingredients)[:300],
            "original_approval": original, "recent_approvals": recent,
            "url": f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={digits}"}


# ── arXiv ─────────────────────────────────────────────────────────────────────────────────────────
ATOM = {"a": "http://www.w3.org/2005/Atom"}


async def arxiv(query: str, limit: int = 5, newest_first: bool = False) -> dict:
    query = (query or "").strip()[:200]
    if not query:
        raise DataSourceError("Describe what to search for.")
    terms = " AND ".join(f'all:"{word}"' if " " in word else f"all:{word}"
                         for word in re.findall(r'"[^"]+"|\S+', query.replace('"', ' ').strip())[:8])
    text = await _fetch("https://export.arxiv.org/api/query",
                        {"search_query": terms, "max_results": max(1, min(int(limit or 5), 10)),
                         "sortBy": "submittedDate" if newest_first else "relevance", "sortOrder": "descending"},
                        as_json=False, cache_ttl=3600)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise DataSourceError("arXiv returned data that could not be read.") from None
    papers = []
    for entry in root.findall("a:entry", ATOM):
        title = " ".join((entry.findtext("a:title", "", ATOM) or "").split())
        link = entry.findtext("a:id", "", ATOM)
        if not title or not link:
            continue
        authors = [a.findtext("a:name", "", ATOM) for a in entry.findall("a:author", ATOM)]
        papers.append({"title": title, "url": link, "published": (entry.findtext("a:published", "", ATOM) or "")[:10],
                       "authors": ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
                       "summary": " ".join((entry.findtext("a:summary", "", ATOM) or "").split())[:900]})
    return {"papers": papers, "sources": [_source(p["title"], p["url"], f"{p['published']}. {p['summary']}") for p in papers]}
