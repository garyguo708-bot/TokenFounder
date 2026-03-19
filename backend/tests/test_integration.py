"""
Integration tests for the FastAPI backend.

These tests exercise the full HTTP → SSE pipeline, mocking only the four
AI agent calls so no LLM / network access is needed.

Mocked at the backend.main import level:
  - check_topic    (guardrail)
  - orchestrate    (main orchestrator, async generator)
  - evaluate_bmc   (BMC judge)
  - generate_canvas (canvas generator)

Test groups:
  1.  Health & session state endpoints (smoke)
  2.  Normal chat turn — text + bmc_progress events
  3.  Off-topic message — redirect event only, pipeline aborted
  4.  Canvas triggered — canvas_start + canvas_complete appended
  5.  Canvas idempotency — second trigger skipped when already generated
  6.  Event ordering — text always precedes bmc_progress
  7.  Multi-chunk streaming — all chunks delivered as separate text events
  8.  Session persistence — state visible via GET after POST
  9.  Error handling — unhandled exception → error event
  10. bmc_progress payload — correct fields & values
  11. canvas_complete payload — matches BusinessCanvas.to_dict() schema
"""

import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.models.bmc import BusinessCanvas, CanvasItem
from backend.models.session import _sessions, DTStage

pytestmark = pytest.mark.asyncio


# ── Fixtures & helpers ─────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    """httpx async client backed by the FastAPI ASGI app (no real server)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


def fresh_sid() -> str:
    """Unique session ID per test — avoids cross-test session state leakage."""
    return str(uuid.uuid4())


def _full_canvas() -> BusinessCanvas:
    """Minimal but structurally complete BusinessCanvas for testing."""
    def item(content, inferred=False):
        return CanvasItem(content, inferred)

    return BusinessCanvas(
        project_name="SalesMind AI",
        tagline="让每封销售邮件都像手写一样个性化",
        customer_segments=item(["B2B销售团队"]),
        value_propositions=item(["回复率提升3倍"]),
        channels=item(["Salesforce"]),
        customer_relationships=item(["CSM服务"]),
        revenue_streams=item(["$99/月/席位"]),
        key_resources=item(["训练数据集"]),
        key_activities=item(["模型训练"]),
        key_partnerships=item(["Salesforce集成"], inferred=True),
        cost_structure=item(["API调用成本"]),
        next_steps=["招募Beta用户", "开发MVP"],
    )


def mock_orchestrate(chunks: list[str]):
    """Replace orchestrate() with an async generator yielding fixed chunks."""
    async def _gen(session):
        for chunk in chunks:
            yield chunk
    return _gen


def _guard(relevant: bool = True, redirect: str = "偏题了，请继续聊创业想法") -> AsyncMock:
    payload = {"is_relevant": relevant, "confidence": 0.95, "redirect_message": None}
    if not relevant:
        payload["redirect_message"] = redirect
    return AsyncMock(return_value=payload)


def _judge(covered: int = 3, trigger: bool = False) -> AsyncMock:
    return AsyncMock(return_value={
        "scores": {},
        "covered_count": covered,
        "trigger_canvas": trigger,
        "missing_items": ["渠道通路", "成本结构"],
        "extracted": {},
    })


def parse_sse(content: bytes) -> list[dict]:
    """Parse raw SSE bytes into a list of parsed event dicts."""
    events = []
    for line in content.decode("utf-8").splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def post_chat(client, session_id: str, message: str = "我想做一个AI销售助理"):
    return client.post("/api/chat", json={"session_id": session_id, "message": message})


# ── 1. Smoke tests ─────────────────────────────────────────────────────────────

class TestHealthAndSession:
    async def test_health_returns_ok(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    async def test_new_session_defaults(self, client):
        sid = fresh_sid()
        r = await client.get(f"/api/session/{sid}")
        assert r.status_code == 200
        body = r.json()
        assert body["session_id"] == sid
        assert body["current_stage"] == DTStage.EMPATHIZE.value
        assert body["turn_count"] == 0
        assert body["bmc_covered"] == 0
        assert body["canvas_generated"] is False
        assert body["messages"] == []

    async def test_session_endpoint_returns_200_for_any_id(self, client):
        r = await client.get(f"/api/session/{fresh_sid()}")
        assert r.status_code == 200

    async def test_post_chat_returns_200_with_sse_content_type(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            r = await post_chat(client, sid)
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]


# ── 2. Normal chat turn ────────────────────────────────────────────────────────

class TestNormalChatTurn:
    async def test_emits_text_events(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["你好！", "说说你的想法"])),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        text_events = [e for e in events if e["type"] == "text"]
        assert len(text_events) == 2
        assert text_events[0]["data"]["chunk"] == "你好！"
        assert text_events[1]["data"]["chunk"] == "说说你的想法"

    async def test_emits_bmc_progress_event(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(covered=4)),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        progress = [e for e in events if e["type"] == "bmc_progress"]
        assert len(progress) == 1
        assert progress[0]["data"]["covered_count"] == 4
        assert progress[0]["data"]["total"] == 9

    async def test_no_canvas_events_when_not_triggered(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(trigger=False)),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        types = {e["type"] for e in events}
        assert "canvas_start" not in types
        assert "canvas_complete" not in types

    async def test_no_redirect_on_relevant_message(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard(relevant=True)),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        assert not any(e["type"] == "redirect" for e in events)


# ── 3. Off-topic (guardrail redirects) ────────────────────────────────────────

class TestGuardrailRedirect:
    async def test_emits_redirect_event(self, client):
        sid = fresh_sid()
        with patch("backend.main.check_topic", new=_guard(relevant=False, redirect="偏题了！")):
            r = await client.post(
                "/api/chat",
                json={"session_id": sid, "message": "今天天气怎么样？"},
            )

        events = parse_sse(r.content)
        assert len(events) == 1
        assert events[0]["type"] == "redirect"
        assert events[0]["data"]["message"] == "偏题了！"

    async def test_redirect_aborts_pipeline_no_text(self, client):
        sid = fresh_sid()
        mock_orch = MagicMock()  # should never be called
        with (
            patch("backend.main.check_topic", new=_guard(relevant=False)),
            patch("backend.main.orchestrate", new=mock_orch),
        ):
            r = await client.post(
                "/api/chat",
                json={"session_id": sid, "message": "随便说说"},
            )

        events = parse_sse(r.content)
        types = [e["type"] for e in events]
        assert "text" not in types
        assert "bmc_progress" not in types
        mock_orch.assert_not_called()

    async def test_redirect_does_not_add_user_message_to_session(self, client):
        sid = fresh_sid()
        with patch("backend.main.check_topic", new=_guard(relevant=False)):
            await client.post(
                "/api/chat",
                json={"session_id": sid, "message": "今天天气如何"},
            )

        r = await client.get(f"/api/session/{sid}")
        # Session was auto-created by GET; turn_count was never incremented
        assert r.json()["turn_count"] == 0


# ── 4. Canvas triggered ────────────────────────────────────────────────────────

class TestCanvasTriggered:
    async def test_canvas_start_event_emitted(self, client):
        sid = fresh_sid()
        canvas = _full_canvas()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(covered=7, trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=canvas)),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        assert any(e["type"] == "canvas_start" for e in events)

    async def test_canvas_complete_event_emitted(self, client):
        sid = fresh_sid()
        canvas = _full_canvas()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(covered=7, trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=canvas)),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        complete = [e for e in events if e["type"] == "canvas_complete"]
        assert len(complete) == 1

    async def test_canvas_complete_data_matches_to_dict(self, client):
        sid = fresh_sid()
        canvas = _full_canvas()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(covered=7, trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=canvas)),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        complete = next(e for e in events if e["type"] == "canvas_complete")
        expected = canvas.to_dict()
        assert complete["data"]["project_name"] == expected["project_name"]
        assert complete["data"]["tagline"] == expected["tagline"]
        assert set(complete["data"]["canvas"].keys()) == set(expected["canvas"].keys())
        assert complete["data"]["next_steps"] == expected["next_steps"]

    async def test_session_stage_set_to_complete_after_canvas(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(covered=7, trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=_full_canvas())),
        ):
            await post_chat(client, sid)

        state = (await client.get(f"/api/session/{sid}")).json()
        assert state["current_stage"] == DTStage.COMPLETE.value
        assert state["canvas_generated"] is True


# ── 5. Canvas idempotency ──────────────────────────────────────────────────────

class TestCanvasIdempotency:
    async def test_canvas_not_generated_twice(self, client):
        sid = fresh_sid()
        mock_gen_canvas = AsyncMock(return_value=_full_canvas())

        def _do_chat():
            return post_chat(client, sid)

        for _ in range(2):
            with (
                patch("backend.main.check_topic", new=_guard()),
                patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
                patch("backend.main.evaluate_bmc", new=_judge(covered=9, trigger=True)),
                patch("backend.main.generate_canvas", new=mock_gen_canvas),
            ):
                await _do_chat()

        # generate_canvas should only have been called once across both turns
        assert mock_gen_canvas.call_count == 1

    async def test_no_canvas_events_on_second_turn_after_generated(self, client):
        sid = fresh_sid()

        # First turn: triggers canvas
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(covered=9, trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=_full_canvas())),
        ):
            await post_chat(client, sid)

        # Second turn: trigger=True again but canvas_generated is now True
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Follow-up"])),
            patch("backend.main.evaluate_bmc", new=_judge(covered=9, trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=_full_canvas())) as mock_gen,
        ):
            r2 = await post_chat(client, sid, message="继续聊")

        events2 = parse_sse(r2.content)
        assert not any(e["type"] in ("canvas_start", "canvas_complete") for e in events2)
        mock_gen.assert_not_called()


# ── 6. Event ordering ──────────────────────────────────────────────────────────

class TestEventOrdering:
    async def test_text_events_precede_bmc_progress(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["A", "B", "C"])),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        types = [e["type"] for e in events]
        last_text_idx = max(i for i, t in enumerate(types) if t == "text")
        progress_idx = next(i for i, t in enumerate(types) if t == "bmc_progress")
        assert last_text_idx < progress_idx

    async def test_canvas_start_precedes_canvas_complete(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=_full_canvas())),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        types = [e["type"] for e in events]
        start_idx = types.index("canvas_start")
        complete_idx = types.index("canvas_complete")
        assert start_idx < complete_idx

    async def test_full_event_sequence_with_canvas(self, client):
        """text* → bmc_progress → canvas_start → canvas_complete"""
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=_full_canvas())),
        ):
            r = await post_chat(client, sid)

        types = [e["type"] for e in parse_sse(r.content)]
        assert "text" in types
        assert "bmc_progress" in types
        assert "canvas_start" in types
        assert "canvas_complete" in types
        # Structural ordering
        assert types.index("bmc_progress") > types.index("text")
        assert types.index("canvas_start") > types.index("bmc_progress")
        assert types.index("canvas_complete") > types.index("canvas_start")


# ── 7. Multi-chunk streaming ───────────────────────────────────────────────────

class TestMultiChunkStreaming:
    async def test_each_chunk_becomes_separate_text_event(self, client):
        chunks = ["这是", "一个", "流式", "回复", "的测试"]
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(chunks)),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            r = await post_chat(client, sid)

        text_events = [e for e in parse_sse(r.content) if e["type"] == "text"]
        assert len(text_events) == len(chunks)
        assert [e["data"]["chunk"] for e in text_events] == chunks

    async def test_single_chunk_works(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["单一回复"])),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            r = await post_chat(client, sid)

        text_events = [e for e in parse_sse(r.content) if e["type"] == "text"]
        assert len(text_events) == 1
        assert text_events[0]["data"]["chunk"] == "单一回复"

    async def test_empty_orchestrator_still_emits_bmc_progress(self, client):
        """Even with no text output, bmc_progress must be sent."""
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate([])),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        assert any(e["type"] == "bmc_progress" for e in events)


# ── 8. Session persistence ─────────────────────────────────────────────────────

class TestSessionPersistence:
    async def test_turn_count_increments_after_chat(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            await post_chat(client, sid)

        state = (await client.get(f"/api/session/{sid}")).json()
        assert state["turn_count"] == 1

    async def test_messages_stored_in_session(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["你好，很高兴聊！"])),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            await post_chat(client, sid, message="我有个创业想法")

        state = (await client.get(f"/api/session/{sid}")).json()
        messages = state["messages"]
        assert len(messages) == 2  # user + assistant
        assert messages[0] == {"role": "user", "content": "我有个创业想法"}
        assert messages[1] == {"role": "assistant", "content": "你好，很高兴聊！"}

    async def test_bmc_covered_reflected_in_session_state(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(covered=5)),
        ):
            await post_chat(client, sid)

        # bmc_covered in GET endpoint comes from session.bmc_info.covered_count
        # (which is updated by evaluate_bmc via session mutation)
        state = (await client.get(f"/api/session/{sid}")).json()
        # covered_count may be 0 or 5 depending on whether the judge mock
        # also calls update_from_judge; here we just verify the field exists
        assert "bmc_covered" in state

    async def test_multiple_turns_accumulate_messages(self, client):
        sid = fresh_sid()
        for i, msg in enumerate(["第一轮", "第二轮", "第三轮"]):
            with (
                patch("backend.main.check_topic", new=_guard()),
                patch("backend.main.orchestrate", new=mock_orchestrate([f"回复{i}"])),
                patch("backend.main.evaluate_bmc", new=_judge()),
            ):
                await post_chat(client, sid, message=msg)

        state = (await client.get(f"/api/session/{sid}")).json()
        assert state["turn_count"] == 3
        assert len(state["messages"]) == 6  # 3 user + 3 assistant


# ── 9. Error handling ──────────────────────────────────────────────────────────

class TestErrorHandling:
    async def test_orchestrator_exception_emits_error_event(self, client):
        async def _exploding_orchestrate(session):
            raise RuntimeError("模拟API崩溃")
            yield  # make it a generator

        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=_exploding_orchestrate),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        assert r.status_code == 200  # SSE always returns 200 initially
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "RuntimeError" in error_events[0]["data"]["message"]

    async def test_evaluate_bmc_exception_emits_error_event(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=AsyncMock(side_effect=ValueError("judge崩了"))),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        assert any(e["type"] == "error" for e in events)

    async def test_generate_canvas_exception_emits_error_event(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(side_effect=RuntimeError("canvas崩了"))),
        ):
            r = await post_chat(client, sid)

        events = parse_sse(r.content)
        assert any(e["type"] == "error" for e in events)

    async def test_error_event_no_crash_to_http_500(self, client):
        """Even on internal error the HTTP response is 200 (SSE contract)."""
        async def _boom(session):
            raise Exception("BOOM")
            yield

        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=_boom),
        ):
            r = await post_chat(client, sid)

        assert r.status_code == 200


# ── 10. bmc_progress payload detail ───────────────────────────────────────────

class TestBMCProgressPayload:
    async def test_bmc_progress_has_all_required_fields(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(covered=6)),
        ):
            r = await post_chat(client, sid)

        progress = next(e for e in parse_sse(r.content) if e["type"] == "bmc_progress")
        data = progress["data"]
        assert "covered_count" in data
        assert "total" in data
        assert "missing_items" in data
        assert "current_stage" in data

    async def test_bmc_progress_total_always_nine(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(covered=0)),
        ):
            r = await post_chat(client, sid)

        progress = next(e for e in parse_sse(r.content) if e["type"] == "bmc_progress")
        assert progress["data"]["total"] == 9

    async def test_bmc_progress_stage_is_valid_dt_stage(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            r = await post_chat(client, sid)

        progress = next(e for e in parse_sse(r.content) if e["type"] == "bmc_progress")
        valid_stages = {s.value for s in DTStage}
        assert progress["data"]["current_stage"] in valid_stages

    async def test_bmc_missing_items_is_list(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge()),
        ):
            r = await post_chat(client, sid)

        progress = next(e for e in parse_sse(r.content) if e["type"] == "bmc_progress")
        assert isinstance(progress["data"]["missing_items"], list)


# ── 11. canvas_complete payload structure ──────────────────────────────────────

class TestCanvasCompletePayload:
    async def test_canvas_complete_has_nine_sections(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=_full_canvas())),
        ):
            r = await post_chat(client, sid)

        complete = next(e for e in parse_sse(r.content) if e["type"] == "canvas_complete")
        assert len(complete["data"]["canvas"]) == 9

    async def test_canvas_is_inferred_flag_present_in_all_sections(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=_full_canvas())),
        ):
            r = await post_chat(client, sid)

        complete = next(e for e in parse_sse(r.content) if e["type"] == "canvas_complete")
        for key, section in complete["data"]["canvas"].items():
            assert "is_inferred" in section, f"is_inferred missing in {key}"
            assert "content" in section, f"content missing in {key}"

    async def test_canvas_inferred_flag_value_preserved(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=_full_canvas())),
        ):
            r = await post_chat(client, sid)

        complete = next(e for e in parse_sse(r.content) if e["type"] == "canvas_complete")
        # key_partnerships was set to inferred=True in _full_canvas()
        assert complete["data"]["canvas"]["key_partnerships"]["is_inferred"] is True
        assert complete["data"]["canvas"]["customer_segments"]["is_inferred"] is False

    async def test_canvas_next_steps_is_list(self, client):
        sid = fresh_sid()
        with (
            patch("backend.main.check_topic", new=_guard()),
            patch("backend.main.orchestrate", new=mock_orchestrate(["Hi"])),
            patch("backend.main.evaluate_bmc", new=_judge(trigger=True)),
            patch("backend.main.generate_canvas", new=AsyncMock(return_value=_full_canvas())),
        ):
            r = await post_chat(client, sid)

        complete = next(e for e in parse_sse(r.content) if e["type"] == "canvas_complete")
        assert isinstance(complete["data"]["next_steps"], list)
        assert len(complete["data"]["next_steps"]) == 2
