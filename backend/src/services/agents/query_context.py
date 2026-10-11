"""Bounded conversation context and conservative follow-up resolution."""
import re


def clean_history(messages: list | None) -> list[dict[str, str]]:
    """Client history is conversation data, never trusted system instructions."""
    return [
        {"role": message["role"], "content": message["content"][:3000]}
        for message in (messages or [])[-12:]
        if isinstance(message, dict) and message.get("role") in {"user", "assistant"}
        and isinstance(message.get("content"), str) and message["content"].strip()
    ]


def company_alias(company_name: str) -> str:
    return re.sub(r"\b(?:services|private|limited|pvt|ltd)\b\.?", "", company_name,
                  flags=re.IGNORECASE).strip()


def mentions_company(query: str, company_name: str) -> bool:
    alias = company_alias(company_name)
    return bool(alias and re.search(rf"\b{re.escape(alias)}\b", query, re.IGNORECASE))


def is_contextual(query: str) -> bool:
    # Supplied-text editing does not require turning every pronoun into an entity.
    if re.match(r"\s*(?:translate|rewrite|rephrase|proofread|edit|summari[sz]e)\b", query, re.I):
        return False
    query = re.sub(r"\b(will|does|is|can|could) it (?=(?:rain|snow|hail|drizzle)\b)", r"\1 ", query, flags=re.I)
    return bool(re.search(r"\b(?:it|its|they|their|them|these|those|the company|that company|this company|"
                          r"that place|this place)\b", query, re.I)
                or re.search(r"\b(?:located|based|offices?) there\b", query, re.I)
                or re.match(r"\s*(?:what|how) about\b", query, re.I)
                or re.fullmatch(r"\s*(?:location|headquarters|offices|tell me more|more details)[\s?.!]*", query, re.I))


def ambiguous_comparison_followup(query: str, history: list) -> bool:
    """A singular pronoun after a comparison has no safe entity to search for."""
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    return bool(re.search(r"\b(?:compare|versus|vs)\b", last_user, re.I) and re.match(
        r"\s*(?:and )?(?:where|when|what|who|how)\s+(?:(?:is|was|does|did|are|do|can|has|will) )?(?:it|its)\b",
        query, re.I))


def resolve_company_followup(query: str, history: list, company_name: str, brand_name: str = "Corten") -> str:
    """Resolve org pronouns only after an unambiguous company/developer question.

    Prefer the previous user's subject over incidental names in an assistant answer.
    CEO/person, comparisons and topic switches remain for the general resolver.
    """
    if not is_contextual(query) or mentions_company(query, company_name):
        return query
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    company_topic = mentions_company(last_user, company_name) and not re.search(
        r"\b(?:ceo|founder|president|director|compare|versus|vs)\b", last_user, re.I)
    from src.services.agents.routing_policy import direct_intent
    developer_topic = (direct_intent(last_user, brand_name) == "identity" and
                       bool(re.search(r"developed|created|built|made|developer|creator", last_user, re.I)))
    if not (company_topic or developer_topic):
        return query
    # Only questions whose pronoun clearly represents an organization.
    if not re.search(r"\b(?:located|location|headquarters|offices?|based|business|"
                     r"services?|products?|work|do|does|operate)\b", query, re.I):
        return query
    return re.sub(r"\b(?:it|its|they|their|them|that company|this company)\b",
                  company_alias(company_name), query, flags=re.I)


def resolve_named_followup(query: str, history: list) -> str:
    """Resolve simple single-entity questions without relying on classifier JSON.

    Complex previous questions and lowercase ambiguous names stay with the validated
    model resolver. Only an explicit, bounded name from the previous user is reused.
    """
    if not is_contextual(query):
        return query
    last_user = next((message["content"] for message in reversed(history) if message["role"] == "user"), "")
    match = re.fullmatch(r"\s*(?:what is|who is|tell me about)\s+(.+?)[\s?!.]*", last_user, re.I)
    if not match:
        return query
    entity = match.group(1).strip()
    if (not 2 <= len(entity) <= 100 or len(entity.split()) > 6 or not entity[0].isupper()
            or re.search(r"\b(?:and|or|difference|between|ceo|founder|president|director|versus|vs)\b", entity, re.I)):
        return query
    resolved = re.sub(r"\b(?:it|its|they|their|them|the company|this company|that company)\b",
                      lambda _: entity, query, flags=re.I)
    if re.fullmatch(r"\s*(?:location|headquarters|offices)[\s?.!]*", query, re.I):
        return f"{entity} {query.strip(' ?.!!')}"
    return resolved


def validated_standalone(query: str, candidate: object, entity: object, history: list) -> str | None:
    """Accept a resolver's entity only when it occurs in the immediate conversation."""
    if not isinstance(candidate, str) or not isinstance(entity, str):
        return None
    candidate, entity = candidate.strip(), entity.strip()
    if not candidate or len(candidate) > 1000 or not 2 <= len(entity) <= 120:
        return None
    if entity.lower() in {"it", "they", "company", "the company", "place", "there", "this"}:
        return None
    recent = (query + " " + " ".join(message["content"] for message in history[-2:])).casefold()
    if entity.casefold() not in recent or entity.casefold() not in candidate.casefold():
        return None
    if is_contextual(candidate) or candidate.casefold() == query.strip().casefold():
        return None
    return candidate
