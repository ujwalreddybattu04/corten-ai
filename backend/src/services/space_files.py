"""Space knowledge files: bounded text extraction, chunking and private disk storage.

Uploaded bytes are never executed or rendered. Office files are read as ZIP/XML with
decompression limits; DTDs are refused so entity expansion is impossible.
"""
import io
import os
import re
import unicodedata
import zipfile
import zlib
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from uuid import UUID
from src.config.settings import settings

MAX_EXTRACTED_CHARS = 2_000_000
MAX_PDF_PAGES = 2000
MAX_ZIP_UNCOMPRESSED = 200 * 1024 * 1024
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".log", ".rst", ".tex",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb",
    ".php", ".swift", ".kt", ".scala", ".sql", ".sh", ".r", ".m", ".ini", ".toml", ".css", ".srt", ".vtt",
}
HTML_EXTENSIONS = {".html", ".htm"}
SUPPORTED = TEXT_EXTENSIONS | HTML_EXTENSIONS | {".pdf", ".docx", ".pptx", ".xlsx"}
CONTENT_TYPES = {".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv", ".html": "text/html", ".htm": "text/html", ".json": "application/json"}


class FileRejected(ValueError):
    """A user-correctable problem with an uploaded file."""


def clean_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", os.path.basename((name or "").replace("\\", "/")))
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip(" .")
    if not name:
        raise FileRejected("The file needs a name.")
    if len(name) > 255:
        stem, ext = os.path.splitext(name)
        name = stem[:255 - len(ext)] + ext
    return name


def extension(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext not in SUPPORTED:
        raise FileRejected("This file type is not supported. Upload PDF, Word (.docx), PowerPoint (.pptx), "
                           "Excel (.xlsx), HTML or text files.")
    return ext


def content_type(ext: str) -> str:
    return CONTENT_TYPES.get(ext, "text/plain")


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if b"\x00" in data[:8192]:
        raise FileRejected("This file appears to be binary rather than text.")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


class _HtmlText(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "td", "th"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"): self.skip += 1
        elif tag in self.BLOCK: self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self.skip: self.skip -= 1

    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


def _xml(data: bytes):
    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data.upper():
        raise FileRejected("This document contains unsupported XML declarations.")
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        raise FileRejected("This document is damaged or not a valid Office file.") from None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _zip_members(data: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise FileRejected("This document is damaged or not a valid Office file.") from None
    if sum(item.file_size for item in archive.infolist()) > MAX_ZIP_UNCOMPRESSED:
        raise FileRejected("This document expands to more data than Spaces can process.")
    return archive


def _office_text(archive: zipfile.ZipFile, names: list[str], paragraph: str) -> str:
    lines = []
    for name in names:
        root = _xml(archive.read(name))
        for block in root.iter():
            if _local(block.tag) != paragraph:
                continue
            text = "".join(node.text or "" for node in block.iter() if _local(node.tag) == "t")
            if text.strip():
                lines.append(text)
    return "\n".join(lines)


def _natural(name: str):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _xlsx_text(archive: zipfile.ZipFile) -> str:
    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        for item in _xml(archive.read("xl/sharedStrings.xml")):
            shared.append("".join(node.text or "" for node in item.iter() if _local(node.tag) == "t"))
    lines = []
    sheets = sorted((n for n in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)), key=_natural)
    for index, name in enumerate(sheets, start=1):
        lines.append(f"Sheet {index}")
        for row in _xml(archive.read(name)).iter():
            if _local(row.tag) != "row":
                continue
            cells = []
            for cell in row:
                if _local(cell.tag) != "c":
                    continue
                kind = cell.get("t")
                value = next((node.text or "" for node in cell.iter() if _local(node.tag) == "v"), "")
                if kind == "s" and value.isdigit() and int(value) < len(shared):
                    value = shared[int(value)]
                elif kind == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter() if _local(node.tag) == "t")
                cells.append(value)
            if any(value.strip() for value in cells):
                lines.append("\t".join(cells))
    return "\n".join(lines)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise FileRejected("Password-protected PDFs cannot be read. Upload an unprotected copy.")
        pages = []
        for number, page in enumerate(reader.pages[:MAX_PDF_PAGES], start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[Page {number}]\n{text}")
            if sum(map(len, pages)) > MAX_EXTRACTED_CHARS:
                break
        return "\n\n".join(pages)
    except FileRejected:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError):
        raise FileRejected("This PDF is damaged or cannot be read.") from None


def extract_text(name: str, data: bytes) -> str:
    """Return normalized searchable text, or raise FileRejected with a user-facing reason."""
    ext = extension(name)
    if ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise FileRejected("This file is not a valid PDF.")
        text = _pdf_text(data)
    elif ext in (".docx", ".pptx", ".xlsx"):
        try:
            text = _office(ext, _zip_members(data))
        except (zipfile.BadZipFile, zipfile.LargeZipFile, KeyError, EOFError, RuntimeError, zlib.error, NotImplementedError):
            raise FileRejected("This document is damaged, encrypted or not a valid Office file.") from None
    elif ext in HTML_EXTENSIONS:
        parser = _HtmlText()
        parser.feed(_decode(data))
        text = "".join(parser.parts)
    else:
        text = _decode(data)
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    # Tabs separate spreadsheet columns; keep them so tables stay readable.
    text = re.sub(r"[^\S\n\t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()[:MAX_EXTRACTED_CHARS]
    if not text:
        raise FileRejected("No readable text was found. Scanned images and image-only PDFs are not supported yet.")
    return text


def _office(ext: str, archive: zipfile.ZipFile) -> str:
    members = archive.namelist()
    if ext == ".docx":
        if "word/document.xml" not in members:
            raise FileRejected("This is not a valid Word document.")
        return _office_text(archive, ["word/document.xml"], "p")
    if ext == ".pptx":
        slides = sorted((n for n in members if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_natural)
        if not slides:
            raise FileRejected("This presentation has no readable slides.")
        return "\n\n".join(f"[Slide {i}]\n" + _office_text(archive, [n], "p") for i, n in enumerate(slides, 1))
    return _xlsx_text(archive)


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split on paragraph or sentence boundaries where possible, with overlap for context."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start:end]
            # Prefer the strongest boundary in the second half: paragraph, then line, then sentence.
            for boundary in ("\n\n", "\n", ". ", "。", "! ", "? "):
                cut = window.rfind(boundary)
                if cut > size // 2:
                    end = start + cut + len(boundary)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


# ── Private storage ──────────────────────────────────────────────────────────

def _root() -> Path:
    return Path(settings.SPACE_FILES_DIR).resolve()


def file_path(space_id: UUID, file_id: UUID) -> Path:
    # Identifiers are server-generated UUIDs; user filenames never reach the filesystem.
    return _root() / UUID(str(space_id)).hex / UUID(str(file_id)).hex


def store(space_id: UUID, file_id: UUID, data: bytes) -> None:
    target = file_path(space_id, file_id)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_suffix(".partial")
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


def remove(space_id: UUID, file_id: UUID) -> None:
    try:
        file_path(space_id, file_id).unlink()
    except FileNotFoundError:
        pass


def remove_space(space_id: UUID) -> None:
    folder = _root() / UUID(str(space_id)).hex
    if not folder.is_dir():
        return
    for item in folder.iterdir():
        try: item.unlink()
        except OSError: pass
    try: folder.rmdir()
    except OSError: pass
