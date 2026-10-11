"""Small, validated chat headings, including provider-independent fallbacks."""
import re


def is_greeting(query: str) -> bool:
    return bool(re.fullmatch(
        r"\s*(?:hi|hello|hey|hello there|good (?:morning|afternoon|evening))"
        r"(?:\s+(?:corten|there|assistant))?[\s!?.]*", query, re.I,
    ))


def fallback_title(query: str) -> str:
    """Extract a topic rather than displaying a question or request verb."""
    if is_greeting(query):
        return "New Conversation"
    if re.search(r"\b(?:previous|last|first|earlier|past)\b.*\b(?:question|message|chat)\b", query, re.I):
        return "Conversation Recap"
    if re.search(r"\b(?:who (?:created|developed|made) you|your (?:creator|developer))\b", query, re.I):
        return "About Corten"
    if re.search(r"\b(?:code|coding|script|program|function)\b", query, re.I):
        for language in ("Python", "JavaScript", "TypeScript", "Java", "SQL", "Rust", "Go"):
            if re.search(rf"\b{language}\b", query, re.I):
                return f"{language} Coding"
    if re.search(r"\bforecast(?:ing|s)?\b", query, re.I) and re.search(r"\b(?:pharma|pharmaceutical|drug)\b", query, re.I):
        return "Pharma Forecasting"
    project = re.search(r"\b(?:my |our |the )?project\s+(?:is |named |called |codename (?:is )?)?([\w-]+)", query, re.I)
    if project and re.search(r"\b(?:remember|note|keep in mind)\b", query, re.I):
        return f"{project.group(1).title()} Project Notes"
    topic = re.sub(r'^\s*(?:regarding|summarize)\s+(?:the\s+)?article\s*', '', query, flags=re.I)
    topic = re.sub(r"https?://\S+", "", topic)
    stop = set("i me my you your we our a an the is are was were do does did can could would should please "
               "what whats who where when why how tell explain describe give show help about of to for and in on "
               "it this that need want write create make generate summarize summary regarding article remember "
               "keep mind that has have with from".split())
    words = [w for w in re.findall(r"[\w]+(?:[-'][\w]+)*", topic) if w.lower() not in stop]
    if not words:
        return "General Discussion"
    words = words[:5]
    if len(words) == 1:
        words.append("Discussion")
    return " ".join(w if w.isupper() else w[0].upper() + w[1:] for w in words)[:64].rstrip()


def validate_title(value: object, query: str) -> str | None:
    if not isinstance(value, str):
        return None
    title = value.strip().strip('"\'`')
    title = re.sub(r"^(?:chat )?title:\s*", "", title, flags=re.I).strip()
    title = title.strip('"\'`').rstrip('.!?')
    if "\n" in title or len(title) > 64 or not 2 <= len(title.split()) <= 6:
        return None
    if re.search(r"[<>\[\]{}#*]|https?://", title) or re.match(
        r"^(?:who|what|where|when|why|how|can|could|please|write|tell|give|generate|summarize)\b", title, re.I,
    ):
        return None
    if title.casefold().rstrip('?.!') == query.strip().casefold().rstrip('?.!'):
        return None
    return title
