"""Chat attachments: images for the vision model, documents as cited text, and generated files.

Images are decoded and re-encoded as JPEG, which removes metadata (such as GPS location)
and anything that is not image data. Files are stored under server-generated UUID paths.
"""
import base64
import io
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import select, func
from src.config.settings import settings
from src.models.attachment import ChatAttachment
from src.services import space_files

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MAX_IMAGE_SIDE = 2048
MAX_IMAGE_PIXELS = 50_000_000
MAX_DOCUMENT_CHARS = 400_000
MAX_PER_QUESTION = 10
MAX_IMAGES_PER_QUESTION = 5


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _root() -> Path:
    return Path(settings.SPACE_FILES_DIR).resolve() / "attachments"


def file_path(user_id: UUID, attachment_id: UUID) -> Path:
    return _root() / UUID(str(user_id)).hex / UUID(str(attachment_id)).hex


def _store(user_id: UUID, attachment_id: UUID, data: bytes) -> None:
    target = file_path(user_id, attachment_id)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_suffix(".partial")
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


def _remove(user_id: UUID, attachment_id: UUID) -> None:
    try:
        file_path(user_id, attachment_id).unlink()
    except FileNotFoundError:
        pass


def normalize_image(data: bytes) -> bytes:
    """Decode, bound and re-encode an image as JPEG. Raises FileRejected for anything unsafe."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP", "GIF", "BMP", "MPO"}:
                raise space_files.FileRejected("Upload images as PNG, JPEG, WebP, GIF or BMP.")
            source.seek(0)
            image = ImageOps.exif_transpose(source)  # respect camera orientation before dropping metadata
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])
                image = background
            else:
                image = image.convert("RGB")
            image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue()
    except space_files.FileRejected:
        raise
    except Image.DecompressionBombError:
        raise space_files.FileRejected("This image is too large to process.") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise space_files.FileRejected("This image is damaged or not a supported format.") from None


def view(item: ChatAttachment) -> dict:
    return {"id": str(item.id), "name": item.filename, "kind": item.kind, "size": item.size_bytes,
            "contentType": item.content_type, "characters": item.char_count,
            "url": f"/api/v1/attachments/{item.id}/content",
            "createdAt": int(aware(item.created_at).timestamp() * 1000),
            "expiresAt": int(aware(item.expires_at).timestamp() * 1000)}


async def purge_expired(db, user_id: UUID, limit: int = 50) -> int:
    rows = (await db.scalars(select(ChatAttachment).where(ChatAttachment.user_id == user_id,
        ChatAttachment.expires_at <= now()).limit(limit))).all()
    for row in rows:
        _remove(row.user_id, row.id)
        await db.delete(row)
    return len(rows)


async def _check_quota(db, user_id: UUID, size: int):
    count, total = (await db.execute(select(func.count(), func.coalesce(func.sum(ChatAttachment.size_bytes), 0))
        .where(ChatAttachment.user_id == user_id))).one()
    if count >= settings.ATTACHMENT_MAX_PER_USER or total + size > settings.ATTACHMENT_MAX_TOTAL_BYTES:
        raise HTTPException(413, "Your file storage is full. Delete older attachments in Settings to add more.")


def prepare_upload(name: str, data: bytes) -> tuple[str, str, bytes, str | None]:
    """Validate and convert an upload. Returns (kind, content_type, stored_bytes, extracted_text)."""
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image", "image/jpeg", normalize_image(data), None
    space_files.extension(name)  # raises FileRejected for unsupported types
    text = space_files.extract_text(name, data)[:MAX_DOCUMENT_CHARS]
    return "document", space_files.content_type(ext), data, text


async def save_upload(db, user_id: str, name: str, kind: str, content_type: str, data: bytes, text: str | None,
                      digest: str) -> dict:
    owner = UUID(user_id)
    await purge_expired(db, owner)
    await _check_quota(db, owner, len(data))
    item = ChatAttachment(id=uuid4(), user_id=owner, filename=name, content_type=content_type, kind=kind,
                          size_bytes=len(data), sha256=digest, text=text, char_count=len(text or ""),
                          created_at=now(), expires_at=now() + timedelta(days=settings.ATTACHMENT_RETENTION_DAYS))
    _store(owner, item.id, data)
    try:
        db.add(item)
        await db.flush()
    except BaseException:
        _remove(owner, item.id)
        raise
    return view(item)


async def owned(db, user_id: str, attachment_id: str) -> ChatAttachment:
    try:
        key = UUID(attachment_id)
    except ValueError:
        raise HTTPException(404, "Attachment not found") from None
    item = await db.get(ChatAttachment, key)
    if not item or item.user_id != UUID(user_id) or aware(item.expires_at) <= now():
        raise HTTPException(404, "This attachment is no longer available.")
    return item


async def remove_attachment(db, user_id: str, attachment_id: str):
    item = await owned(db, user_id, attachment_id)
    _remove(item.user_id, item.id)
    await db.delete(item)


async def list_for_user(db, user_id: str, limit: int = 200) -> list[dict]:
    rows = (await db.scalars(select(ChatAttachment).where(ChatAttachment.user_id == UUID(user_id),
        ChatAttachment.expires_at > now()).order_by(ChatAttachment.created_at.desc()).limit(limit))).all()
    return [view(row) for row in rows]


async def load_for_turn(db, user_id: str, ids: list[str]) -> tuple[list[dict], list[str], list[str]]:
    """Documents (id, name, text), image data URLs and image names for one question.

    Unknown or expired IDs are skipped, so a later follow-up still works after old files expire.
    """
    keys = []
    for value in ids[:MAX_PER_QUESTION]:
        try:
            keys.append(UUID(value))
        except ValueError:
            continue
    if not keys:
        return [], [], []
    rows = {row.id: row for row in (await db.scalars(select(ChatAttachment).where(
        ChatAttachment.id.in_(keys), ChatAttachment.user_id == UUID(user_id), ChatAttachment.expires_at > now()))).all()}
    documents, images, names = [], [], []
    for key in keys:
        row = rows.get(key)
        if not row:
            continue
        if row.kind == "document" and row.text:
            documents.append({"id": str(row.id), "name": row.filename, "text": row.text})
        elif row.kind == "image" and len(images) < MAX_IMAGES_PER_QUESTION:
            path = file_path(row.user_id, row.id)
            if path.is_file():
                images.append("data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode())
                names.append(row.filename)
    return documents, images, names


async def store_generated(db, user_id: str, name: str, content_type: str, data: bytes) -> dict:
    """Save a file Corten created (document, spreadsheet, presentation) for download."""
    import hashlib
    return await save_upload(db, user_id, name, "generated", content_type, data, None, hashlib.sha256(data).hexdigest())
