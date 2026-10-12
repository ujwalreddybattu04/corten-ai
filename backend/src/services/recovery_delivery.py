"""Private CLI for the host's role-based mail worker; never expose it as an API."""
import asyncio
import json
import secrets
import sys
from datetime import timedelta
from uuid import UUID
from sqlalchemy import select, delete
from src.db.session import async_session_factory, engine
from src.models.password_reset import PasswordReset, RecoveryEmail
from src.services.password_recovery import now, aware
from src.services.recovery_email import open_payload

async def claim(db):
    stamp = now()
    # Locks/leases permit multiple delivery workers without duplicate concurrent claims.
    for _ in range(32):
        row = (await db.execute(select(RecoveryEmail).where(
            RecoveryEmail.status.in_(("pending", "sending")), RecoveryEmail.available_at <= stamp)
            .order_by(RecoveryEmail.available_at).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
        if not row: return None
        reset = await db.get(PasswordReset, row.reset_id)
        if not reset or reset.used_at or aware(row.expires_at) <= stamp or row.attempts >= 4:
            row.status = "cancelled"; row.payload = ""; await db.commit(); continue
        try: message = open_payload(row.payload)
        except Exception:
            row.status = "failed"; row.payload = ""; await db.commit(); continue
        row.lease = secrets.token_hex(16); row.attempts += 1
        row.status = "sending"; row.available_at = stamp + timedelta(seconds=90)
        await db.commit()
        return {"id": str(row.id), "lease": row.lease, "message": message}
    return None

async def finish(db, identifier, lease, outcome, receipt=""):
    row = (await db.execute(select(RecoveryEmail).where(RecoveryEmail.id == UUID(identifier)).with_for_update())).scalar_one_or_none()
    if not row or row.status != "sending" or row.lease != lease: return
    if outcome == "sent":
        row.status = "sent"; row.receipt = receipt[:200]; row.payload = ""
    elif outcome == "permanent": row.status = "failed"; row.payload = ""
    else:
        row.status = "pending"; row.available_at = now()+timedelta(seconds=min(600, 30*2**row.attempts))
    row.lease = None
    await db.commit()

async def main(args):
    try:
        async with async_session_factory() as db:
            if args == ["claim"]: print(json.dumps(await claim(db), ensure_ascii=False))
            elif len(args) in (4,5) and args[0] == "finish": await finish(db,*args[1:])
            elif args == ["prune"]:
                await db.execute(delete(PasswordReset).where(PasswordReset.expires_at < now()-timedelta(days=7)))
                await db.commit()
            else: raise ValueError("Unknown mail worker operation")
    finally: await engine.dispose()

if __name__ == "__main__": asyncio.run(main(sys.argv[1:]))
