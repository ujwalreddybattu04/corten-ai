"""Read explicitly labelled office addresses without asking a model to infer them."""
import re
from urllib.parse import urlsplit
from src.config.settings import settings

from src.services.agents.query_context import company_alias


def official_office_answer(query: str, sources: list, company_name: str) -> str | None:
    """Use a verified contact-page section; changed/missing layouts fall back to review.

    Addresses are copied from live evidence, never stored as company facts in code.
    Founding locations, operating regions and other prose are not address evidence.
    """
    if not re.search(r"\b(?:where|located|locations?|headquarters?|headquartered|hq|offices?|based|registered)\b", query, re.I):
        return None
    if re.search(r"\b(?:and|also|compare|versus|vs|ceo|founder|services?|products?|business)\b", query, re.I):
        return None
    headquarters = bool(re.search(r"\b(?:headquarters?|headquartered|hq)\b", query, re.I))
    registered = bool(re.search(r"\bregistered\b", query, re.I))
    if (headquarters or registered) and any(re.search(
        r"\b(?:headquarters?|headquartered|registered (?:office|address))\b", source.get("snippet", ""), re.I
    ) for source in sources):
        return None  # Explicit headquarters evidence belongs in the reviewed synthesis.
    for source in sources:
        parsed = urlsplit(source.get("url", ""))
        official_host = (urlsplit(settings.COMPANY_WEBSITE).hostname or "").removeprefix("www.")
        host = (parsed.hostname or "").removeprefix("www.")
        if parsed.scheme not in {"http", "https"} or host != official_host or parsed.path.rstrip("/") != "/contact-us":
            continue
        text = source.get("snippet", "")
        heading = re.search(r"(?im)^#{1,6}\s*(?:our\s+)?office locations\s*$", text)
        if not heading:
            continue
        section = re.split(r"(?m)^\s*(?:#{1,6}\s|!\[|\[!\[)", text[heading.end():], maxsplit=1)[0]
        blocks = [re.sub(r"\s+", " ", block).strip() for block in re.split(r"\n\s*\n", section)]
        addresses = [block for block in blocks if 10 <= len(block) <= 500
                     and re.search(r"\d", block) and not re.search(r"https?://|\[|\]", block)]
        if not 1 <= len(addresses) <= 12:
            return None
        citation = source.get("citationIndex")
        if not isinstance(citation, int):
            return None
        prefix = ""
        if headquarters:
            prefix = "I couldn’t verify a designated headquarters from the retrieved official sources. "
        elif registered:
            prefix = "I couldn’t verify a registered legal address from the retrieved official sources. "
        return (prefix + f"{company_alias(company_name)} lists these office locations on its contact page:\n\n" +
                "\n".join(f"- {address} [{citation}]" for address in addresses))
    return None
