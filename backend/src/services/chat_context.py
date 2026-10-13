"""Per-question context beyond the text: answer mode, attachments and personalization."""
import math
import re
from dataclasses import dataclass, field
from src.services.space_files import chunk_text
from src.services.space_service import CJK, query_terms, _score

ATTACHMENT_DOMAIN = "Attachment"
# The question points at material already in the conversation ("the brief", "this PDF", "summarize it").
CONTEXT_REFERENCE = re.compile(
    r"\b(?:summari[sz]e|attached|attachments?|uploaded)\b|"
    r"\b(?:the|this|that|these|those|my|our|earlier|previous|above)\s+(?:files?|documents?|docs?|pdfs?|briefs?|"
    r"reports?|memos?|decks?|slides|spreadsheets?|sheets?|notes|text|contract|proposal|transcript)\b", re.I)


# Asking for information beyond the attached files.
OUTSIDE_INFORMATION = re.compile(
    r"\b(?:latest|current(?:ly)?|today|recent(?:ly)?|news|web|online|internet|google|search|compare|comparison|versus|vs)\b",
    re.I)
# Words that only say what to do with a file, not what to look up.
_INSTRUCTION_WORDS = set("""whats what's explain describe summarize summarise summary tell check read analyse analyze review
translate mean means meaning please document documents file files pdf doc image picture photo screenshot details detail
info information content contents say says kind type thing something anything understand help""".split())


def about_attachments(query: str) -> bool:
    """Whether a question sent together with files is about those files ("what's this?", "summarize it",
    "is this valid?") rather than the wider world. Such questions are answered from the files only:
    a web search for "what's this" finds unrelated pages (a song of that name) instead."""
    if OUTSIDE_INFORMATION.search(query):
        return False
    terms = [term for term in query_terms(query) if term not in _INSTRUCTION_WORDS]
    if len(terms) <= 3:
        return True
    return bool(CONTEXT_REFERENCE.search(query) or re.search(r"\b(?:this|these|it|attached)\b", query, re.I)) \
        and len(terms) <= 6


# Words that only point at the workspace itself ("what is this Space for?", "what can I do here?").
_SPACE_WORDS = set("space spaces here project workspace purpose about use used using work works start begin can".split())
_POINTING = re.compile(r"\b(?:this|here|space|it|you|what|how|help)\b", re.I)
# Words that only ask for recent changes, with no topic of their own ("what's new?", "any updates this week?").
_FRESHNESS_WORDS = set("new news latest recent recently update updates updated today week weekly month monthly year "
                       "changes changed happening developments trends any".split())


def refers_to_context(query: str) -> bool:
    """A question with nothing of its own to look up ("what's this about?", "what is this Space for?",
    "how does this work?"). It refers to its context: the Space when it opens a thread there, the previous
    answer in a follow-up, attached files when sent with them. Searching the web for the phrase itself
    finds dictionary entries and song lyrics instead."""
    if OUTSIDE_INFORMATION.search(query):
        return False
    terms = [term for term in query_terms(query) if term not in _INSTRUCTION_WORDS and term not in _SPACE_WORDS]
    return not terms and bool(_POINTING.search(query))


def freshness_only(query: str) -> bool:
    """A request for what is new with no topic of its own. Inside a Space the topic is the Space."""
    terms = query_terms(query)
    return bool(terms) and all(term in _FRESHNESS_WORDS or term in _INSTRUCTION_WORDS or term.isdigit() for term in terms) \
        and any(term in _FRESHNESS_WORDS for term in terms)


def document_relevant(doc: dict, query: str) -> bool:
    """Whether a document from an earlier message bears on this question: the question refers to it,
    names it, or shares a good part of its key words with it. Unrelated follow-ups (a diagram, a
    question about the user) are then answered normally instead of from the document."""
    if CONTEXT_REFERENCE.search(query):
        return True
    terms = [term for term in query_terms(query) if len(term) >= 4 or term.isdigit()]
    if not terms:
        # Questions written in scripts without word spacing cannot be matched by words; keep the document.
        return bool(CJK.search(query))
    name = doc["name"].lower()
    if any(term in name for term in terms if not term.isdigit()):
        return True
    text = doc["text"].lower()
    return sum(term in text for term in terms) >= max(1, math.ceil(len(terms) * 0.4))


@dataclass
class TurnContext:
    mode: str = "auto"
    # Documents attached to this message: dicts with id, name and extracted text. Always read.
    documents: list[dict] = field(default_factory=list)
    # Documents from earlier messages in the conversation. Read only when relevant to the question.
    context_documents: list[dict] = field(default_factory=list)
    # Attached images as data URLs, ready for the vision model.
    images: list[str] = field(default_factory=list)
    image_names: list[str] = field(default_factory=list)
    # Prompt block with the user's saved memory, style and personal instructions.
    personal: str = ""
    # Private chats never read or write memory.
    incognito: bool = False
    # Account that receives files Corten creates during this answer.
    user_id: str | None = None


def attachment_sources(documents: list[dict], query: str, budget: int) -> list[dict]:
    """Cite each attached document once. Small documents go in whole; large ones contribute
    their most relevant passages, in document order, within the evidence budget."""
    if not documents:
        return []
    share = max(2000, budget // len(documents))
    sources = []
    terms = query_terms(query)
    for doc in documents:
        text = doc["text"]
        if len(text) > share:
            chunks = chunk_text(text, size=1500, overlap=0)
            # The opening usually carries the title and summary; then the best-matching passages.
            ranked = sorted(range(len(chunks)), key=lambda i: (-_score(chunks[i], terms), i))
            chosen, used = {0}, len(chunks[0])
            for index in ranked:
                if used + len(chunks[index]) > share:
                    continue
                chosen.add(index)
                used += len(chunks[index])
            text = "\n…\n".join(chunks[i] for i in sorted(chosen))
        sources.append({"title": doc["name"], "url": f"/api/v1/attachments/{doc['id']}/content",
                        "domain": ATTACHMENT_DOMAIN, "snippet": text, "snippet_limit": share,
                        "source_type": "attachment"})
    return sources
