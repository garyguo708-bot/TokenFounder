"""
Unit tests for Canvas Generator (backend/agents/canvas_generator.py).

All Anthropic API calls are mocked — no network required.

Test groups:
1. Happy path — model returns valid JSON → BusinessCanvas returned
2. JSON parsing — markdown stripping, whitespace trimming
3. Field mapping — all 9 canvas sections mapped correctly
4. is_inferred flag — propagated per section
5. Missing / partial model output — graceful defaults
6. next_steps — list preserved
7. API contract — correct model, prompt contains conversation history
8. Integration with session — uses history and judge_result extracted data
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.agents.canvas_generator import generate_canvas
from backend.models.bmc import BusinessCanvas, CanvasItem
from backend.models.session import Session
from backend.tests.conftest import make_mock_response, make_canvas_payload

pytestmark = pytest.mark.asyncio

_CANVAS_KEYS = [
    "customer_segments", "value_propositions", "channels",
    "customer_relationships", "revenue_streams", "key_resources",
    "key_activities", "key_partnerships", "cost_structure",
]


def patch_client(text: str):
    mock_resp = make_mock_response(text)
    return patch(
        "backend.agents.canvas_generator._client",
        messages=MagicMock(create=AsyncMock(return_value=mock_resp)),
    )


def _make_judge_result(extracted: dict | None = None) -> dict:
    if extracted is None:
        extracted = {k: None for k in _CANVAS_KEYS}
    return {"extracted": extracted}


# ── 1. Happy path ──────────────────────────────────────────────────────────────

class TestGenerateCanvasHappyPath:
    async def test_returns_business_canvas_instance(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert isinstance(canvas, BusinessCanvas)

    async def test_project_name_extracted(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.project_name == "SalesMind AI"

    async def test_tagline_extracted(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.tagline == "让每封销售邮件都像手写一样个性化"

    async def test_all_nine_sections_present(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        for key in _CANVAS_KEYS:
            item = getattr(canvas, key)
            assert isinstance(item, CanvasItem), f"{key} should be a CanvasItem"

    async def test_content_lists_populated(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert len(canvas.customer_segments.content) > 0
        assert len(canvas.value_propositions.content) > 0
        assert len(canvas.revenue_streams.content) > 0

    async def test_next_steps_populated(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert isinstance(canvas.next_steps, list)
        assert len(canvas.next_steps) == 3

    async def test_to_dict_roundtrip(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        d = canvas.to_dict()
        assert d["project_name"] == "SalesMind AI"
        assert "canvas" in d
        assert len(d["canvas"]) == 9


# ── 2. JSON parsing ────────────────────────────────────────────────────────────

class TestJSONParsing:
    async def test_strips_json_markdown_block(self, rich_session):
        inner = make_canvas_payload()
        wrapped = f"```json\n{inner}\n```"
        with patch_client(wrapped):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.project_name == "SalesMind AI"

    async def test_strips_plain_markdown_block(self, rich_session):
        inner = make_canvas_payload()
        wrapped = f"```\n{inner}\n```"
        with patch_client(wrapped):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.project_name == "SalesMind AI"

    async def test_strips_trailing_whitespace(self, rich_session):
        payload = "  " + make_canvas_payload() + "   \n"
        with patch_client(payload):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.project_name == "SalesMind AI"

    async def test_invalid_json_raises(self, rich_session):
        with patch_client("这根本不是JSON"):
            with pytest.raises(Exception):
                await generate_canvas(rich_session, _make_judge_result())


# ── 3. Field mapping ───────────────────────────────────────────────────────────

class TestFieldMapping:
    @pytest.mark.parametrize("key,expected_first_item", [
        ("customer_segments", "中大型企业B2B销售团队"),
        ("value_propositions", "AI生成个性化邮件，回复率提升3倍"),
        ("channels", "Salesforce AppExchange"),
        ("customer_relationships", "CSM一对一服务"),
        ("revenue_streams", "席位订阅$99/月"),
        ("key_resources", "销售邮件训练数据集"),
        ("key_activities", "模型持续训练"),
        ("key_partnerships", "Salesforce/HubSpot集成"),
        ("cost_structure", "LLM API调用成本"),
    ])
    async def test_section_content_mapped(self, rich_session, key, expected_first_item):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        item = getattr(canvas, key)
        assert expected_first_item in item.content

    async def test_content_is_list_of_strings(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        for key in _CANVAS_KEYS:
            item = getattr(canvas, key)
            assert isinstance(item.content, list)
            for point in item.content:
                assert isinstance(point, str)


# ── 4. is_inferred flag ────────────────────────────────────────────────────────

class TestIsInferredFlag:
    async def test_inferred_false_by_default(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.customer_segments.is_inferred is False
        assert canvas.value_propositions.is_inferred is False

    async def test_inferred_true_when_model_says_so(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        # From conftest: key_partnerships and channels are inferred
        assert canvas.key_partnerships.is_inferred is True

    async def test_all_inferred_false_when_model_says_so(self, rich_session):
        payload_data = json.loads(make_canvas_payload())
        for key in _CANVAS_KEYS:
            payload_data["canvas"][key]["is_inferred"] = False
        with patch_client(json.dumps(payload_data, ensure_ascii=False)):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        for key in _CANVAS_KEYS:
            assert getattr(canvas, key).is_inferred is False

    async def test_all_inferred_true(self, rich_session):
        payload_data = json.loads(make_canvas_payload())
        for key in _CANVAS_KEYS:
            payload_data["canvas"][key]["is_inferred"] = True
        with patch_client(json.dumps(payload_data, ensure_ascii=False)):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        for key in _CANVAS_KEYS:
            assert getattr(canvas, key).is_inferred is True


# ── 5. Missing / partial model output ─────────────────────────────────────────

class TestPartialModelOutput:
    async def test_missing_project_name_defaults(self, rich_session):
        payload_data = json.loads(make_canvas_payload())
        del payload_data["project_name"]
        with patch_client(json.dumps(payload_data, ensure_ascii=False)):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.project_name == "未命名项目"

    async def test_missing_tagline_defaults_to_empty(self, rich_session):
        payload_data = json.loads(make_canvas_payload())
        del payload_data["tagline"]
        with patch_client(json.dumps(payload_data, ensure_ascii=False)):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.tagline == ""

    async def test_missing_canvas_section_defaults_to_empty_item(self, rich_session):
        payload_data = json.loads(make_canvas_payload())
        del payload_data["canvas"]["key_partnerships"]
        with patch_client(json.dumps(payload_data, ensure_ascii=False)):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.key_partnerships.content == []
        assert canvas.key_partnerships.is_inferred is False

    async def test_missing_next_steps_defaults_to_empty_list(self, rich_session):
        payload_data = json.loads(make_canvas_payload())
        del payload_data["next_steps"]
        with patch_client(json.dumps(payload_data, ensure_ascii=False)):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.next_steps == []

    async def test_section_with_empty_content_list(self, rich_session):
        payload_data = json.loads(make_canvas_payload())
        payload_data["canvas"]["channels"]["content"] = []
        with patch_client(json.dumps(payload_data, ensure_ascii=False)):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.channels.content == []


# ── 6. next_steps ──────────────────────────────────────────────────────────────

class TestNextSteps:
    async def test_three_next_steps(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert len(canvas.next_steps) == 3

    async def test_next_steps_content(self, rich_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert "Beta" in canvas.next_steps[0]

    async def test_single_next_step(self, rich_session):
        payload_data = json.loads(make_canvas_payload())
        payload_data["next_steps"] = ["只有一步"]
        with patch_client(json.dumps(payload_data, ensure_ascii=False)):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        assert canvas.next_steps == ["只有一步"]


# ── 7. API contract ────────────────────────────────────────────────────────────

class TestAPIContract:
    async def test_uses_main_model(self, rich_session):
        from backend.config import config
        mock_resp = make_mock_response(make_canvas_payload())
        mock_create = AsyncMock(return_value=mock_resp)
        with patch(
            "backend.agents.canvas_generator._client",
            messages=MagicMock(create=mock_create),
        ):
            await generate_canvas(rich_session, _make_judge_result())
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == config.model_main

    async def test_prompt_includes_conversation_history(self, rich_session):
        mock_resp = make_mock_response(make_canvas_payload())
        mock_create = AsyncMock(return_value=mock_resp)
        with patch(
            "backend.agents.canvas_generator._client",
            messages=MagicMock(create=mock_create),
        ):
            await generate_canvas(rich_session, _make_judge_result())
        call_kwargs = mock_create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        # History truncated to last 3000 chars — check a distinctive phrase
        assert "SalesMind" in user_content or "B2B销售" in user_content

    async def test_prompt_includes_extracted_bmc_info(self, rich_session):
        extracted = {"customer_segments": "特定客户群", **{k: None for k in _CANVAS_KEYS if k != "customer_segments"}}
        judge = _make_judge_result(extracted=extracted)
        mock_resp = make_mock_response(make_canvas_payload())
        mock_create = AsyncMock(return_value=mock_resp)
        with patch(
            "backend.agents.canvas_generator._client",
            messages=MagicMock(create=mock_create),
        ):
            await generate_canvas(rich_session, judge)
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "特定客户群" in user_content

    async def test_called_exactly_once(self, rich_session):
        mock_resp = make_mock_response(make_canvas_payload())
        mock_create = AsyncMock(return_value=mock_resp)
        with patch(
            "backend.agents.canvas_generator._client",
            messages=MagicMock(create=mock_create),
        ):
            await generate_canvas(rich_session, _make_judge_result())
        assert mock_create.call_count == 1


# ── 8. Integration with session ────────────────────────────────────────────────

class TestSessionIntegration:
    async def test_uses_last_3000_chars_of_history(self, rich_session):
        """Verify truncation doesn't break parsing."""
        # Add a lot of content to force truncation
        for i in range(50):
            rich_session.add_message("user", f"消息 {i}: " + "内容" * 100)
            rich_session.add_message("assistant", f"回复 {i}: " + "分析" * 100)

        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(rich_session, _make_judge_result())
        # Should still work and return a valid canvas
        assert canvas.project_name == "SalesMind AI"

    async def test_empty_session_history_still_works(self, empty_session):
        with patch_client(make_canvas_payload()):
            canvas = await generate_canvas(empty_session, _make_judge_result())
        assert isinstance(canvas, BusinessCanvas)
