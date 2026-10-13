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
