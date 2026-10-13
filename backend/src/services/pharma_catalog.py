"""Verified source coverage and conservative drug-name matching."""
import hashlib
import re
import unicodedata

SOURCE_CATALOG = {
    "fda": {"name":"FDA · Drugs@FDA","url":"https://open.fda.gov/apis/drug/drugsfda/","cadence":"Weekday dataset updates","scope":"US approved submissions; all therapy areas"},
    "trials": {"name":"ClinicalTrials.gov","url":"https://clinicaltrials.gov/data-api/api","cadence":"As registry records are posted","scope":"Global drug and biologic study events"},
    "fda_updates": {"name":"FDA · Drug announcements","url":"https://www.fda.gov/drugs/news-events-human-drugs","cadence":"As FDA publishes","scope":"FDA drug announcements; publication dates"},
    "fda_safety": {"name":"FDA · Drug safety","url":"https://www.fda.gov/drugs/drug-safety-and-availability","cadence":"As FDA publishes","scope":"Drug-relevant MedWatch publications; current feed coverage"},
    "ema": {"name":"EMA · Medicines","url":"https://www.ema.europa.eu/en/medicines","cadence":"Published dataset twice daily","scope":"EU centralised human medicines; opinions and authorisation decisions distinguished"},
    "company": {"name":"Company press releases","url":"https://news.bms.com/news/default.aspx","cadence":"Monitored public releases","scope":"BMS, Pfizer, Novartis, AstraZeneca and Amgen; indexed publication dates"},
    "news": {"name":"Pharma trade reporting","url":"https://pharmatimes.com/","cadence":"Publisher feeds and indexed reporting","scope":"Attributed pharma/biotech reporting; headlines and short summaries"},
}
COMPANIES = {"bms.com":"Bristol Myers Squibb","pfizer.com":"Pfizer","novartis.com":"Novartis",
             "astrazeneca.com":"AstraZeneca","amgen.com":"Amgen"}
TRADE_DOMAINS = ("pharmatimes.com","fiercebiotech.com","fiercepharma.com","pharmaphorum.com")

# Requested identity is explicitly documented by FDA-SRS, not guessed by an LLM.
VERIFIED_IDENTITIES = [{"name":"luspatercept","ingredients":["luspatercept"],
    "aliases":["Reblozyl","luspatercept","luspatercept-aamt"],
    "evidence_url":"https://precision.fda.gov/uniisearch/srs/unii/AQK7UBA1LS"}]


def normalize_name(value):
    return re.sub(r"\s+"," ",unicodedata.normalize("NFKC",value).casefold()).strip()[:240]


def drug_identity(ingredients):
    # Combination products keep a distinct identity; component drugs are not merged.
    names = sorted({normalize_name(value) for value in ingredients if isinstance(value,str) and value.strip()})
    if not names:
        return None
    for identity in VERIFIED_IDENTITIES:
        if len(names)==1 and names[0] in {normalize_name(a) for a in identity["aliases"]}:
            names = [identity["name"]]
    return hashlib.sha256(("ingredients:"+"|".join(names)).encode()).hexdigest()


def unique_aliases(rows):
    """A shared name mapping to multiple products stays ambiguous."""
    result = {}
    for alias,drug in rows:
        result.setdefault(normalize_name(alias),set()).add(drug)
    return {alias:next(iter(drugs)) for alias,drugs in result.items() if len(drugs)==1}


def mentioned_drugs(item, aliases):
    details = item.get("details") or {}
    values = [item.get("title",""),item.get("summary",""),
              *(details.get("ingredients") or []),*(details.get("interventions") or [])]
    text = normalize_name(" ".join(values)) if sum(len(v) for v in values)<240 else unicodedata.normalize("NFKC"," ".join(values)).casefold()
    return sorted({drug for alias,drug in aliases.items() if re.search(r"(?<!\w)"+re.escape(alias)+r"(?!\w)",text)})[:8]
