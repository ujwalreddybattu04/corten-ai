"""Chat attachments: upload images and documents, read them back, delete them."""
import asyncio
import hashlib
import logging
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from src.api.deps import get_current_user_id, get_db
from src.config.settings import settings
from src.services import attachments, space_files

logger = logging.getLogger(__name__)
router = APIRouter()
EXTRACTION_TIMEOUT = 90


@router.post("", status_code=201)
async def upload(file: UploadFile = File(...), user: str = Depends(get_current_user_id), db=Depends(get_db)):
    try:
        name = space_files.clean_filename(file.filename or "")
    except space_files.FileRejected as error:
        raise HTTPException(415, str(error)) from None
    data = await file.read(settings.ATTACHMENT_MAX_BYTES + 1)
    if len(data) > settings.ATTACHMENT_MAX_BYTES:
        raise HTTPException(413, f"Files must be no larger than {settings.ATTACHMENT_MAX_BYTES // (1024 * 1024)} MB.")
    if not data:
        raise HTTPException(422, "This file is empty.")
    try:
        kind, content_type, stored, text = await asyncio.wait_for(
            asyncio.to_thread(attachments.prepare_upload, name, data), EXTRACTION_TIMEOUT)
    except space_files.FileRejected as error:
        raise HTTPException(415 if "not supported" in str(error) else 422, str(error)) from None
    except asyncio.TimeoutError:
        raise HTTPException(422, "This file took too long to read. Try a smaller or simpler file.") from None
    except Exception:
        logger.exception("Attachment processing failed")
        raise HTTPException(422, "This file could not be read. Check that it is not damaged.") from None
    result = await attachments.save_upload(db, user, name, kind, content_type, stored, text,
                                           hashlib.sha256(data).hexdigest())
    await db.commit()
    return result


@router.get("")
async def list_attachments(user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return {"items": await attachments.list_for_user(db, user)}


@router.get("/{attachment_id}/content")
async def content(attachment_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    item = await attachments.owned(db, user, attachment_id)
    path = attachments.file_path(item.user_id, item.id)
    if not path.is_file():
        raise HTTPException(404, "The stored copy of this file is unavailable.")
    headers = {"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "sandbox"}
    if item.kind == "image":
        # Re-encoded JPEG produced by the server; safe to display inline.
        return FileResponse(path, media_type="image/jpeg", headers=headers)
    return FileResponse(path, media_type=item.content_type if item.kind == "generated" else "application/octet-stream",
                        filename=item.filename, headers={**headers, "Cache-Control": "private, no-store"})


@router.delete("/{attachment_id}", status_code=204)
async def delete_attachment(attachment_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    await attachments.remove_attachment(db, user, attachment_id)
    await db.commit()
