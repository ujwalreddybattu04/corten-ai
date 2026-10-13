"""Shared Spaces: role checks, CRUD, invitations, shared threads and file retrieval.

Roles: owner (everything, members, delete) > editor (ask, files, context) > viewer (read).
Non-members receive 404 so Space identifiers never reveal that a Space exists.
"""
import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import select, func, delete, text, or_
from src.config.settings import settings
from src.models.space import Space, SpaceMember, SpaceInvite, SpaceFile, SpaceFileChunk, SpaceThread
from src.models.user import User

ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}
# Icon names from the first design, kept for existing Spaces, plus the emoji offered by the icon picker.
EMOJI = ("💊", "🧬", "🔬", "🧪", "🏥", "📊", "📈", "💼", "🏛️", "⚖️", "🌍", "🚀", "🎯", "💡", "🧠", "📚",
         "📝", "🗂️", "📌", "🔍", "🤝", "🛠️", "💻", "🎓", "✈️", "🏠", "🎨", "📣", "💰", "🗓️", "⭐", "🌱")
ICONS = {"bookmark", "folder", "book", "briefcase", "code", "lightbulb", "graduation", "beaker", "pen", "trending", *EMOJI}
LINK_INVITE_DAYS = 7
EMAIL_INVITE_DAYS = 14
MAX_THREAD_BYTES = 256 * 1024
THREAD_PAGE = 50


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def ms(value: datetime | None) -> int | None:
    value = aware(value)
    return int(value.timestamp() * 1000) if value else None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def parse_uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError:
        raise HTTPException(404, "Space not found") from None


# ── Access ───────────────────────────────────────────────────────────────────

async def access(db, space_id, user_id, minimum="viewer", lock=False) -> tuple[Space, str]:
    statement = (select(Space, SpaceMember.role).join(SpaceMember, SpaceMember.space_id == Space.id)
                 .where(Space.id == parse_uuid(space_id), SpaceMember.user_id == UUID(user_id)))
    if lock:
        statement = statement.with_for_update(of=Space)
    row = (await db.execute(statement)).first()
    if not row:
        raise HTTPException(404, "Space not found")
    space, role = row
    if ROLE_RANK.get(role, 0) < ROLE_RANK[minimum]:
        raise HTTPException(403, {"viewer": "You do not have access to this Space.",
            "editor": "Only editors and the owner can do this. Ask the owner for edit access.",
            "owner": "Only the Space owner can do this."}[minimum])
    return space, role


def serialize(space: Space, role: str, counts: dict | None = None, owner_name: str | None = None) -> dict:
    counts = counts or {}
    return {
        "id": str(space.id), "name": space.name, "description": space.description or "",
        "instructions": space.custom_instructions or "", "icon": space.icon, "color": space.color,
        "links": list(space.links or []), "webSearch": bool(space.web_search), "revision": space.revision,
        "role": role, "ownerName": owner_name, "legacyId": space.legacy_id,
        "memberCount": counts.get("members", 1), "threadCount": counts.get("threads", 0),
        "fileCount": counts.get("files", 0),
        "createdAt": ms(space.created_at), "updatedAt": ms(space.updated_at),
    }


async def _counts(db, ids: list[UUID]) -> dict[UUID, dict]:
    result = {space_id: {} for space_id in ids}
    if not ids:
        return result
    for key, model, column in (("members", SpaceMember, SpaceMember.space_id),
                               ("threads", SpaceThread, SpaceThread.space_id),
                               ("files", SpaceFile, SpaceFile.space_id)):
        for space_id, count in (await db.execute(select(column, func.count()).where(column.in_(ids)).group_by(column))).all():
            result[space_id][key] = count
    return result


async def list_spaces(db, user_id) -> list[dict]:
    rows = (await db.execute(select(Space, SpaceMember.role, User.name)
        .join(SpaceMember, SpaceMember.space_id == Space.id).join(User, User.id == Space.owner_id)
        .where(SpaceMember.user_id == UUID(user_id)).order_by(Space.updated_at.desc()))).all()
    counts = await _counts(db, [space.id for space, _, _ in rows])
    return [serialize(space, role, counts[space.id], owner) for space, role, owner in rows]


async def get_space(db, space_id, user_id) -> dict:
    space, role = await access(db, space_id, user_id)
    owner = await db.scalar(select(User.name).where(User.id == space.owner_id))
    return serialize(space, role, (await _counts(db, [space.id]))[space.id], owner)


async def create_space(db, user_id, values: dict, legacy_id: str | None = None) -> Space:
    owner = UUID(user_id)
    owned = await db.scalar(select(func.count()).select_from(Space).where(Space.owner_id == owner))
    if owned >= settings.SPACE_MAX_OWNED:
        raise HTTPException(413, f"You can own up to {settings.SPACE_MAX_OWNED} Spaces. Delete one to create another.")
    space = Space(id=uuid4(), owner_id=owner, legacy_id=legacy_id, revision=1, name=values["name"],
        description=values.get("description", ""), custom_instructions=values.get("instructions", ""),
        icon=values.get("icon", "bookmark"), color=values.get("color", "#6366f1"),
        links=values.get("links", []), web_search=values.get("webSearch", True),
        created_at=now(), updated_at=now())
    db.add(space)
    db.add(SpaceMember(space_id=space.id, user_id=owner, role="owner", joined_at=now()))
    await db.flush()
    return space


FIELD_COLUMNS = {"name": "name", "description": "description", "instructions": "custom_instructions",
    "icon": "icon", "color": "color", "links": "links", "webSearch": "web_search"}


async def update_space(db, space_id, user_id, changes: dict, expected_revision: int) -> dict:
    space, role = await access(db, space_id, user_id, "editor", lock=True)
    if space.revision != expected_revision:
        raise HTTPException(409, "Someone else changed this Space. Reload it before saving.")
    for key, value in changes.items():
        setattr(space, FIELD_COLUMNS[key], value)
    space.revision += 1
    space.updated_at = now()
    await db.flush()
    return await get_space(db, space_id, user_id)


async def delete_space(db, space_id, user_id) -> UUID:
    space, _ = await access(db, space_id, user_id, "owner", lock=True)
    await db.delete(space)
    await db.flush()
    return space.id


async def touch(db, space: Space):
    space.updated_at = now()


# ── Members and invitations ──────────────────────────────────────────────────

async def members(db, space_id, user_id) -> dict:
    space, role = await access(db, space_id, user_id)
    rows = (await db.execute(select(SpaceMember.user_id, SpaceMember.role, SpaceMember.joined_at, User.name, User.email, User.avatar_url)
        .join(User, User.id == SpaceMember.user_id).where(SpaceMember.space_id == space.id)
        .order_by(SpaceMember.joined_at))).all()
    owner = role == "owner"
    result = {"role": role, "members": [{
        "userId": str(row.user_id), "name": row.name, "role": row.role, "joinedAt": ms(row.joined_at),
        "avatarUrl": row.avatar_url, "isYou": str(row.user_id) == user_id,
        # Member emails are personal data; only the owner manages access by email.
        **({"email": row.email} if owner or str(row.user_id) == user_id else {}),
    } for row in rows], "invites": []}
    if owner:
        invites = (await db.scalars(select(SpaceInvite).where(SpaceInvite.space_id == space.id,
            SpaceInvite.revoked_at.is_(None), SpaceInvite.accepted_at.is_(None), SpaceInvite.expires_at > now())
            .order_by(SpaceInvite.created_at.desc()))).all()
        result["invites"] = [invite_view(item) for item in invites]
    return result


def invite_view(invite: SpaceInvite) -> dict:
    return {"id": str(invite.id), "email": invite.email, "role": invite.role,
            "kind": "email" if invite.email else "link",
            "createdAt": ms(invite.created_at), "expiresAt": ms(invite.expires_at)}


async def _seats_used(db, space_id: UUID) -> int:
    members_count = await db.scalar(select(func.count()).select_from(SpaceMember).where(SpaceMember.space_id == space_id))
    pending = await db.scalar(select(func.count()).select_from(SpaceInvite).where(SpaceInvite.space_id == space_id,
        SpaceInvite.email.is_not(None), SpaceInvite.revoked_at.is_(None), SpaceInvite.accepted_at.is_(None),
        SpaceInvite.expires_at > now()))
    return members_count + pending


async def create_invite(db, space_id, user_id, role: str, email: str | None) -> dict:
    space, _ = await access(db, space_id, user_id, "owner", lock=True)
    if email:
        member = await db.scalar(select(SpaceMember.user_id).join(User, User.id == SpaceMember.user_id)
            .where(SpaceMember.space_id == space.id, func.lower(User.email) == email))
        if member:
            raise HTTPException(409, "This person is already a member of the Space.")
        existing = await db.scalar(select(SpaceInvite).where(SpaceInvite.space_id == space.id, SpaceInvite.email == email,
            SpaceInvite.revoked_at.is_(None), SpaceInvite.accepted_at.is_(None), SpaceInvite.expires_at > now()))
        if existing:
            # Replace rather than accumulate: the newest role and link win.
            existing.revoked_at = now()
            await db.flush()
        if await _seats_used(db, space.id) >= settings.SPACE_MAX_MEMBERS:
            raise HTTPException(413, f"A Space can have up to {settings.SPACE_MAX_MEMBERS} members and pending invitations.")
    token = secrets.token_urlsafe(32)
    invite = SpaceInvite(id=uuid4(), space_id=space.id, token_hash=token_hash(token), email=email, role=role,
        created_by=UUID(user_id), created_at=now(),
        expires_at=now() + timedelta(days=EMAIL_INVITE_DAYS if email else LINK_INVITE_DAYS))
    db.add(invite)
    await db.flush()
    return {"invite": invite_view(invite), "token": token}


async def revoke_invite(db, space_id, user_id, invite_id):
    space, _ = await access(db, space_id, user_id, "owner")
    invite = await db.get(SpaceInvite, parse_uuid(invite_id))
    if not invite or invite.space_id != space.id or invite.accepted_at:
        raise HTTPException(404, "Invitation not found")
    invite.revoked_at = invite.revoked_at or now()


async def _usable_invite(db, token: str) -> SpaceInvite:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", token or ""):
        raise HTTPException(404, "This invitation link is invalid.")
    invite = await db.scalar(select(SpaceInvite).where(SpaceInvite.token_hash == token_hash(token)))
    if not invite or invite.revoked_at:
        raise HTTPException(404, "This invitation link is invalid or was revoked.")
    if invite.accepted_at:
        raise HTTPException(410, "This invitation has already been used.")
    if aware(invite.expires_at) <= now():
        raise HTTPException(410, "This invitation has expired. Ask the owner for a new link.")
    return invite


async def _user_email(db, user_id) -> str:
    return (await db.scalar(select(User.email).where(User.id == UUID(user_id))) or "").lower()


async def preview_invite(db, token, user_id) -> dict:
    invite = await _usable_invite(db, token)
    space = await db.get(Space, invite.space_id)
    inviter = await db.scalar(select(User.name).where(User.id == invite.created_by))
    role = await db.scalar(select(SpaceMember.role).where(SpaceMember.space_id == space.id, SpaceMember.user_id == UUID(user_id)))
    return {"spaceId": str(space.id), "name": space.name, "description": space.description or "", "icon": space.icon,
            "color": space.color, "inviterName": inviter, "role": invite.role, "memberRole": role,
            "emailMismatch": bool(invite.email and invite.email != await _user_email(db, user_id))}


async def _join(db, invite: SpaceInvite, user_id) -> str:
    space = await db.scalar(select(Space).where(Space.id == invite.space_id).with_for_update())
    existing = await db.get(SpaceMember, (space.id, UUID(user_id)))
    if invite.email:
        if invite.email != await _user_email(db, user_id):
            raise HTTPException(403, "This invitation was sent to a different email address. Sign in with that account.")
        invite.accepted_at = now()
        await db.flush()
    if existing:
        # Never downgrade an existing member through an invitation.
        if ROLE_RANK[invite.role] > ROLE_RANK[existing.role]:
            existing.role = invite.role
    else:
        # An accepted email invitation no longer holds a pending seat.
        if await _seats_used(db, space.id) >= settings.SPACE_MAX_MEMBERS:
            raise HTTPException(413, "This Space has reached its member limit. Ask the owner to make room.")
        db.add(SpaceMember(space_id=space.id, user_id=UUID(user_id), role=invite.role, joined_at=now()))
    await db.flush()
    return str(space.id)


async def accept_link(db, token, user_id) -> str:
    return await _join(db, await _usable_invite(db, token), user_id)


async def my_invitations(db, user_id) -> list[dict]:
    email = await _user_email(db, user_id)
    rows = (await db.execute(select(SpaceInvite, Space.name, Space.icon, Space.color, User.name)
        .join(Space, Space.id == SpaceInvite.space_id).join(User, User.id == SpaceInvite.created_by)
        .where(SpaceInvite.email == email, SpaceInvite.revoked_at.is_(None), SpaceInvite.accepted_at.is_(None),
               SpaceInvite.expires_at > now()).order_by(SpaceInvite.created_at.desc()).limit(50))).all()
    return [{**invite_view(invite), "spaceId": str(invite.space_id), "spaceName": name, "icon": icon, "color": color,
             "inviterName": inviter} for invite, name, icon, color, inviter in rows]


async def respond_invitation(db, invite_id, user_id, accept: bool) -> str | None:
    invite = await db.get(SpaceInvite, parse_uuid(invite_id))
    email = await _user_email(db, user_id)
    if (not invite or invite.email != email or invite.revoked_at or invite.accepted_at
            or aware(invite.expires_at) <= now()):
        raise HTTPException(404, "Invitation not found or no longer valid.")
    if accept:
        return await _join(db, invite, user_id)
    invite.revoked_at = now()
    return None


async def change_role(db, space_id, user_id, member_id, role: str):
    space, _ = await access(db, space_id, user_id, "owner", lock=True)
    target = await db.get(SpaceMember, (space.id, parse_uuid(member_id)))
    if not target:
        raise HTTPException(404, "Member not found")
    if str(target.user_id) == user_id:
        raise HTTPException(400, "Transfer ownership to another member instead of changing your own role.")
    if role == "owner":
        # Ownership transfer: exactly one owner; the previous owner keeps edit access.
        current = await db.get(SpaceMember, (space.id, UUID(user_id)))
        current.role = "editor"
        space.owner_id = target.user_id
    target.role = role
    space.revision += 1
    await db.flush()


async def remove_member(db, space_id, user_id, member_id):
    space, role = await access(db, space_id, user_id)
    target_id = parse_uuid(member_id)
    leaving = str(target_id) == user_id
    if not leaving and role != "owner":
        raise HTTPException(403, "Only the Space owner can remove members.")
    target = await db.get(SpaceMember, (space.id, target_id))
    if not target:
        raise HTTPException(404, "Member not found")
    if target.role == "owner":
        raise HTTPException(400, "The owner cannot leave. Transfer ownership or delete the Space.")
    await db.delete(target)
    await db.flush()


# ── Shared threads ───────────────────────────────────────────────────────────

THREAD_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def validate_thread(thread_id: str, data: dict) -> tuple[str, int]:
    if not THREAD_ID.match(thread_id) or not isinstance(data, dict) or data.get("id") != thread_id:
        raise HTTPException(422, "Thread identity must match its data.")
    try:
        size = len(json.dumps(data, ensure_ascii=False, allow_nan=False).encode())
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, "Thread must contain finite JSON data.") from None
    if size > MAX_THREAD_BYTES:
        raise HTTPException(413, "This conversation is too long to save to a Space. Start a new thread.")
    title = next((str(data.get(key)).strip() for key in ("title", "query")
                  if isinstance(data.get(key), str) and data.get(key).strip()), "Untitled thread")
    return title[:300], size


async def save_thread(db, space_id, user_id, thread_id, data) -> dict:
    space, _ = await access(db, space_id, user_id, "editor")
    title, size = validate_thread(thread_id, data)
    row = await db.get(SpaceThread, (space.id, thread_id))
    if row and str(row.author_id) != user_id:
        raise HTTPException(403, "Only the author can update this thread. Ask a follow-up to start your own copy.")
    if row:
        row.title, row.data, row.size_bytes, row.updated_at = title, data, size, now()
    else:
        row = SpaceThread(space_id=space.id, thread_id=thread_id, author_id=UUID(user_id), title=title,
                          data=data, size_bytes=size, created_at=now(), updated_at=now())
        db.add(row)
    await touch(db, space)
    await db.flush()
    return {"threadId": thread_id, "title": title, "updatedAt": ms(row.updated_at)}


PREVIEW_CHARS = 180


def answer_preview(answer: str | None) -> str:
    """The opening of an answer as plain text for thread lists: no artifacts, Markdown, citations or links."""
    text = re.sub(r":::artifact\{[^}\n]*\}[\s\S]*?(?:\n:::|$)", " ", answer or "")
    text = re.sub(r"```[\s\S]*?(?:```|$)", " ", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)          # links and images keep their text
    text = re.sub(r"\s*(?:\[\d+(?:,\s*\d+)*\]|【\d+】)", "", text)      # citation markers
    text = re.sub(r"^\s{0,3}(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+|\|)", "", text, flags=re.M)
    text = re.sub(r"[*_`~|]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= PREVIEW_CHARS:
        return text
    cut = text[:PREVIEW_CHARS].rsplit(" ", 1)[0].rstrip(",;:—-")
    return cut + "…"


async def list_threads(db, space_id, user_id, before: int | None = None) -> dict:
    space, role = await access(db, space_id, user_id)
    # Only the first question and the opening of its answer are read, never whole conversations.
    first = SpaceThread.data["history"][0]
    first_question = func.coalesce(first["query"].as_string(), SpaceThread.data["query"].as_string())
    first_answer = func.coalesce(first["answer"].as_string(), SpaceThread.data["answer"].as_string())
    statement = (select(SpaceThread.thread_id, SpaceThread.title, SpaceThread.author_id, SpaceThread.created_at,
                        SpaceThread.updated_at, User.name, func.substr(first_question, 1, 300).label("question"),
                        func.substr(first_answer, 1, 1200).label("answer"))
                 .join(User, User.id == SpaceThread.author_id)
                 .where(SpaceThread.space_id == space.id))
    if before:
        statement = statement.where(SpaceThread.updated_at < datetime.fromtimestamp(before / 1000, timezone.utc))
    rows = (await db.execute(statement.order_by(SpaceThread.updated_at.desc()).limit(THREAD_PAGE + 1))).all()
    items = [{"threadId": row.thread_id, "title": row.title, "question": re.sub(r"\s+", " ", row.question or "").strip() or None,
              "preview": answer_preview(row.answer), "authorName": row.name,
              "isAuthor": str(row.author_id) == user_id, "createdAt": ms(row.created_at),
              "updatedAt": ms(row.updated_at)} for row in rows[:THREAD_PAGE]]
    return {"items": items, "next": items[-1]["updatedAt"] if len(rows) > THREAD_PAGE else None}


async def get_thread(db, space_id, user_id, thread_id) -> dict:
    space, role = await access(db, space_id, user_id)
    row = await db.get(SpaceThread, (space.id, thread_id))
    if not row:
        raise HTTPException(404, "Thread not found in this Space")
    author = await db.scalar(select(User.name).where(User.id == row.author_id))
    return {"threadId": thread_id, "data": row.data, "authorName": author, "isAuthor": str(row.author_id) == user_id,
            "canEdit": ROLE_RANK[role] >= ROLE_RANK["editor"], "updatedAt": ms(row.updated_at)}


async def remove_thread(db, space_id, user_id, thread_id):
    space, role = await access(db, space_id, user_id, "editor")
    row = await db.get(SpaceThread, (space.id, thread_id))
    if not row:
        raise HTTPException(404, "Thread not found in this Space")
    if str(row.author_id) != user_id and role != "owner":
        raise HTTPException(403, "Only the author or the Space owner can remove this thread.")
    await db.delete(row)
    await db.flush()


# ── Files ────────────────────────────────────────────────────────────────────

def file_view(item: SpaceFile, uploader: str | None = None) -> dict:
    return {"id": str(item.id), "name": item.filename, "size": item.size_bytes, "contentType": item.content_type,
            "characters": item.char_count, "uploadedBy": uploader, "createdAt": ms(item.created_at)}


async def list_files(db, space_id, user_id) -> list[dict]:
    space, _ = await access(db, space_id, user_id)
    rows = (await db.execute(select(SpaceFile, User.name).outerjoin(User, User.id == SpaceFile.uploaded_by)
        .where(SpaceFile.space_id == space.id).order_by(SpaceFile.created_at.desc()))).all()
    return [file_view(item, name) for item, name in rows]


async def check_file_quota(db, space: Space, size: int, digest: str):
    count, total = (await db.execute(select(func.count(), func.coalesce(func.sum(SpaceFile.size_bytes), 0))
        .where(SpaceFile.space_id == space.id))).one()
    if count >= settings.SPACE_MAX_FILES:
        raise HTTPException(413, f"A Space can contain up to {settings.SPACE_MAX_FILES} files. Remove one to add another.")
    if total + size > settings.SPACE_MAX_TOTAL_BYTES:
        raise HTTPException(413, f"This Space has reached its {settings.SPACE_MAX_TOTAL_BYTES // (1024 * 1024)} MB file storage limit.")
    duplicate = await db.scalar(select(SpaceFile.filename).where(SpaceFile.space_id == space.id, SpaceFile.sha256 == digest))
    if duplicate:
        raise HTTPException(409, f"This file is already in the Space as “{duplicate}”.")


async def add_file(db, space: Space, user_id, file_id: UUID, name: str, kind: str, size: int, digest: str, chunks: list[str]) -> dict:
    item = SpaceFile(id=file_id, space_id=space.id, uploaded_by=UUID(user_id), filename=name, content_type=kind,
                     size_bytes=size, sha256=digest, char_count=sum(map(len, chunks)), created_at=now())
    db.add(item)
    await db.flush()
    for start in range(0, len(chunks), 500):
        db.add_all([SpaceFileChunk(file_id=file_id, space_id=space.id, ordinal=start + offset, content=chunk)
                    for offset, chunk in enumerate(chunks[start:start + 500])])
        await db.flush()
    await touch(db, space)
    uploader = await db.scalar(select(User.name).where(User.id == UUID(user_id)))
    return file_view(item, uploader)


async def get_file(db, space_id, user_id, file_id) -> SpaceFile:
    space, _ = await access(db, space_id, user_id)
    item = await db.get(SpaceFile, parse_uuid(file_id))
    if not item or item.space_id != space.id:
        raise HTTPException(404, "File not found")
    return item


async def delete_file(db, space_id, user_id, file_id) -> SpaceFile:
    space, _ = await access(db, space_id, user_id, "editor")
    item = await db.get(SpaceFile, parse_uuid(file_id))
    if not item or item.space_id != space.id:
        raise HTTPException(404, "File not found")
    await db.execute(delete(SpaceFileChunk).where(SpaceFileChunk.file_id == item.id))
    await db.delete(item)
    await touch(db, space)
    await db.flush()
    return item


# ── Retrieval ────────────────────────────────────────────────────────────────

STOPWORDS = set("""a an and are as at be by can could did do does for from had has have how i if in into is it its
me my of on or our please should so tell than that the their them then there these they this to was we were what
when where which who why will with would you your about give list show find explain describe summary""".split())
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
FILE_REFERENCE = re.compile(r"\b(file|files|document|documents|doc|pdf|upload|uploaded|attachment|attached|"
                            r"spreadsheet|slides?|deck|notes|summari[sz]e|summary|overview)\b", re.I)
MAX_FILE_SOURCES = 4
CHUNKS_PER_FILE = 3


def query_terms(query: str) -> list[str]:
    terms = []
    for word in re.findall(r"\w+", query.lower()):
        if CJK.search(word):
            continue
        if word in STOPWORDS or (len(word) < 2 and not word.isdigit()) or word in terms:
            continue
        terms.append(word)
    return terms[:24]


def cjk_patterns(query: str) -> list[str]:
    runs = re.findall(r"[぀-ヿ㐀-䶿一-鿿가-힯]+", query)
    grams = {run[i:i + 2] for run in runs for i in range(max(1, len(run) - 1))}
    return [f"%{gram}%" for gram in sorted(grams)][:24]


def _score(content: str, terms: list[str]) -> float:
    lowered = content.lower()
    return sum(1 + min(lowered.count(term), 5) * 0.2 for term in terms if term in lowered)


async def _ranked_chunks(db, space_id: UUID, query: str, limit: int) -> list[tuple]:
    terms = query_terms(query)
    patterns = cjk_patterns(query)
    if db.get_bind().dialect.name == "postgresql":
        rows = []
        if terms:
            tsquery = " | ".join(f"{term}:*" if len(term) >= 4 else term for term in terms)
            rows = (await db.execute(text(
                "SELECT c.file_id, c.ordinal, c.content, ts_rank_cd(c.search_vector, q) AS rank "
                "FROM space_file_chunks c, to_tsquery('simple', :q) q "
                "WHERE c.space_id = :space AND c.search_vector @@ q ORDER BY rank DESC LIMIT :limit"),
                {"q": tsquery, "space": space_id, "limit": limit})).all()
        if not rows and patterns:
            # CJK text has no word boundaries for the 'simple' parser; match bigrams within this Space.
            candidates = (await db.execute(select(SpaceFileChunk.file_id, SpaceFileChunk.ordinal, SpaceFileChunk.content)
                .where(SpaceFileChunk.space_id == space_id, or_(*[SpaceFileChunk.content.like(p) for p in patterns])).limit(200))).all()
            grams = [p.strip("%") for p in patterns]
            rows = sorted(((r.file_id, r.ordinal, r.content, sum(g in r.content for g in grams)) for r in candidates),
                          key=lambda r: -r[3])[:limit]
        return [tuple(row) for row in rows]
    # Portable path for local tests and development databases without full-text search.
    candidates = (await db.execute(select(SpaceFileChunk.file_id, SpaceFileChunk.ordinal, SpaceFileChunk.content)
        .where(SpaceFileChunk.space_id == space_id).limit(5000))).all()
    grams = [p.strip("%") for p in patterns]
    scored = [(r.file_id, r.ordinal, r.content, _score(r.content, terms) + sum(g in r.content for g in grams)) for r in candidates]
    return sorted((r for r in scored if r[3] > 0), key=lambda r: -r[3])[:limit]


async def retrieve(db, space_id: UUID, query: str, broad: bool = False) -> list[dict]:
    """Best-matching file passages grouped into one citable source per file."""
    rows = await _ranked_chunks(db, space_id, query, MAX_FILE_SOURCES * CHUNKS_PER_FILE * 2)
    if not rows and (broad or FILE_REFERENCE.search(query)):
        # Questions such as "summarize the document" share no words with its content.
        rows = [(r.file_id, r.ordinal, r.content, 0) for r in (await db.execute(
            select(SpaceFileChunk.file_id, SpaceFileChunk.ordinal, SpaceFileChunk.content)
            .join(SpaceFile, SpaceFile.id == SpaceFileChunk.file_id)
            .where(SpaceFileChunk.space_id == space_id, SpaceFileChunk.ordinal < 2)
            .order_by(SpaceFile.created_at.desc(), SpaceFileChunk.ordinal).limit(MAX_FILE_SOURCES * 2))).all()]
    grouped: dict[UUID, list] = {}
    for file_id, ordinal, content, _ in rows:
        if file_id in grouped or len(grouped) < MAX_FILE_SOURCES:
            passages = grouped.setdefault(file_id, [])
            if len(passages) < CHUNKS_PER_FILE:
                passages.append((ordinal, content))
    if not grouped:
        return []
    names = dict((await db.execute(select(SpaceFile.id, SpaceFile.filename).where(SpaceFile.id.in_(list(grouped))))).all())
    return [{
        "title": names.get(file_id, "Space file"),
        "url": f"/api/v1/spaces/{space_id}/files/{file_id}/download",
        "domain": "Space file",
        "snippet": "\n…\n".join(content for _, content in sorted(passages))[:3600],
        "source_type": "space_file",
    } for file_id, passages in grouped.items() if file_id in names]


PROMPT_FILE_NAMES = 20
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACE_TAG = re.compile(r"<\s*/?\s*space\s*>", re.I)


def prompt_safe(text: str, limit: int, single_line: bool = False) -> str:
    """Member-written text for the prompt: no control characters, no tags that would end the Space
    section early, bounded length."""
    text = _SPACE_TAG.sub("", _CONTROL.sub(" ", text or ""))
    if single_line:
        text = re.sub(r"\s+", " ", text)
    return text.strip()[:limit]


@dataclass
class SpaceContext:
    """What a question asked inside a Space carries into answer generation."""
    space_id: UUID
    name: str
    instructions: str = ""
    web_search: bool = True
    domains: list[str] = field(default_factory=list)
    has_files: bool = False
    description: str = ""
    file_names: list[str] = field(default_factory=list)
    file_count: int = 0

    def prompt_text(self) -> str:
        """The Space as the model sees it: what it is for, what it holds, then its instructions.
        Without this, "what's this about?" asked in a Space has nothing to refer to."""
        lines = [f"Name: {prompt_safe(self.name, 100, single_line=True)}"]
        description = prompt_safe(self.description, 1000, single_line=True)
        if description:
            lines.append(f"Purpose: {description}")
        names = [name for name in (prompt_safe(item, 100, single_line=True) for item in self.file_names) if name]
        # Stated even when empty, so the model never assumes the Space holds material it does not.
        if names:
            more = max(0, self.file_count - len(names))
            lines.append(f"Files ({self.file_count}): " + "; ".join(names) + (f"; and {more} more" if more else ""))
        else:
            lines.append(f"Files: {self.file_count}" if self.file_count else "Files: none yet")
        lines.append("Priority sites: " + (", ".join(self.domains) if self.domains else "none"))
        lines.append("Web search: on" if self.web_search else "Web search: off (answers use only this Space's files)")
        instructions = prompt_safe(self.instructions, 8000)
        # Instructions go last so the Space's identity always fits.
        return "\n".join(lines) + ("\n\nInstructions:\n" + instructions if instructions else "")

    async def retrieve(self, query: str, broad: bool = False) -> list[dict]:
        if not self.has_files:
            return []
        from src.db.session import async_session_factory
        async with async_session_factory() as db:
            # Unmatched questions get no file passages, so a files-only Space never answers
            # unrelated questions from model knowledge. "Summarize the document" still works,
            # and broad questions about the Space get the opening of its newest files.
            return await retrieve(db, self.space_id, query, broad=broad)


def link_domains(links: list[str]) -> list[str]:
    from urllib.parse import urlsplit
    domains = []
    for link in links or []:
        host = (urlsplit(link).hostname or "").lower().removeprefix("www.")
        if host and host not in domains:
            domains.append(host)
    return domains[:10]


async def search_context(db, space_id, user_id) -> SpaceContext:
    space, _ = await access(db, space_id, user_id, "editor")
    file_count = await db.scalar(select(func.count()).select_from(SpaceFile).where(SpaceFile.space_id == space.id)) or 0
    names = (await db.scalars(select(SpaceFile.filename).where(SpaceFile.space_id == space.id)
                              .order_by(SpaceFile.created_at.desc()).limit(PROMPT_FILE_NAMES))).all() if file_count else []
    return SpaceContext(space_id=space.id, name=space.name, instructions=(space.custom_instructions or "").strip(),
                        web_search=bool(space.web_search), domains=link_domains(space.links), has_files=file_count > 0,
                        description=(space.description or "").strip(), file_names=list(names), file_count=file_count)
