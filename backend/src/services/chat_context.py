"""Per-question context beyond the text: answer mode, attachments and personalization."""
from dataclasses import dataclass, field
from src.services.space_files import chunk_text
from src.services.space_service import query_terms, _score

ATTACHMENT_DOMAIN = "Attachment"


@dataclass
class TurnContext:
    mode: str = "auto"
    # Attached documents: dicts with id, name and extracted text.
    documents: list[dict] = field(default_factory=list)
    # Attached images as data URLs, ready for the vision model.
    images: list[str] = field(default_factory=list)
    image_names: list[str] = field(default_factory=list)
    # Prompt block with the user's saved memory, style and personal instructions.
    personal: str = ""
    # Private chats never read or write memory.
    incognito: bool = False
    # Account that receives files Corten creates during this answer.
    user_id: str | None = None

    @property
    def document_chars(self) -> int:
        return sum(len(doc["text"]) for doc in self.documents)


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
