"""Answer modes, chat attachments, personalization and memory."""
import io
import json
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4, UUID
import pytest
import pytest_asyncio
from fastapi import Request
from httpx import AsyncClient, ASGITransport
from PIL import Image
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.main import app
from src.api.deps import get_db, get_current_user_id
from src.config.settings import settings
from src.models.user import User
from src.models.attachment import ChatAttachment, UserMemory
from src.services import answer_modes, attachments, personalization, space_files
from src.services.chat_context import TurnContext, attachment_sources
from src.services.llm_service import groq_llm_service, ReasoningChunk
from src.services.search_orchestrator import SearchOrchestrator
from src.tools import ToolResult


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(element, compiler, **kw):
    return "JSON"


ALICE, BOB = str(uuid4()), str(uuid4())


@pytest_asyncio.fixture
async def sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SPACE_FILES_DIR", str(tmp_path / "files"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: [table.create(sync) for table in
                                                (User.__table__, ChatAttachment.__table__, UserMemory.__table__)])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        for user, name in ((ALICE, "Alice"), (BOB, "Bob")):
            db.add(User(id=UUID(user), name=name, email=f"{name.lower()}@example.com", preferences={}))
        await db.commit()

    async def database():
        async with factory() as session:
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
    yield factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(sessions):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


def as_user(user):
    return {"x-test-user": user}


def png(width=40, height=30, mode="RGBA", color=(200, 30, 30, 128), exif=False):
    image = Image.new(mode, (width, height), color)
    output = io.BytesIO()
    if exif:
        image = image.convert("RGB")
        data = image.getexif()
        data[0x010F] = "SecretCameraMaker"  # Make
        image.save(output, format="JPEG", exif=data.tobytes())
    else:
        image.save(output, format="PNG")
    return output.getvalue()


# ── Modes ────────────────────────────────────────────────────────────────────

def test_answer_modes_choose_capable_models():
    assert answer_modes.resolve("auto").model == settings.DEFAULT_MODEL
    assert answer_modes.resolve("auto", complexity=5).model == settings.HEAVY_MODEL
    assert answer_modes.resolve("auto", strategy="deep").mode == "pro"
    think = answer_modes.resolve("think")
    assert think.model == settings.HEAVY_MODEL and think.reasoning_effort == "high" and think.show_reasoning
    # Fast cannot hold long documents; images always need the vision model.
    assert answer_modes.resolve("fast", long_context=True).mode == "pro"
    assert answer_modes.resolve("pro", has_images=True).model == settings.VISION_MODEL
    assert answer_modes.resolve("unknown").mode == "fast"


def test_runtime_gives_large_models_a_larger_output_budget():
    from src.services.llm_runtime import LLMRuntime, Endpoint
    runtime = LLMRuntime([Endpoint("groq", object())], 2048, {settings.HEAVY_MODEL: 8192})
    assert runtime._options(runtime.endpoints[0], {"model": settings.HEAVY_MODEL, "max_tokens": 50000})["max_tokens"] == 8192
    assert runtime._options(runtime.endpoints[0], {"model": settings.DEFAULT_MODEL, "max_tokens": 50000})["max_tokens"] == 2048


# ── Image safety ─────────────────────────────────────────────────────────────

def test_images_are_reencoded_bounded_and_stripped_of_metadata(monkeypatch):
    big = attachments.normalize_image(png(5000, 100))
    with Image.open(io.BytesIO(big)) as image:
        assert image.format == "JPEG" and max(image.size) == attachments.MAX_IMAGE_SIDE
    with Image.open(io.BytesIO(attachments.normalize_image(png(exif=True, mode="RGB", color=(1, 2, 3))))) as image:
        assert "SecretCameraMaker" not in str(dict(image.getexif()))
    # Transparency is flattened onto white rather than black.
    with Image.open(io.BytesIO(attachments.normalize_image(png(color=(0, 0, 0, 0))))) as image:
        assert image.getpixel((5, 5))[0] > 240
    for bad in (b"not an image", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20):
        with pytest.raises(space_files.FileRejected):
            attachments.normalize_image(bad)
    monkeypatch.setattr(attachments, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(space_files.FileRejected):
        attachments.normalize_image(png(400, 400))


# ── Attachments API ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_attachments_are_private_typed_and_expire(client, sessions):
    image = (await client.post("/api/v1/attachments", headers=as_user(ALICE), files={"file": ("chart.png", png())})).json()
    assert image["kind"] == "image" and image["contentType"] == "image/jpeg"
    doc = (await client.post("/api/v1/attachments", headers=as_user(ALICE),
                             files={"file": ("brief.md", "# Brief\nLaunch budget is 3.2 million euros.".encode())})).json()
    assert doc["kind"] == "document" and doc["characters"] > 10
    assert (await client.post("/api/v1/attachments", headers=as_user(ALICE), files={"file": ("x.exe", b"MZ")})).status_code == 415
    assert (await client.post("/api/v1/attachments", headers=as_user(ALICE), files={"file": ("x.png", b"junk")})).status_code == 422

    shown = await client.get(image["url"], headers=as_user(ALICE))
    assert shown.status_code == 200 and shown.headers["content-type"] == "image/jpeg"
    assert shown.headers["x-content-type-options"] == "nosniff"
    download = await client.get(doc["url"], headers=as_user(ALICE))
    assert download.headers["content-type"] == "application/octet-stream" and "attachment" in download.headers["content-disposition"]
    # Another account cannot read, list or delete them.
    assert (await client.get(image["url"], headers=as_user(BOB))).status_code == 404
    assert (await client.get("/api/v1/attachments", headers=as_user(BOB))).json()["items"] == []
    assert (await client.delete(f"/api/v1/attachments/{doc['id']}", headers=as_user(BOB))).status_code == 404

    async with sessions() as db:
        documents, images, names = await attachments.load_for_turn(db, ALICE, [doc["id"], image["id"], str(uuid4()), "bad"])
        assert [d["name"] for d in documents] == ["brief.md"] and names == ["chart.png"]
        assert images[0].startswith("data:image/jpeg;base64,")
        assert await attachments.load_for_turn(db, BOB, [doc["id"], image["id"]]) == ([], [], [])
        row = await db.get(ChatAttachment, UUID(doc["id"]))
        row.expires_at = attachments.now() - timedelta(minutes=1)
        await db.commit()
    assert (await client.get(doc["url"], headers=as_user(ALICE))).status_code == 404
    async with sessions() as db:
        assert (await attachments.load_for_turn(db, ALICE, [doc["id"]]))[0] == []
        assert await attachments.purge_expired(db, UUID(ALICE)) == 1
        await db.commit()
    assert not attachments.file_path(UUID(ALICE), UUID(doc["id"])).exists()
    assert (await client.delete(f"/api/v1/attachments/{image['id']}", headers=as_user(ALICE))).status_code == 204
    assert not attachments.file_path(UUID(ALICE), UUID(image["id"])).exists()


@pytest.mark.asyncio
async def test_attachment_storage_quota(client, monkeypatch):
    monkeypatch.setattr(settings, "ATTACHMENT_MAX_PER_USER", 1)
    assert (await client.post("/api/v1/attachments", headers=as_user(ALICE), files={"file": ("a.txt", b"one")})).status_code == 201
    assert (await client.post("/api/v1/attachments", headers=as_user(ALICE), files={"file": ("b.txt", b"two")})).status_code == 413


def test_long_documents_contribute_their_most_relevant_passages():
    filler = "\n\n".join(f"Section {i}. Routine operational notes about logistics and staffing." for i in range(400))
    text = "Annual report summary.\n\n" + filler + "\n\nThe oncology pipeline produced revenue of 812 million euros.\n\n" + filler
    [source] = attachment_sources([{"id": "a1", "name": "report.pdf", "text": text}], "oncology revenue", 6000)
    assert "812 million" in source["snippet"] and source["snippet"].startswith("Annual report summary")
    assert len(source["snippet"]) <= 6000 + 200 and source["domain"] == "Attachment"
    [small] = attachment_sources([{"id": "a2", "name": "n.txt", "text": "Short note."}], "x", 6000)
    assert small["snippet"] == "Short note." and small["url"] == "/api/v1/attachments/a2/content"


# ── Personalization ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_preferences_memories_and_private_chats(client, sessions):
    defaults = (await client.get("/api/v1/me/personalization", headers=as_user(ALICE))).json()
    assert defaults == {"style": "normal", "custom_style": "", "personal_instructions": "", "memory_enabled": True}
    updated = await client.put("/api/v1/me/personalization", headers=as_user(ALICE),
                               json={"style": "concise", "personal_instructions": "  Use metric units.  "})
    assert updated.json()["personal_instructions"] == "Use metric units."
    assert (await client.put("/api/v1/me/personalization", headers=as_user(ALICE), json={"style": "loud"})).status_code == 422
    assert (await client.put("/api/v1/me/personalization", headers=as_user(ALICE), json={})).status_code == 422

    first = (await client.post("/api/v1/me/memories", headers=as_user(ALICE), json={"content": "User leads EU oncology pricing"})).json()
    assert (await client.post("/api/v1/me/memories", headers=as_user(ALICE), json={"content": "user leads EU oncology pricing."})).json() == {"duplicate": True}
    edited = (await client.patch(f"/api/v1/me/memories/{first['id']}", headers=as_user(ALICE), json={"content": "User leads APAC pricing"})).json()
    assert edited["content"] == "User leads APAC pricing" and edited["source"] == "manual"
    assert (await client.delete(f"/api/v1/me/memories/{first['id']}", headers=as_user(BOB))).status_code == 404
    assert (await client.get("/api/v1/me/memories", headers=as_user(BOB))).json()["items"] == []

    async with sessions() as db:
        block = await personalization.personal_block(db, ALICE)
        assert "Use metric units." in block and "User leads APAC pricing" in block and "RESPONSE STYLE" in block
        private = await personalization.personal_block(db, ALICE, incognito=True)
        assert "Use metric units." in private and "APAC" not in private
        await personalization.update_preferences(db, ALICE, {"memory_enabled": False})
        assert "APAC" not in await personalization.personal_block(db, ALICE)
        assert await personalization.personal_block(db, BOB) == ""
    assert (await client.delete("/api/v1/me/memories", headers=as_user(ALICE))).json() == {"removed": 1}


def test_memory_extraction_only_runs_for_self_disclosure():
    assert personalization.should_extract("I'm a market analyst in Munich")
    assert personalization.should_extract("Remember that we use IFRS")
    assert not personalization.should_extract("What is the capital of Peru?")
    assert not personalization.should_extract("Summarize this article about Pfizer")


@pytest.mark.asyncio
async def test_memory_extraction_saves_new_facts_once(sessions, monkeypatch):
    import src.db.session as db_session
    monkeypatch.setattr(db_session, "async_session_factory", sessions)

    class Completion:
        def __init__(self, content): self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]

    reply = json.dumps({"memories": ["User is a market analyst in Munich", "", "x" * 400]})
    fake = type("Client", (), {})()
    fake.chat = type("Chat", (), {})()
    fake.chat.completions = type("Completions", (), {"create": AsyncMock(return_value=Completion(reply))})()
    with patch.object(groq_llm_service, "client", fake):
        assert await personalization.remember_from_message(ALICE, "I'm a market analyst in Munich") == ["User is a market analyst in Munich"]
        assert await personalization.remember_from_message(ALICE, "I'm a market analyst in Munich") == []
        assert await personalization.remember_from_message(ALICE, "What is GDP?") == []
        assert fake.chat.completions.create.await_count == 2
    async with sessions() as db:
        memories = await personalization.list_memories(db, ALICE)
        assert [(m["content"], m["source"]) for m in memories] == [("User is a market analyst in Munich", "auto")]


# ── Orchestrator integration ─────────────────────────────────────────────────

def parse(events):
    return [json.loads(item[6:]) for item in events]


@pytest.mark.asyncio
async def test_image_questions_use_the_vision_model_without_web_search():
    captured = {}

    async def answer(query, results, history, focus, **options):
        captured.update(options)
        yield "The chart shows revenue rising."

    route = {"strategy": "quick", "query_type": "factual", "tools": ["web_search"], "requires_search": True}
    turn = TurnContext(images=["data:image/jpeg;base64,AAAA"], image_names=["chart.png"], personal="\nPERSONAL\n")
    with patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
         patch("src.services.search_orchestrator.tool_executor.execute_tools", AsyncMock(return_value=[])) as tools, \
         patch("src.services.search_orchestrator.tool_executor.execute_single", AsyncMock()) as image_search, \
         patch.object(groq_llm_service, "stream_answer", answer), \
         patch.object(groq_llm_service, "generate_follow_up_questions", AsyncMock(return_value=[])):
        events = parse([e async for e in SearchOrchestrator().stream_search("What does this chart show?", turn=turn)])
    assert tools.await_args.args[0] == [] and not image_search.await_count
    assert captured["profile"].model == settings.VISION_MODEL and captured["images"] == turn.images
    assert captured["personal"] == "\nPERSONAL\n"
    assert "The chart shows revenue rising." in [e.get("content") for e in events]
    assert next(e for e in events if e["type"] == "meta")["mode"] == "Vision"


@pytest.mark.asyncio
async def test_attached_documents_are_cited_first_even_when_no_search_is_needed():
    captured = {}

    async def answer(query, results, history, focus, **options):
        captured["results"] = results
        yield "The budget is 3.2 million euros [1]."

    route = {"strategy": "direct", "query_type": "text", "tools": [], "requires_search": False}
    turn = TurnContext(documents=[{"id": "d1", "name": "brief.md", "text": "Launch budget is 3.2 million euros."}])
    with patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
         patch("src.services.search_orchestrator.tool_executor.execute_tools", AsyncMock(return_value=[])), \
         patch.object(groq_llm_service, "stream_answer", answer), \
         patch.object(groq_llm_service, "generate_follow_up_questions", AsyncMock(return_value=[])):
        events = parse([e async for e in SearchOrchestrator().stream_search("Summarize my brief", turn=turn)])
    sources = next(e for e in events if e["type"] == "sources")["sources"]
    assert sources[0]["title"] == "brief.md" and sources[0]["citationIndex"] == 1 and "snippet_limit" not in sources[0]
    assert captured["results"][0]["snippet"] == "Launch budget is 3.2 million euros."


@pytest.mark.asyncio
async def test_extended_thinking_streams_reasoning_separately():
    async def answer(query, results, history, focus, **options):
        assert options["profile"].mode == "think"
        yield ReasoningChunk("Let x be the ball price. ")
        yield "The ball costs $0.05."

    route = {"strategy": "direct", "query_type": "math", "tools": [], "requires_search": False}
    with patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
         patch.object(groq_llm_service, "stream_answer", answer):
        events = parse([e async for e in SearchOrchestrator().stream_search("Bat and ball puzzle", turn=TurnContext(mode="think"))])
    assert [e["content"] for e in events if e["type"] == "reasoning"] == ["Let x be the ball price. "]
    assert "".join(e.get("content", "") for e in events if e["type"] == "token") == "The ball costs $0.05."
    assert {"type": "mode", "mode": "think", "label": "Extended thinking"} in events


@pytest.mark.asyncio
async def test_recall_questions_use_saved_memory_when_the_chat_has_no_history():
    from src.services.conversation_memory import MISSING_HISTORY
    route = {"strategy": "direct", "query_type": "question_recall", "tools": [], "requires_search": False}
    memory = "\n\n" + personalization.MEMORY_HEADING + " (saved memories):\n- User is based in Munich\n"
    captured = {}

    async def answer(query, results, history, focus="all", **options):
        captured.update(options)
        yield "You told me you're based in Munich."

    with patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
         patch.object(groq_llm_service, "stream_answer", answer):
        events = parse([e async for e in SearchOrchestrator().stream_search("Which city am I based in?", turn=TurnContext(personal=memory))])
        assert "Munich" in "".join(e.get("content", "") for e in events if e["type"] == "token")
        assert captured["conversation_only"] is True and captured["personal"] == memory
        # Without memories or history, the honest fixed reply is kept and no model call is made.
        captured.clear()
        events = parse([e async for e in SearchOrchestrator().stream_search("Which city am I based in?", turn=TurnContext())])
        assert [e["content"] for e in events if e["type"] == "token"] == [MISSING_HISTORY] and not captured


@pytest.mark.asyncio
async def test_private_chats_skip_memory_capture(client):
    with patch("src.api.v1.search.search_orchestrator.stream_search") as stream, \
         patch("src.api.v1.search.personalization.remember_from_message", AsyncMock()) as remember:
        async def empty(*args, **kwargs):
            yield "data: {}\n\n"
        stream.side_effect = empty
        await client.post("/api/v1/search/stream", headers=as_user(ALICE), json={"query": "I'm a pharma analyst", "incognito": True})
        remember.assert_not_awaited()
        await client.post("/api/v1/search/stream", headers=as_user(ALICE), json={"query": "I'm a pharma analyst", "mode": "pro"})
        remember.assert_awaited_once_with(ALICE, "I'm a pharma analyst")
        assert stream.call_args.kwargs["turn"].mode == "pro"
    assert (await client.post("/api/v1/search/stream", headers=as_user(ALICE), json={"query": "x", "mode": "turbo"})).status_code == 422
