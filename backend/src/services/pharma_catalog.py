"""Verified source coverage and conservative drug-name matching."""
import hashlib
import re
import unicodedata
from collections import deque

SOURCE_CATALOG = {
    "fda": {"name":"FDA · Drugs@FDA","url":"https://open.fda.gov/apis/drug/drugsfda/","cadence":"Weekday dataset updates","scope":"US approved submissions; all therapy areas"},
    "trials": {"name":"ClinicalTrials.gov","url":"https://clinicaltrials.gov/data-api/api","cadence":"As registry records are posted","scope":"Global drug and biologic study events"},
    "fda_updates": {"name":"FDA · Drug announcements","url":"https://www.fda.gov/drugs/news-events-human-drugs","cadence":"As FDA publishes","scope":"FDA drug announcements; publication dates"},
    "fda_safety": {"name":"FDA · Drug safety","url":"https://www.fda.gov/drugs/drug-safety-and-availability","cadence":"As FDA publishes","scope":"Drug-relevant MedWatch publications and classified drug enforcement reports"},
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


class AliasMatcher:
    """Single-pass literal matching with Unicode word boundaries and overlapping aliases."""
    def __init__(self,aliases):
        self.nodes=[{}];self.failure=[0];self.outputs=[[]]
        for alias,drug in aliases.items():
            state=0
            for character in alias:
                if character not in self.nodes[state]:
                    self.nodes[state][character]=len(self.nodes)
                    self.nodes.append({});self.failure.append(0);self.outputs.append([])
                state=self.nodes[state][character]
            self.outputs[state].append((len(alias),drug))
        pending=deque(self.nodes[0].values())
        while pending:
            parent=pending.popleft()
            for character,child in self.nodes[parent].items():
                pending.append(child);fallback=self.failure[parent]
                while fallback and character not in self.nodes[fallback]:fallback=self.failure[fallback]
                self.failure[child]=self.nodes[fallback].get(character,0)
                self.outputs[child].extend(self.outputs[self.failure[child]])

    def match(self,text):
        state=0;found=set()
        def word(c):return c.isalnum() or c=='_'
        for index,character in enumerate(text):
            while state and character not in self.nodes[state]:state=self.failure[state]
            state=self.nodes[state].get(character,0)
            for length,drug in self.outputs[state]:
                start=index-length+1
                if (start==0 or not word(text[start-1])) and (index+1==len(text) or not word(text[index+1])):found.add(drug)
        return sorted(found)[:8]


def mentioned_drugs(item, aliases, matcher=None):
    details = item.get("details") or {}
    values = [item.get("title",""),item.get("summary",""),
              *(details.get("ingredients") or []),*(details.get("interventions") or [])]
    text = " ".join(unicodedata.normalize("NFKC"," ".join(values)).casefold().split())
    return (matcher or AliasMatcher(aliases)).match(text)
