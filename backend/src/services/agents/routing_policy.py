"""Conservative rules for requests that do not need external information."""

import re
from typing import Optional


def normalize_query(query: str) -> str:
    text = re.sub(r"\s+", " ", query.lower().replace("’", "'")).strip()
    return re.sub(r"\bu\b", "you", text)


def needs_external_information(query: str) -> bool:
    """Freshness and sourcing requests override generic writing/code shortcuts."""
    return bool(re.search(
        r"https?://|\b(search|browse|research|news|weather|prices?|stocks?|"
        r"earnings|laws?|regulations?|medical|diagnosis|dosage|biography|"
        r"latest|current|recent|live|updated|up.to.date|look up|fact.check|"
        r"sources|citations|references|exchange rates?|market)\b",
        normalize_query(query),
    ))


def direct_intent(query: str, brand_name: str, has_history: bool = False) -> Optional[str]:
    """Return an offline intent only when the whole request supports it.

    Do not match arbitrary substrings: 'Hi, latest AI news' and
    'Who developed you and what is the current stock price?' must search.
    """
    text = normalize_query(query)
    greeting = (r"(?:hi|hello|hey|hi there|hello there|good (?:morning|afternoon|evening)|"
                r"thanks(?: a lot)?|thank you(?: so much)?|ok(?:ay)?|bye|goodbye|"
                r"how are you(?: doing)?|what's up)")
    if re.fullmatch(greeting, text.strip(" .?!,;")):
        return "greeting"
    text = re.sub(r"^(?:(?:hi|hey|hello)[, !]+)?(?:please |can you |could you )*", "", text)
    text = re.sub(r"^tell me (?=(?:who|what|which|where|how)\b)", "", text)
    text = text.strip(" .?!,;")
    target = rf"(?:you|yourself|{re.escape(brand_name.lower())}(?: ai)?)"
    agent_target = rf"(?:you|yourself|(?:this |the )?{re.escape(brand_name.lower())}(?: ai)?|this assistant)"
    agent_patterns = [
        rf"(?:do|does) {agent_target} (?:have|use|contain|include) (?:(?:any|ai|multiple) )*agents?(?: (?:inside|within|in) {agent_target})?",
        rf"(?:do|does) you have (?:(?:any|ai|multiple) )*agents?(?: (?:inside|within|in) {agent_target})?",
        rf"(?:what|which|how many) (?:ai )?agents? (?:do|does) {agent_target} (?:have|use)",
        rf"(?:are|is) there (?:(?:any|ai) )*agents? (?:inside|within|in) {agent_target}",
        r"(?:what are|explain|describe|tell me about) your (?:ai )?agents",
        rf"how (?:do|does) (?:your agents|{agent_target}) (?:research|perform research|do research)",
        r"(?:explain|describe|what is|what's) your (?:architecture|agent architecture)",
        rf"(?:is|are) {agent_target} (?:an? )?(?:multi.agent|agent.based)(?: (?:system|assistant))?",
    ]
    capability_patterns = [
        rf"what (?:can|do) {target} do",
        r"what are your (?:capabilities|features|tools)",
        r"(?:which|what) tools do you (?:have|use)",
        r"(?:how can you help(?: me)?|what are you capable of)",
        rf"can {target} (?:search|browse)(?: (?:the )?(?:web|internet|online))?",
        rf"(?:explain|describe|tell me about) {agent_target}(?:'s)? (?:capabilities|features|tools)",
        rf"what are (?:the )?(?:capabilities|features|tools) of {agent_target}",
        rf"how (?:do|does) {agent_target} work",
    ]
    if any(re.fullmatch(pattern, text) for pattern in agent_patterns):
        return "agents"
    if any(re.fullmatch(pattern, text) for pattern in capability_patterns):
        return "capabilities"
    if re.fullmatch(r"who (?:trained you|trained your (?:model|language model))", text):
        return "training"
    identity_patterns = [
        rf"who (?:are|r) {target}",
        rf"what (?:is|are) (?:this |the )?{re.escape(brand_name.lower())}(?: ai)?",
        rf"who (?:(?:has |have )?(?:developed|created|built|made|designed|invented)|owns) {target}",
        rf"(?:which|what) company (?:developed|created|built|made) {target}",
        rf"who (?:is|was) behind {target}",
        rf"who (?:is|was) (?:your|the) (?:developer|creator|maker|owner)",
        rf"(?:what(?:'s| is)|tell me) your (?:name|identity|purpose)",
        rf"(?:tell me about yourself|introduce yourself)",
        rf"(?:are you (?:an? )?(?:ai|chatbot|assistant|chatgpt)|who developed you)",
    ]
    # Support combined identity questions without swallowing unrelated clauses.
    clauses = [part.strip(" .?!,;") for part in re.split(r"\s+and\s+", text)]
    if clauses and all(any(re.fullmatch(pattern, part) for pattern in identity_patterns) for part in clauses):
        return "identity"
    if re.fullmatch(greeting, text):
        return "greeting"

    # URLs need retrieval. Supplied text can be edited/translated even if it
    # contains words such as 'latest news'; those words are content, not intent.
    if re.search(r"https?://", text):
        return None
    if has_history and re.fullmatch(
        r"(?:(?:make|keep) (?:it|that|your answer|the above) (?:(?:much|a bit|more|less) )?"
        r"(?:shorter|longer|formal|concise|detailed|simpler|clearer)|"
        r"(?:shorten|expand) (?:it|that|your answer)|"
        r"explain (?:it|that|your answer) in (?:simpler|simple) (?:terms|words))", text
    ):
        return "text"
    transformation = re.match(
        r"(?:translate|rewrite|rephrase|proofread|edit|summari[sz]e|"
        r"explain (?:this|the following) (?:code|text))\b", text,
    )
    if transformation:
        supplied = re.search(r"[:\n]\s*\S.{7,}|[\"']\S.+[\"']", query, re.DOTALL)
        prior_text = has_history and re.search(r"\b(above|previous|that|it|your answer)\b", text)
        if supplied or (prior_text and not needs_external_information(text)):
            return "text"

    if needs_external_information(text):
        return None
    # A generic workspace explanation needs no invented project-specific inputs.
    if re.fullmatch(
        r"(?:write|draft) (?:(?:me|a|an|one|two|2|short|brief|simple|concise|sentences?|paragraph|explanation) )*"
        r"(?:explain(?:ing)?|about|on) (?:forecast|forecasting) assumptions"
        r"(?: (?:to|for) (?:(?:a|the|our) )?(?:team|analysts|forecasting team))?", text
    ):
        return "forecast_explanation"
    expression = re.sub(r"^(?:what is|what's|calculate|compute|solve)\s+", "", text)
    if re.fullmatch(r"[\d\s.+*/%()^=-]+", expression) and re.search(r"\d", expression):
        return "math"
    if re.fullmatch(r"(?:sqrt|abs|sin|cos|tan|log|round|factorial)\([\d\s.+*/()-]+\)", expression):
        return "math"
    if re.match(r"(?:write|draft|compose|create|generate)\s+(?:me\s+)?(?:an?\s+)?"
                r"(?:(?:professional|formal|polite|leave|sick leave|short|simple)\s+)?"
                r"(?:email|letter|poem|story|joke|birthday (?:message|wish)|cover letter|"
                r"thank.you (?:note|message)|apology|invitation)\b", text):
        return "creative"
    if re.match(r"(?:write|create|generate|implement|fix|debug)\b", text) and re.search(
        r"\b(code|function|script|algorithm|regex|sql query|program)\b", text
    ):
        return "code"
    return None
