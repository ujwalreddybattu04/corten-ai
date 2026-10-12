"""Auth and authorization regressions. All users and storage are isolated fixtures."""
import asyncio
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
import jwt
from src.main import app
from src.api.deps import get_db
from src.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from src.config.settings import settings
from src.services import auth_sessions
from src.services.auth_service import auth_service
from src.services.thread_service import thread_service
from src.models.user import User


class FakeDB:
    def __init__(self): self.users = {}
    async def execute(self, stmt):
        params = stmt.compile().params
        user = next((u for u in self.users.values() if u.email == params.get("email_1") or u.id == params.get("id_1")), None)
        return SimpleNamespace(scalar_one_or_none=lambda: user)
    def add(self, user):
        user.is_active = True
        user.subscription_tier = "free"
        self.users[user.id] = user
    async def flush(self): pass
    async def commit(self): pass
    async def rollback(self): pass

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", [
    ("POST","/api/v1/search/stream",{"query":"hello"}),
    ("POST","/api/v1/search/title",{"query":"hello"}),
    ("POST","/api/v1/report/stream",{"topic":"Research"}),
    ("GET","/api/v1/report/download/"+"a"*32,None),
    ("GET","/api/v1/discover",None),
    ("GET","/api/v1/discover/sidebar",None),
    ("GET","/api/v1/pharma/updates",None),
    ("POST","/api/v1/interpolation/preview",{}),
    ("GET","/api/v1/spaces",None),
    ("GET","/api/v1/collections",None),
    ("GET","/api/v1/personal/changes",None),
])
async def test_tool_endpoints_require_authentication(client,auth_state,method,path,body):
    response=await client.request(method,path,**({"json":body} if body is not None else {}))
    assert response.status_code==401

@pytest.mark.asyncio
async def test_password_version_invalidates_old_access_and_refresh(client,auth_state):
    tokens=(await signup(client)).json();user=next(iter(auth_state[0].users.values()))
    headers={"Authorization":"Bearer "+tokens["access_token"]}
    assert (await client.get('/api/v1/auth/me',headers=headers)).status_code==200
    user.auth_version=1
    assert (await client.get('/api/v1/auth/me',headers=headers)).status_code==401
    assert (await client.post('/api/v1/auth/refresh',json={'refresh_token':tokens['refresh_token']})).status_code==401


class SecurityRedis:
    """Simulates Redis's serialized execution; live CAS is tested separately on deployment."""
    def __init__(self): self.sessions = {}; self.counts = {}
    async def eval(self, script, count, key, *args):
        if "INCR" in script:
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]
        if "EXPIRE" in script:
            self.sessions[key] = {"user": args[0], "jti": args[1]}; return 1
        session = self.sessions.get(key)
        if "HSET" in script:
            if not session or session["user"] != args[0]: return 0
            if session["jti"] != args[1]: del self.sessions[key]; return 0
            session["jti"] = args[2]; return 1
        if "DEL" in script:
            if session and session["user"] == args[0]: del self.sessions[key]; return 1
            return 0
        return int(bool(session and session["user"] == args[0]))


@pytest.fixture
def auth_state(monkeypatch):
    db, redis = FakeDB(), SecurityRedis()
    monkeypatch.setattr(auth_sessions, "get_redis", AsyncMock(return_value=redis))
    async def database(): yield db
    app.dependency_overrides[get_db] = database
    yield db, redis
    app.dependency_overrides.pop(get_db, None)


async def signup(client, email="audit@example.com", password="audit-pass-123"):
    return await client.post("/api/v1/auth/register", json={"name": "Audit User", "email": email, "password": password})


@pytest.mark.asyncio
async def test_register_login_me_refresh_logout_complete(client, auth_state):
    response = await signup(client)
    assert response.status_code == 201
    tokens = response.json()
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["email"] == "audit@example.com"
    assert (await client.get("/api/v1/users/me", headers=headers)).json()["id"] == tokens["user"]["id"]
    fresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert fresh.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + fresh.json()["access_token"]})).status_code == 200
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 401
    # Reuse is treated as potential theft and invalidates the active token family.
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + fresh.json()["access_token"]})).status_code == 401
    assert (await client.post("/api/v1/auth/logout", json={"refresh_token": fresh.json()["refresh_token"]})).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": fresh.json()["refresh_token"]})).status_code == 401
    login = await client.post("/api/v1/auth/login", json={"email": "AUDIT@example.com", "password": "audit-pass-123"})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_token_types_cannot_be_interchanged(client, auth_state):
    tokens = (await signup(client)).json()
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + tokens["refresh_token"]})).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})).status_code == 401


@pytest.mark.asyncio
async def test_concurrent_refresh_is_single_use(client, auth_state):
    tokens = (await signup(client)).json()
    responses = await asyncio.gather(*(client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}) for _ in range(8)))
    assert sorted(r.status_code for r in responses) == [200] + [401] * 7


@pytest.mark.asyncio
async def test_disabled_or_deleted_users_lose_existing_access(client, auth_state):
    tokens = (await signup(client)).json()
    db, _ = auth_state
    user = next(iter(db.users.values()))
    user.is_active = False
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + tokens["access_token"]})).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 401
    assert (await client.post("/api/v1/auth/login", json={"email": user.email, "password": "audit-pass-123"})).json()["detail"] == "Invalid email or password"
    db.users.clear()
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + tokens["access_token"]})).status_code == 401


@pytest.mark.asyncio
async def test_invalid_and_expired_tokens_fail_without_server_errors(client, auth_state):
    user, _, _, = await auth_service.register(auth_state[0], "Audit User", "audit@example.com", "audit-pass-123")
    claims = {"sub": str(user.id), "sid": uuid.uuid4().hex}
    for token in ["malformed", create_access_token(claims, timedelta(seconds=-1)), create_access_token({"sub": "not-uuid", "sid": uuid.uuid4().hex}), jwt.encode({"sub": str(user.id)}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)]:
        assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})).status_code == 401


@pytest.mark.asyncio
async def test_duplicate_case_and_input_validation(client, auth_state):
    assert (await signup(client)).status_code == 201
    assert (await signup(client, "AUDIT@example.com")).status_code == 409
    for changes in [{"name": " "}, {"name": "x" * 101}, {"email": "invalid"}, {"password": "short"}, {"password": "x" * 1025}]:
        body = {"name": "Audit User", "email": "different@example.com", "password": "audit-pass-123", **changes}
        assert (await client.post("/api/v1/auth/register", json=body)).status_code == 422


def test_long_passwords_do_not_collide_and_legacy_passwords_work():
    password = "a" * 72 + "different-tail"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("a" * 72 + "another-tail", hashed)
    from src.core.security import pwd_context
    legacy = pwd_context.hash("legacy-pass", scheme="bcrypt")
    assert verify_password("legacy-pass", legacy)
    assert not verify_password("legacy-pass" + "x" * 100, legacy)


@pytest.mark.asyncio
async def test_security_store_outage_fails_closed(client, auth_state, monkeypatch):
    tokens = (await signup(client)).json()
    monkeypatch.setattr(auth_sessions, "get_redis", AsyncMock(side_effect=ConnectionError("private-endpoint")))
    for response in [await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + tokens["access_token"]}), await client.post("/api/v1/auth/login", json={"email": "audit@example.com", "password": "audit-pass-123"}), await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})]:
        assert response.status_code == 503
        assert "private-endpoint" not in response.text


@pytest.mark.asyncio
async def test_auth_rate_limits_return_retry_after(client, auth_state):
    for _ in range(20):
        assert (await client.post("/api/v1/auth/login", json={"email": "none@example.com", "password": "invalid-pass"})).status_code == 401
    response = await client.post("/api/v1/auth/login", json={"email": "none@example.com", "password": "invalid-pass"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "900"


@pytest.mark.asyncio
async def test_private_threads_deny_anonymous_and_other_accounts(client, auth_state, monkeypatch):
    tokens = (await signup(client)).json()
    owner = tokens["user"]["id"]
    outsider = (await signup(client, "outsider@example.com")).json()
    thread = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.UUID(owner), is_public=False, title="Private", focus_mode="all", model_used="test", share_token=None, message_count=0, last_message_at=None, created_at=None, updated_at=None)
    async def lookup(db, thread_id, user_id=None): return thread if user_id is None or user_id == owner else None
    monkeypatch.setattr(thread_service, "get_thread", lookup)
    messages = AsyncMock(return_value=[])
    monkeypatch.setattr(thread_service, "get_messages", messages)
    path = f"/api/v1/threads/{thread.id}"
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers={"Authorization": "Bearer " + outsider["access_token"]})).status_code == 404
    messages.assert_not_awaited()
    assert (await client.get(path, headers={"Authorization": "Bearer " + tokens["access_token"]})).status_code == 200
    thread.is_public = True
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers={"Authorization": "Bearer " + outsider["access_token"]})).status_code == 200
    assert (await client.get("/api/v1/threads/not-a-uuid")).status_code == 401
    assert (await client.get("/api/v1/threads/not-a-uuid", headers={"Authorization": "Bearer " + tokens["access_token"]})).status_code == 422


@pytest.mark.asyncio
async def test_refresh_claims_are_bound_to_the_session_owner(client, auth_state):
    tokens = (await signup(client)).json()
    payload = decode_token(tokens["refresh_token"], "refresh")
    other = (await signup(client, "other@example.com")).json()
    payload["sub"] = other["user"]["id"]
    forged = create_refresh_token(payload)
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": forged})).status_code == 401


@pytest.mark.asyncio
async def test_account_apis_require_auth_and_profile_can_be_updated(client, auth_state):
    for path in ["/api/v1/users/me", "/api/v1/threads", "/api/v1/spaces", "/api/v1/collections", "/api/v1/personal/changes"]:
        assert (await client.get(path)).status_code == 401
    tokens = (await signup(client)).json()
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    response = await client.put("/api/v1/users/me", json={"name": "Updated Name"}, headers=headers)
    assert response.status_code == 200 and response.json()["name"] == "Updated Name"
