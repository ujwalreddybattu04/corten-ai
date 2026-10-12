"""Shared Spaces: roles, invitations, threads, files, retrieval and answer integration."""
import io
import json
import zipfile
from unittest.mock import AsyncMock, patch
from uuid import uuid4, UUID
import pytest
import pytest_asyncio
from fastapi import Request
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.main import app
from src.api.deps import get_db, get_current_user_id
from src.config.settings import settings
from src.models.space import Space, SpaceMember, SpaceInvite, SpaceFile, SpaceFileChunk, SpaceThread
from src.services import space_files, space_service
from src.services.search_orchestrator import SearchOrchestrator, NO_SPACE_EVIDENCE
from src.services.llm_service import groq_llm_service
from src.tools import ToolResult

from src.models.personal_record import PersonalRecord
TABLES = [Space.__table__, SpaceMember.__table__, SpaceInvite.__table__, SpaceFile.__table__,
          SpaceFileChunk.__table__, SpaceThread.__table__, PersonalRecord.__table__]
OWNER, EDITOR, VIEWER, STRANGER = (str(uuid4()) for _ in range(4))
EMAILS = {OWNER: "owner@example.com", EDITOR: "editor@example.com", VIEWER: "viewer@example.com",
          STRANGER: "stranger@example.com"}


@pytest_asyncio.fixture
async def factory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SPACE_FILES_DIR", str(tmp_path / "files"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'spaces.db'}")
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY, name TEXT, email TEXT, avatar_url TEXT)"))
        for user, email in EMAILS.items():
            await connection.execute(text("INSERT INTO users VALUES (:id, :name, :email, NULL)"),
                                     {"id": UUID(user).hex, "name": email.split("@")[0].title(), "email": email})
        await connection.run_sync(lambda sync: [table.create(sync) for table in TABLES])
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def database():
        async with sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def current_user(request: Request) -> str:
        return request.headers["x-test-user"]

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user_id] = current_user
    yield sessions
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def api(factory):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        def as_user(user):
            class Caller:
                async def request(self, method, url, **kwargs):
                    return await client.request(method, url, headers={"x-test-user": user}, **kwargs)
                get = lambda self, url, **kw: self.request("GET", url, **kw)
                post = lambda self, url, **kw: self.request("POST", url, **kw)
                patch = lambda self, url, **kw: self.request("PATCH", url, **kw)
                put = lambda self, url, **kw: self.request("PUT", url, **kw)
                delete = lambda self, url, **kw: self.request("DELETE", url, **kw)
            return Caller()
        yield as_user


async def shared_space(api):
    """Owner's Space with an editor (email invitation) and a viewer (link invitation)."""
    owner = api(OWNER)
    space = (await owner.post("/api/v1/spaces", json={"name": "  Market research ", "instructions": "Answer in French.",
                                                       "links": ["example.org/reports"], "icon": "briefcase"})).json()
    link = (await owner.post(f"/api/v1/spaces/{space['id']}/invites", json={"role": "viewer"})).json()
    assert (await api(VIEWER).post(f"/api/v1/spaces/join/{link['token']}")).json()["spaceId"] == space["id"]
    invite = (await owner.post(f"/api/v1/spaces/{space['id']}/invites", json={"role": "editor", "email": "Editor@Example.com"})).json()
    assert invite["invite"]["email"] == "editor@example.com"
    pending = (await api(EDITOR).get("/api/v1/spaces/invitations")).json()["items"]
    assert [item["spaceName"] for item in pending] == ["Market research"]
    assert (await api(EDITOR).post(f"/api/v1/spaces/invitations/{pending[0]['id']}/accept")).status_code == 200
    return space


@pytest.mark.asyncio
async def test_roles_control_every_space_operation(api):
    space = await shared_space(api)
    sid = space["id"]
    assert space["name"] == "Market research" and space["links"] == ["https://example.org/reports"] and space["role"] == "owner"
    # Non-members cannot learn that a Space exists.
    for path in ("", "/members", "/threads", "/files"):
        assert (await api(STRANGER).get(f"/api/v1/spaces/{sid}{path}")).status_code == 404
    assert (await api(STRANGER).get("/api/v1/spaces")).json()["items"] == []

    roles = {item["id"]: item["role"] for item in (await api(EDITOR).get("/api/v1/spaces")).json()["items"]}
    assert roles == {sid: "editor"}
    listed = (await api(OWNER).get("/api/v1/spaces")).json()["items"][0]
    assert listed["memberCount"] == 3

    viewer = api(VIEWER)
    assert (await viewer.patch(f"/api/v1/spaces/{sid}", json={"name": "x", "expected_revision": 1})).status_code == 403
    assert (await viewer.post(f"/api/v1/spaces/{sid}/files", files={"file": ("a.txt", b"hello")})).status_code == 403
    assert (await viewer.put(f"/api/v1/spaces/{sid}/threads/t1", json={"data": {"id": "t1", "title": "x"}})).status_code == 403
    assert (await viewer.post(f"/api/v1/spaces/{sid}/invites", json={"role": "editor"})).status_code == 403
    assert (await api(EDITOR).post(f"/api/v1/spaces/{sid}/invites", json={"role": "editor"})).status_code == 403
    assert (await api(EDITOR).delete(f"/api/v1/spaces/{sid}")).status_code == 403
    async with _session(api) as db:
        with pytest.raises(Exception) as denied:
            await space_service.search_context(db, sid, VIEWER)
        assert denied.value.status_code == 403
        context = await space_service.search_context(db, sid, EDITOR)
        assert context.instructions == "Answer in French." and context.domains == ["example.org"] and context.web_search

    # Member emails are visible to the owner only.
    as_viewer = (await viewer.get(f"/api/v1/spaces/{sid}/members")).json()
    assert all("email" not in m for m in as_viewer["members"] if not m["isYou"]) and as_viewer["invites"] == []
    as_owner = (await api(OWNER).get(f"/api/v1/spaces/{sid}/members")).json()
    assert {m["email"] for m in as_owner["members"]} == {EMAILS[OWNER], EMAILS[EDITOR], EMAILS[VIEWER]}


class _session:
    """Direct service access to the API test database."""
    def __init__(self, api): self.generator = None

    async def __aenter__(self):
        self.generator = app.dependency_overrides[get_db]()
        return await self.generator.__anext__()

    async def __aexit__(self, *error):
        await self.generator.aclose()


@pytest.mark.asyncio
async def test_concurrent_edits_conflict_instead_of_overwriting(api):
    space = await shared_space(api)
    first = await api(EDITOR).patch(f"/api/v1/spaces/{space['id']}", json={"instructions": "Be brief.", "expected_revision": 1})
    assert first.status_code == 200 and first.json()["revision"] == 2 and first.json()["instructions"] == "Be brief."
    stale = await api(OWNER).patch(f"/api/v1/spaces/{space['id']}", json={"name": "Other", "expected_revision": 1})
    assert stale.status_code == 409
    assert (await api(OWNER).patch(f"/api/v1/spaces/{space['id']}", json={"expected_revision": 2})).status_code == 422
    assert (await api(OWNER).patch(f"/api/v1/spaces/{space['id']}", json={"links": ["javascript:alert(1)"], "expected_revision": 2})).status_code == 422
    assert (await api(OWNER).patch(f"/api/v1/spaces/{space['id']}", json={"links": ["https://u:p@example.com"], "expected_revision": 2})).status_code == 422


@pytest.mark.asyncio
async def test_invitations_are_bound_revocable_and_never_downgrade(api):
    owner = api(OWNER)
    sid = (await owner.post("/api/v1/spaces", json={"name": "Private"})).json()["id"]
    invite = (await owner.post(f"/api/v1/spaces/{sid}/invites", json={"role": "editor", "email": "editor@example.com"})).json()
    # Someone else holding the link cannot use an email-bound invitation.
    preview = (await api(STRANGER).get(f"/api/v1/spaces/join/{invite['token']}")).json()
    assert preview["emailMismatch"] is True and preview["name"] == "Private"
    assert (await api(STRANGER).post(f"/api/v1/spaces/join/{invite['token']}")).status_code == 403
    assert (await api(EDITOR).post(f"/api/v1/spaces/join/{invite['token']}")).status_code == 200
    assert (await api(EDITOR).post(f"/api/v1/spaces/join/{invite['token']}")).status_code == 410
    # A viewer link does not reduce an existing editor's access.
    link = (await owner.post(f"/api/v1/spaces/{sid}/invites", json={"role": "viewer"})).json()
    await api(EDITOR).post(f"/api/v1/spaces/join/{link['token']}")
    assert (await api(EDITOR).get(f"/api/v1/spaces/{sid}")).json()["role"] == "editor"
    assert (await owner.delete(f"/api/v1/spaces/{sid}/invites/{link['invite']['id']}")).status_code == 204
    assert (await api(VIEWER).post(f"/api/v1/spaces/join/{link['token']}")).status_code == 404
    assert (await api(VIEWER).get("/api/v1/spaces/join/not-a-token")).status_code == 404
    # Inviting an existing member is rejected; re-inviting an email replaces the pending invitation.
    assert (await owner.post(f"/api/v1/spaces/{sid}/invites", json={"email": "editor@example.com"})).status_code == 409
    await owner.post(f"/api/v1/spaces/{sid}/invites", json={"email": "viewer@example.com"})
    await owner.post(f"/api/v1/spaces/{sid}/invites", json={"email": "viewer@example.com", "role": "editor"})
    pending = (await api(VIEWER).get("/api/v1/spaces/invitations")).json()["items"]
    assert [item["role"] for item in pending] == ["editor"]
    assert (await api(VIEWER).post(f"/api/v1/spaces/invitations/{pending[0]['id']}/decline")).status_code == 204
    assert (await api(VIEWER).get("/api/v1/spaces/invitations")).json()["items"] == []


@pytest.mark.asyncio
async def test_member_limit_counts_pending_email_invitations(api, monkeypatch):
    monkeypatch.setattr(settings, "SPACE_MAX_MEMBERS", 2)
    owner = api(OWNER)
    sid = (await owner.post("/api/v1/spaces", json={"name": "Small"})).json()["id"]
    assert (await owner.post(f"/api/v1/spaces/{sid}/invites", json={"email": "editor@example.com"})).status_code == 201
    assert (await owner.post(f"/api/v1/spaces/{sid}/invites", json={"email": "viewer@example.com"})).status_code == 413
    link = (await owner.post(f"/api/v1/spaces/{sid}/invites", json={})).json()
    assert (await api(STRANGER).post(f"/api/v1/spaces/join/{link['token']}")).status_code == 413
    pending = (await api(EDITOR).get("/api/v1/spaces/invitations")).json()["items"]
    assert (await api(EDITOR).post(f"/api/v1/spaces/invitations/{pending[0]['id']}/accept")).status_code == 200


@pytest.mark.asyncio
async def test_ownership_transfer_leaving_and_removal(api):
    space = await shared_space(api)
    sid = space["id"]
    members = (await api(OWNER).get(f"/api/v1/spaces/{sid}/members")).json()["members"]
    editor_id = next(m["userId"] for m in members if m["role"] == "editor")
    assert (await api(OWNER).delete(f"/api/v1/spaces/{sid}/members/{OWNER}")).status_code == 400
    assert (await api(EDITOR).delete(f"/api/v1/spaces/{sid}/members/{VIEWER}")).status_code == 403
    assert (await api(OWNER).patch(f"/api/v1/spaces/{sid}/members/{editor_id}", json={"role": "owner"})).status_code == 204
    assert (await api(EDITOR).get(f"/api/v1/spaces/{sid}")).json()["role"] == "owner"
    assert (await api(OWNER).get(f"/api/v1/spaces/{sid}")).json()["role"] == "editor"
    assert (await api(OWNER).delete(f"/api/v1/spaces/{sid}/members/{OWNER}")).status_code == 204
    assert (await api(OWNER).get(f"/api/v1/spaces/{sid}")).status_code == 404
    assert (await api(EDITOR).delete(f"/api/v1/spaces/{sid}/members/{VIEWER}")).status_code == 204
    assert (await api(EDITOR).get(f"/api/v1/spaces/{sid}")).json()["memberCount"] == 1


@pytest.mark.asyncio
async def test_threads_are_shared_but_only_their_author_can_change_them(api):
    space = await shared_space(api)
    sid = space["id"]
    thread = {"id": "thread-1", "title": "Pricing in Europe", "query": "q", "answer": "a", "history": []}
    saved = await api(EDITOR).put(f"/api/v1/spaces/{sid}/threads/thread-1", json={"data": thread})
    assert saved.status_code == 200 and saved.json()["title"] == "Pricing in Europe"
    assert (await api(OWNER).put(f"/api/v1/spaces/{sid}/threads/thread-1", json={"data": {**thread, "title": "Edited"}})).status_code == 403
    assert (await api(EDITOR).put(f"/api/v1/spaces/{sid}/threads/thread-2", json={"data": thread})).status_code == 422
    assert (await api(EDITOR).put(f"/api/v1/spaces/{sid}/threads/thread-1", json={"data": {**thread, "answer": "x" * 300000}})).status_code == 413
    listed = (await api(VIEWER).get(f"/api/v1/spaces/{sid}/threads")).json()
    assert [(t["threadId"], t["authorName"], t["isAuthor"]) for t in listed["items"]] == [("thread-1", "Editor", False)]
    opened = (await api(VIEWER).get(f"/api/v1/spaces/{sid}/threads/thread-1")).json()
    assert opened["data"]["answer"] == "a" and opened["canEdit"] is False and opened["isAuthor"] is False
    assert (await api(VIEWER).delete(f"/api/v1/spaces/{sid}/threads/thread-1")).status_code == 403
    assert (await api(OWNER).delete(f"/api/v1/spaces/{sid}/threads/thread-1")).status_code == 204
    assert (await api(VIEWER).get(f"/api/v1/spaces/{sid}/threads")).json()["items"] == []


def docx(*paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                         f"<w:body>{body}</w:body></w:document>")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_files_are_extracted_searchable_downloadable_and_removed(api, monkeypatch):
    space = await shared_space(api)
    sid = space["id"]
    editor = api(EDITOR)
    report = docx("Quarterly revenue in Germany grew 14 percent.", "Pricing pressure remains in France.")
    uploaded = await editor.post(f"/api/v1/spaces/{sid}/files", files={"file": ("Q3 report.docx", report)})
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]
    assert uploaded.json()["uploadedBy"] == "Editor"
    assert (await editor.post(f"/api/v1/spaces/{sid}/files", files={"file": ("copy.docx", report)})).status_code == 409
    assert (await editor.post(f"/api/v1/spaces/{sid}/files", files={"file": ("tool.exe", b"MZ")})).status_code == 415
    assert (await editor.post(f"/api/v1/spaces/{sid}/files", files={"file": ("bad.pdf", b"not a pdf")})).status_code == 422
    assert (await editor.post(f"/api/v1/spaces/{sid}/files", files={"file": ("empty.txt", b"")})).status_code == 422

    download = await api(VIEWER).get(f"/api/v1/spaces/{sid}/files/{file_id}/download")
    assert download.content == report
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.headers["x-content-type-options"] == "nosniff" and "attachment" in download.headers["content-disposition"]

    async with _session(api) as db:
        found = await space_service.retrieve(db, UUID(sid), "How did revenue grow in Germany?")
        assert found[0]["title"] == "Q3 report.docx" and "14 percent" in found[0]["snippet"]
        assert found[0]["url"] == f"/api/v1/spaces/{sid}/files/{file_id}/download"
        assert await space_service.retrieve(db, UUID(sid), "weather in Tokyo") == []
        overview = await space_service.retrieve(db, UUID(sid), "summarize the document")
        assert overview and overview[0]["title"] == "Q3 report.docx"

    monkeypatch.setattr(settings, "SPACE_MAX_FILES", 1)
    assert (await editor.post(f"/api/v1/spaces/{sid}/files", files={"file": ("n.txt", b"notes")})).status_code == 413
    assert (await api(VIEWER).delete(f"/api/v1/spaces/{sid}/files/{file_id}")).status_code == 403
    stored = space_files.file_path(UUID(sid), UUID(file_id))
    assert stored.is_file()
    assert (await editor.delete(f"/api/v1/spaces/{sid}/files/{file_id}")).status_code == 204
    assert not stored.exists()
    async with _session(api) as db:
        assert await space_service.retrieve(db, UUID(sid), "revenue Germany") == []
    await editor.post(f"/api/v1/spaces/{sid}/files", files={"file": ("n.txt", b"notes")})
    assert (await api(OWNER).delete(f"/api/v1/spaces/{sid}")).status_code == 204
    assert not (stored.parent).exists()
    assert (await api(EDITOR).get(f"/api/v1/spaces/{sid}")).status_code == 404


@pytest.mark.asyncio
async def test_legacy_browser_spaces_import_once_with_their_threads(api):
    payload = {"spaces": [{"legacyId": "sp_old1", "name": "Old", "links": [], "threads": [
        {"id": "t-1", "title": "Saved", "answer": "a"}, {"id": "bad id", "title": "skipped"}]}]}
    first = (await api(OWNER).post("/api/v1/spaces/import", json=payload)).json()["imported"]
    again = (await api(OWNER).post("/api/v1/spaces/import", json=payload)).json()["imported"]
    assert first == again and list(first) == ["sp_old1"]
    threads = (await api(OWNER).get(f"/api/v1/spaces/{first['sp_old1']}/threads")).json()["items"]
    assert [t["threadId"] for t in threads] == ["t-1"]
    assert len((await api(OWNER).get("/api/v1/spaces")).json()["items"]) == 1
    # A Space that reached cloud storage was migrated server-side; after deletion a stale
    # device must not recreate it.
    async with _session(api) as db:
        db.add(PersonalRecord(user_id=UUID(OWNER), namespace="spaces", record_id="sp_synced", data={"id": "sp_synced"},
                              deleted=False, revision=1, size_bytes=1))
        await db.commit()
    stale = {"spaces": [{"legacyId": "sp_synced", "name": "Deleted elsewhere"}]}
    result = (await api(OWNER).post("/api/v1/spaces/import", json=stale)).json()
    assert result == {"imported": {}, "skipped": ["sp_synced"]}
    assert len((await api(OWNER).get("/api/v1/spaces")).json()["items"]) == 1


# ── Extraction and retrieval units ───────────────────────────────────────────

def test_office_html_pdf_and_text_extraction():
    assert "grew 14 percent" in space_files.extract_text("a.docx", docx("Revenue grew 14 percent."))
    xlsx = io.BytesIO()
    with zipfile.ZipFile(xlsx, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", '<sst xmlns="x"><si><t>Region</t></si><si><t>Revenue</t></si></sst>')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="x"><sheetData><row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>'
                         '<row><c t="inlineStr"><is><t>EMEA</t></is></c><c><v>42</v></c></row></sheetData></worksheet>')
    assert "Region\tRevenue\nEMEA\t42" in space_files.extract_text("s.xlsx", xlsx.getvalue())
    pptx = io.BytesIO()
    with zipfile.ZipFile(pptx, "w") as archive:
        for number in (2, 10, 1):
            archive.writestr(f"ppt/slides/slide{number}.xml", f'<p:sld xmlns:p="p" xmlns:a="a"><a:p><a:t>Slide text {number}</a:t></a:p></p:sld>')
    slides = space_files.extract_text("d.pptx", pptx.getvalue())
    assert slides.index("Slide text 1") < slides.index("Slide text 2") < slides.index("Slide text 10")
    html = b"<html><script>steal()</script><h1>Title</h1><p>Body &amp; more</p></html>"
    assert space_files.extract_text("p.html", html) == "Title\nBody & more"
    assert space_files.extract_text("u.txt", "Grüße 東京".encode("utf-16")) == "Grüße 東京"

    from reportlab.pdfgen import canvas
    pdf = io.BytesIO()
    document = canvas.Canvas(pdf)
    document.drawString(72, 720, "Clinical trial enrolment completed in March.")
    document.save()
    assert "[Page 1]" in space_files.extract_text("t.pdf", pdf.getvalue())


def test_extraction_rejects_unsafe_or_unreadable_content(monkeypatch):
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "<w:document xmlns:w='w'>" + "a" * 5000 + "</w:document>")
    monkeypatch.setattr(space_files, "MAX_ZIP_UNCOMPRESSED", 1000)
    for name, data in (("b.docx", bomb.getvalue()),
                       ("e.docx", docx("x").replace(b"<w:document", b'<!DOCTYPE x [<!ENTITY a "b">]><w:document')),
                       ("z.docx", b"PK not a zip"), ("bin.txt", b"\x00\x01binary"), ("img.png", b"\x89PNG"),
                       ("blank.txt", b"   \n  ")):
        with pytest.raises(space_files.FileRejected):
            space_files.extract_text(name, data)
    assert space_files.clean_filename("../../etc/pass\x00wd.txt") == "passwd.txt"
    with pytest.raises(space_files.FileRejected):
        space_files.clean_filename("...")


def test_chunks_cover_text_with_overlap_and_prefer_boundaries():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(40))
    chunks = space_files.chunk_text(text)
    assert all(len(chunk) <= space_files.CHUNK_CHARS for chunk in chunks)
    assert all(f"Paragraph {i}." in "".join(chunks) for i in range(40))
    # Chunks end at paragraph boundaries rather than mid-sentence.
    assert all(chunk.endswith("word") for chunk in chunks[:-1])


def test_query_terms_are_safe_for_full_text_search_in_any_language():
    assert space_service.query_terms("What is the REVENUE growth in Deutschland? (2024)") == ["revenue", "growth", "deutschland", "2024"]
    assert space_service.query_terms("Ventes à Paris & Lyon | !") == ["ventes", "paris", "lyon"]
    assert space_service.query_terms("Как росла выручка") == ["как", "росла", "выручка"]
    assert all(term.replace("_", "").isalnum() for term in space_service.query_terms("a:* | b & !c <-> 'd'"))
    assert set(space_service.cjk_patterns("东京的销售")) == {"%东京%", "%的销%", "%京的%", "%销售%"}


# ── Answer pipeline ──────────────────────────────────────────────────────────

def parse(events):
    return [json.loads(item[6:]) for item in events]


def fake_space(web_search=True, sources=None, domains=None):
    context = space_service.SpaceContext(space_id=uuid4(), name="Research", instructions="Answer in French.",
                                         web_search=web_search, domains=domains or [], has_files=True)
    context.retrieve = AsyncMock(return_value=sources or [])
    return context


FILE_SOURCE = {"title": "Q3.docx", "url": "/api/v1/spaces/s/files/f/download", "domain": "Space file",
               "snippet": "Revenue grew 14 percent.", "source_type": "space_file"}
WEB_SOURCE = {"title": "News", "url": "https://example.org/n", "domain": "example.org", "snippet": "Market news."}


@pytest.mark.asyncio
async def test_files_only_space_never_searches_the_web_or_invents_answers():
    route = {"strategy": "standard", "query_type": "factual", "tools": ["web_search"], "requires_search": True}
    with patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
         patch("src.services.search_orchestrator.tool_executor.execute_tools", AsyncMock()) as tools, \
         patch.object(groq_llm_service, "stream_answer", AsyncMock()) as llm:
        events = parse([e async for e in SearchOrchestrator().stream_search("Revenue?", space=fake_space(web_search=False))])
    tools.assert_not_awaited()
    llm.assert_not_called()
    assert NO_SPACE_EVIDENCE in [e.get("content") for e in events if e["type"] == "token"]


@pytest.mark.asyncio
async def test_space_files_are_cited_first_and_instructions_reach_the_model():
    captured = {}

    async def answer(query, results, history, focus, **options):
        captured.update(results=results, options=options)
        yield "Le chiffre d'affaires a augmenté [1]."

    route = {"strategy": "standard", "query_type": "factual", "tools": ["web_search"], "requires_search": True}
    executor = AsyncMock(return_value=[ToolResult(success=True, tool_name="web_search",
        data={"results": [WEB_SOURCE]}, sources=[dict(WEB_SOURCE)])])
    space = fake_space(sources=[FILE_SOURCE], domains=["example.org"])
    with patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
         patch("src.services.search_orchestrator.tool_executor.execute_tools", executor), \
         patch("src.services.search_orchestrator.tool_executor.execute_single", AsyncMock(return_value=ToolResult(success=False))), \
         patch.object(groq_llm_service, "stream_answer", answer), \
         patch.object(groq_llm_service, "generate_follow_up_questions", AsyncMock(return_value=[])):
        events = parse([e async for e in SearchOrchestrator().stream_search("Revenue growth?", space=space)])
    sources = next(e for e in events if e["type"] == "sources")["sources"]
    assert [(s["title"], s["citationIndex"]) for s in sources] == [("Q3.docx", 1), ("News", 2)]
    assert captured["results"][0]["snippet"] == "Revenue grew 14 percent."
    assert captured["options"]["space_instructions"] == "Answer in French."
    assert executor.call_args.args[1].metadata["priority_domains"] == ["example.org"]
    space.retrieve.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_question_about_space_files_answers_from_files_without_web():
    route = {"strategy": "direct", "query_type": "text", "tools": [], "requires_search": False}

    async def answer(query, results, history, focus, **options):
        assert results[0]["title"] == "Q3.docx"
        yield "Summary [1]."

    with patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
         patch("src.services.search_orchestrator.tool_executor.execute_tools", AsyncMock(return_value=[])) as tools, \
         patch("src.services.search_orchestrator.tool_executor.execute_single", AsyncMock()) as images, \
         patch.object(groq_llm_service, "stream_answer", answer), \
         patch.object(groq_llm_service, "generate_follow_up_questions", AsyncMock(return_value=[])):
        events = parse([e async for e in SearchOrchestrator().stream_search("Summarize my report", space=fake_space(sources=[FILE_SOURCE]))])
    assert tools.await_args.args[0] == []
    images.assert_not_awaited()
    assert "Summary [1]." in "".join(e.get("content", "") for e in events if e["type"] == "token")


@pytest.mark.asyncio
async def test_greetings_in_a_space_do_not_search_files():
    route = {"strategy": "direct", "query_type": "greeting", "tools": [], "requires_search": False}

    async def answer(*args, **options):
        assert options["space_instructions"] == "Answer in French."
        yield "Bonjour !"

    space = fake_space(sources=[FILE_SOURCE])
    with patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
         patch.object(groq_llm_service, "stream_answer", answer):
        events = parse([e async for e in SearchOrchestrator().stream_search("hello", space=space)])
    space.retrieve.assert_not_awaited()
    assert not [e for e in events if e["type"] == "sources"]
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_priority_domains_are_cited_before_open_web_results():
    from src.tools.search.web_search_tool import WebSearchTool
    from src.tools import ToolContext
    calls = []

    async def search(query, max_results=10, include_domains=None):
        calls.append(include_domains)
        if include_domains:
            return {"results": [{"url": "https://docs.example.org/a", "title": "Pinned", "snippet": "pinned"},
                                {"url": "https://evil.test/x", "title": "Off", "snippet": "off"}]}
        return {"results": [{"url": "https://docs.example.org/a", "title": "Pinned", "snippet": "pinned"},
                            {"url": "https://web.test/b", "title": "Web", "snippet": "web"}]}

    with patch("src.services.web_search_service.tavily_search_service.client", object()), \
         patch("src.services.web_search_service.tavily_search_service.search", search):
        result = await WebSearchTool().execute(ToolContext(query="pricing", metadata={"priority_domains": ["example.org"]}))
    assert calls == [None, ["example.org"]]
    assert [r["title"] for r in result.data["results"]] == ["Pinned", "Web"]


def test_space_upload_paths_have_their_own_body_limit():
    from src.core.interpolation_limits import upload_limit
    assert upload_limit("/api/v1/spaces/abc/files")[0] == settings.SPACE_MAX_FILE_BYTES
    assert upload_limit("/api/v1/spaces/abc/files/x/download") is None
    assert upload_limit("/api/v1/interpolation/upload")[0] == 10 * 1024 * 1024
