"""Shared Spaces API: context, files, members, invitations and shared threads."""
import asyncio
import hashlib
import logging
from typing import Literal, Optional
from urllib.parse import urlsplit
from uuid import uuid4
from email_validator import validate_email, EmailNotValidError
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from src.api.deps import get_current_user_id, get_db
from src.config.settings import settings
from src.services import space_files, space_service as spaces

logger = logging.getLogger(__name__)
router = APIRouter()
EXTRACTION_TIMEOUT = 90


def clean_links(links: list[str]) -> list[str]:
    cleaned = []
    for link in links:
        link = link.strip()
        if link and "://" not in link:
            link = "https://" + link
        parsed = urlsplit(link)
        if (len(link) > 2048 or parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or "." not in parsed.hostname):
            raise ValueError("Links must be web addresses such as https://example.com")
        normalized = parsed.geturl() if parsed.path else parsed.geturl() + "/"
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


class SpaceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    instructions: Optional[str] = Field(default=None, max_length=8000)
    icon: Optional[str] = None
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    links: Optional[list[str]] = Field(default=None, max_length=100)
    webSearch: Optional[bool] = None
    template: Optional[str] = Field(default=None, max_length=40)

    @field_validator("template")
    @classmethod
    def known_template(cls, value):
        from src.services.agents import space_templates
        if value is not None and space_templates.get(value) is None:
            raise ValueError("Choose one of the available templates")
        return value

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip() if value else value

    @field_validator("description", "instructions")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if value else value

    @field_validator("icon")
    @classmethod
    def known_icon(cls, value):
        if value is not None and value not in spaces.ICONS:
            raise ValueError("Choose one of the available icons")
        return value

    @field_validator("links")
    @classmethod
    def safe_links(cls, value):
        return clean_links(value) if value is not None else value

    def values(self) -> dict:
        return self.model_dump(exclude_none=True)


class SpaceCreate(SpaceFields):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def has_name(self):
        # A template supplies its own name; otherwise one is required.
        if not self.name and not self.template:
            raise ValueError("Name the Space or choose a template")
        return self


class SpaceUpdate(SpaceFields):
    expected_revision: int = Field(ge=1, le=2**31 - 1)

    @model_validator(mode="after")
    def has_changes(self):
        if not self.model_dump(exclude_none=True, exclude={"expected_revision"}):
            raise ValueError("Provide at least one change")
        return self


class InviteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["editor", "viewer"] = "viewer"
    email: Optional[str] = Field(default=None, max_length=254)

    @field_validator("email")
    @classmethod
    def normalized_email(cls, value):
        if not value or not value.strip():
            return None
        try:
            return validate_email(value.strip(), check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            raise ValueError("Enter a valid email address") from None


class RoleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["owner", "editor", "viewer"]


class ThreadSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: dict


class ImportSpace(SpaceCreate):
    legacyId: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    threads: list[dict] = Field(default_factory=list, max_length=100)


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spaces: list[ImportSpace] = Field(min_length=1, max_length=20)


# Fixed paths are declared before /{space_id} routes.

@router.get("")
async def list_spaces(user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return {"items": await spaces.list_spaces(db, user)}


@router.post("", status_code=201)
async def create_space(body: SpaceCreate, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    space = await spaces.create_space(db, user, body.values())
    await db.commit()
    return await spaces.get_space(db, str(space.id), user)


@router.post("/import")
async def import_spaces(body: ImportRequest, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    """Move Spaces saved only in a browser by the earlier design. Repeating is harmless.

    Spaces that reached personal cloud storage were already moved by migration 0004, so the
    server's state wins: a Space deleted since then is never recreated from a stale device.
    """
    from sqlalchemy import select
    from uuid import UUID
    from src.models.space import Space
    from src.models.personal_record import PersonalRecord
    imported, skipped = {}, []
    for item in body.spaces:
        existing = await db.scalar(select(Space.id).where(Space.owner_id == UUID(user), Space.legacy_id == item.legacyId))
        if existing:
            imported[item.legacyId] = str(existing)
            continue
        if await db.get(PersonalRecord, (UUID(user), "spaces", item.legacyId)):
            skipped.append(item.legacyId)
            continue
        space = await spaces.create_space(db, user, item.values(), legacy_id=item.legacyId)
        for thread in item.threads:
            thread_id = str(thread.get("id", ""))
            try:
                await spaces.save_thread(db, str(space.id), user, thread_id, thread)
            except HTTPException:
                continue  # One unreadable conversation must not block importing the Space.
        imported[item.legacyId] = str(space.id)
    await db.commit()
    return {"imported": imported, "skipped": skipped}


@router.get("/templates")
async def list_templates(user: str = Depends(get_current_user_id)):
    """Templates and the tools each one gives a Space's agent."""
    from src.services.agents import space_templates
    return {"items": [space_templates.public(t) for t in space_templates.TEMPLATES],
            "featured": list(space_templates.FEATURED), "categories": list(space_templates.CATEGORIES)}


@router.get("/invitations")
async def my_invitations(user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return {"items": await spaces.my_invitations(db, user)}


@router.post("/invitations/{invite_id}/accept")
async def accept_invitation(invite_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    space_id = await spaces.respond_invitation(db, invite_id, user, True)
    await db.commit()
    return {"spaceId": space_id}


@router.post("/invitations/{invite_id}/decline", status_code=204)
async def decline_invitation(invite_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    await spaces.respond_invitation(db, invite_id, user, False)
    await db.commit()


@router.get("/join/{token}")
async def preview_invite(token: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return await spaces.preview_invite(db, token, user)


@router.post("/join/{token}")
async def accept_invite(token: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    space_id = await spaces.accept_link(db, token, user)
    await db.commit()
    return {"spaceId": space_id}


@router.get("/{space_id}")
async def get_space(space_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return await spaces.get_space(db, space_id, user)


@router.patch("/{space_id}")
async def update_space(space_id: str, body: SpaceUpdate, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    result = await spaces.update_space(db, space_id, user, body.model_dump(exclude_none=True, exclude={"expected_revision"}),
                                       body.expected_revision)
    await db.commit()
    return result


@router.delete("/{space_id}", status_code=204)
async def delete_space(space_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    removed = await spaces.delete_space(db, space_id, user)
    await db.commit()
    await asyncio.to_thread(space_files.remove_space, removed)


# ── Members ──────────────────────────────────────────────────────────────────

@router.get("/{space_id}/members")
async def list_members(space_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return await spaces.members(db, space_id, user)


@router.post("/{space_id}/invites", status_code=201)
async def create_invite(space_id: str, body: InviteCreate, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    result = await spaces.create_invite(db, space_id, user, body.role, body.email)
    await db.commit()
    return result


@router.delete("/{space_id}/invites/{invite_id}", status_code=204)
async def revoke_invite(space_id: str, invite_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    await spaces.revoke_invite(db, space_id, user, invite_id)
    await db.commit()


@router.patch("/{space_id}/members/{member_id}", status_code=204)
async def change_role(space_id: str, member_id: str, body: RoleChange, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    await spaces.change_role(db, space_id, user, member_id, body.role)
    await db.commit()


@router.delete("/{space_id}/members/{member_id}", status_code=204)
async def remove_member(space_id: str, member_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    await spaces.remove_member(db, space_id, user, member_id)
    await db.commit()


# ── Threads ──────────────────────────────────────────────────────────────────

@router.get("/{space_id}/threads")
async def list_threads(space_id: str, before: Optional[int] = Query(None, ge=0, le=2**53 - 1),
        user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return await spaces.list_threads(db, space_id, user, before)


@router.get("/{space_id}/threads/{thread_id}")
async def get_thread(space_id: str, thread_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return await spaces.get_thread(db, space_id, user, thread_id)


@router.put("/{space_id}/threads/{thread_id}")
async def save_thread(space_id: str, thread_id: str, body: ThreadSave, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    result = await spaces.save_thread(db, space_id, user, thread_id, body.data)
    await db.commit()
    return result


@router.delete("/{space_id}/threads/{thread_id}", status_code=204)
async def remove_thread(space_id: str, thread_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    await spaces.remove_thread(db, space_id, user, thread_id)
    await db.commit()


# ── Files ────────────────────────────────────────────────────────────────────

@router.get("/{space_id}/files")
async def list_files(space_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return {"items": await spaces.list_files(db, space_id, user)}


@router.post("/{space_id}/files", status_code=201)
async def upload_file(space_id: str, file: UploadFile = File(...), user: str = Depends(get_current_user_id), db=Depends(get_db)):
    try:
        name = space_files.clean_filename(file.filename or "")
        ext = space_files.extension(name)
    except space_files.FileRejected as error:
        raise HTTPException(415, str(error)) from None
    data = await file.read(settings.SPACE_MAX_FILE_BYTES + 1)
    if len(data) > settings.SPACE_MAX_FILE_BYTES:
        raise HTTPException(413, f"Files must be no larger than {settings.SPACE_MAX_FILE_BYTES // (1024 * 1024)} MB.")
    if not data:
        raise HTTPException(422, "This file is empty.")
    digest = hashlib.sha256(data).hexdigest()
    space, _ = await spaces.access(db, space_id, user, "editor")
    await spaces.check_file_quota(db, space, len(data), digest)
    try:
        text = await asyncio.wait_for(asyncio.to_thread(space_files.extract_text, name, data), EXTRACTION_TIMEOUT)
    except space_files.FileRejected as error:
        raise HTTPException(422, str(error)) from None
    except asyncio.TimeoutError:
        raise HTTPException(422, "This file took too long to read. Try a smaller or simpler file.") from None
    except Exception:
        logger.exception("Space file extraction failed")
        raise HTTPException(422, "This file could not be read. Check that it is not damaged.") from None
    chunks = space_files.chunk_text(text)
    # Extraction ran without a lock; re-check limits while holding it for the insert.
    await db.rollback()
    space, _ = await spaces.access(db, space_id, user, "editor", lock=True)
    await spaces.check_file_quota(db, space, len(data), digest)
    file_id = uuid4()
    await asyncio.to_thread(space_files.store, space.id, file_id, data)
    try:
        result = await spaces.add_file(db, space, user, file_id, name, space_files.content_type(ext), len(data),
                                       digest, chunks)
        await db.commit()
    except BaseException:
        await asyncio.to_thread(space_files.remove, space.id, file_id)
        raise
    return result


@router.get("/{space_id}/files/{file_id}/download")
async def download_file(space_id: str, file_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    item = await spaces.get_file(db, space_id, user, file_id)
    path = space_files.file_path(item.space_id, item.id)
    if not path.is_file():
        raise HTTPException(404, "The stored copy of this file is unavailable.")
    # Always a download: uploaded HTML or PDF is never rendered on the application origin.
    return FileResponse(path, media_type="application/octet-stream", filename=item.filename,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy": "sandbox"})


@router.delete("/{space_id}/files/{file_id}", status_code=204)
async def delete_file(space_id: str, file_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    item = await spaces.delete_file(db, space_id, user, file_id)
    await db.commit()
    await asyncio.to_thread(space_files.remove, item.space_id, item.id)
