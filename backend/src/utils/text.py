"""Text processing utilities — chunking, cleaning."""
import re


def clean_text(text: str) -> str:
    """Remove extra whitespace and normalize."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, max_chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), max_chunk_size - overlap):
        chunk = " ".join(words[i : i + max_chunk_size])
        chunks.append(chunk)
    return chunks


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.replace("www.", "")
    except Exception:
        return url
