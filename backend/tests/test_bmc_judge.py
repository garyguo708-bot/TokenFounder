"""
Unit tests for BMC Judge (backend/agents/bmc_judge.py).

All Anthropic API calls are mocked — no network required.

Test groups:
1. Happy path — model returns valid JSON
2. Score recomputation — covered_count derived from scores, not trusted from model
3. Trigger logic — threshold boundary (6 vs 7 vs 9 covered)
4. Missing items — Chinese labels derived correctly
5. Session state mutation — bmc_info updated from extracted data
6. Resilience — malformed / wrapped JSON handled gracefully
7. Edge cases — all zeros, all twos, mixed
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.agents.bmc_judge import evaluate_bmc, _BMC_KEYS, _MISSING_LABELS
from backend.models.session import Session, BMCInfo
from backend.tests.conftest import make_mock_response, make_judge_payload

pytestmark = pytest.mark.asyncio

# ── Helpers ────────────────────────────────────────────────────────────────────

ALL_ZERO_SCORES = {k: 0 for k in _BMC_KEYS}
ALL_ONE_SCORES = {k: 1 for k in _BMC_KEYS}
ALL_TWO_SCORES = {k: 2 for k in _BMC_KEYS}

THRESHOLD = 7  # mirrors config.bmc_trigger_threshold


def scores_with_n_covered(n: int, score_value: int = 1) -> dict[str, int]:
    """Return a scores dict where exactly n items are covered."""
    scores = {k: 0 for k in _BMC_KEYS}
    for key in _BMC_KEYS[:n]:
        scores[key] = score_value
    return scores


def patch_client(text: str):
    """Context manager that patches _client.messages.create to return text."""
    mock_resp = make_mock_response(text)
    return patch(
        "backend.agents.bmc_judge._client",
        messages=MagicMock(create=AsyncMock(return_value=mock_resp)),
    )


# ── 1. Happy path ──────────────────────────────────────────────────────────────

class TestEvaluateBMCHappyPath:
    async def test_returns_dict_with_required_keys(self, partial_session):
        payload = make_judge_payload(scores_with_n_covered(3))
        with patch_client(payload):
            result = await evaluate_bmc(partial_session)

        assert "scores" in result
        assert "covered_count" in result
        assert "trigger_canvas" in result
        assert "missing_items" in result
        assert "extracted" in result

    async def test_covered_count_matches_scores(self, partial_session):
        scores = scores_with_n_covered(5)
        payload = make_judge_payload(scores)
        with patch_client(payload):
            result = await evaluate_bmc(partial_session)
        assert result["covered_count"] == 5

    async def test_all_zeros_no_trigger(self, empty_session):
        payload = make_judge_payload(ALL_ZERO_SCORES)
        with patch_client(payload):
            result = await evaluate_bmc(empty_session)
        assert result["covered_count"] == 0
        assert result["trigger_canvas"] is False

    async def test_all_ones_triggers_canvas(self, rich_session):
        payload = make_judge_payload(ALL_ONE_SCORES)
        with patch_client(payload):
            result = await evaluate_bmc(rich_session)
        assert result["covered_count"] == 9
        assert result["trigger_canvas"] is True

    async def test_all_twos_triggers_canvas(self, rich_session):
        payload = make_judge_payload(ALL_TWO_SCORES)
        with patch_client(payload):
            result = await evaluate_bmc(rich_session)
        assert result["trigger_canvas"] is True


# ── 2. Score recomputation ─────────────────────────────────────────────────────

class TestScoreRecomputation:
    async def test_covered_count_recomputed_from_scores(self, empty_session):
        """covered_count from model output is ignored; we recompute from scores."""
        scores = scores_with_n_covered(4)
        # Deliberately send wrong covered_count from model
        raw = json.dumps({
            "scores": scores,
            "covered_count": 999,   # model lies
            "missing_items": [],
            "extracted": {k: None for k in _BMC_KEYS},
        })
        with patch_client(raw):
            result = await evaluate_bmc(empty_session)
        # Must be recomputed, not 999
        assert result["covered_count"] == 4

    async def test_score_of_zero_not_counted(self, empty_session):
        scores = {k: 0 for k in _BMC_KEYS}
        scores["customer_segments"] = 2  # one item with score 2
        payload = make_judge_payload(scores)
        with patch_client(payload):
            result = await evaluate_bmc(empty_session)
        assert result["covered_count"] == 1

    async def test_score_of_one_counts_as_covered(self, empty_session):
        scores = {k: 0 for k in _BMC_KEYS}
        scores["value_propositions"] = 1  # fuzzy mention counts
        payload = make_judge_payload(scores)
        with patch_client(payload):
            result = await evaluate_bmc(empty_session)
        assert result["covered_count"] == 1


# ── 3. Trigger threshold boundary ─────────────────────────────────────────────

class TestTriggerThreshold:
    @pytest.mark.parametrize("n_covered,expected_trigger", [
        (5, False),
        (6, False),
        (7, True),   # exactly at threshold
        (8, True),
        (9, True),
    ])
    async def test_threshold_boundary(self, empty_session, n_covered, expected_trigger):
        scores = scores_with_n_covered(n_covered)
        payload = make_judge_payload(scores)
        with patch_client(payload):
            result = await evaluate_bmc(empty_session)
        assert result["trigger_canvas"] is expected_trigger, (
            f"Expected trigger={expected_trigger} for {n_covered} covered items"
        )

    async def test_canvas_already_generated_does_not_affect_judge(self, rich_session):
        """Judge always evaluates; canvas_generated guard is in main.py, not here."""
        rich_session.canvas_generated = True
        payload = make_judge_payload(ALL_ONE_SCORES)
        with patch_client(payload):
            result = await evaluate_bmc(rich_session)
        # Judge still returns trigger_canvas=True; main.py decides whether to act
        assert result["trigger_canvas"] is True


# ── 4. Missing items ───────────────────────────────────────────────────────────

class TestMissingItems:
    async def test_all_missing_when_all_zero(self, empty_session):
        payload = make_judge_payload(ALL_ZERO_SCORES)
        with patch_client(payload):
            result = await evaluate_bmc(empty_session)
        assert len(result["missing_items"]) == 9

    async def test_missing_items_are_in_chinese(self, empty_session):
        payload = make_judge_payload(ALL_ZERO_SCORES)
        with patch_client(payload):
            result = await evaluate_bmc(empty_session)
        expected_labels = set(_MISSING_LABELS.values())
        for item in result["missing_items"]:
            assert item in expected_labels, f"'{item}' not a valid Chinese label"

    async def test_covered_items_absent_from_missing(self, empty_session):
        scores = {k: 0 for k in _BMC_KEYS}
        scores["customer_segments"] = 2
        scores["revenue_streams"] = 1
        payload = make_judge_payload(scores)
        with patch_client(payload):
            result = await evaluate_bmc(empty_session)
        assert "客户细分" not in result["missing_items"]
        assert "收入来源" not in result["missing_items"]
        assert len(result["missing_items"]) == 7

    async def test_no_missing_when_all_covered(self, rich_session):
        payload = make_judge_payload(ALL_TWO_SCORES)
        with patch_client(payload):
            result = await evaluate_bmc(rich_session)
        assert result["missing_items"] == []

    async def test_missing_items_derived_server_side_ignores_model_list(self, empty_session):
        """Server must derive missing_items from scores, not trust the model's list."""
        scores = scores_with_n_covered(7)
        raw = json.dumps({
            "scores": scores,
            "covered_count": 7,
            "missing_items": ["胡说八道的内容"],   # model provides garbage
            "extracted": {k: None for k in _BMC_KEYS},
        })
        with patch_client(raw):
            result = await evaluate_bmc(empty_session)
        # Server recomputes: 2 items are missing (last two in _BMC_KEYS)
        assert len(result["missing_items"]) == 2
        # And they should be valid Chinese labels, not the garbage string
        for item in result["missing_items"]:
            assert item in _MISSING_LABELS.values()


# ── 5. Session state mutation ──────────────────────────────────────────────────

class TestSessionStateMutation:
    async def test_extracted_info_written_to_session(self, empty_session):
        extracted = {
            "customer_segments": "B2B销售团队",
            "revenue_streams": "席位订阅$99/月",
            **{k: None for k in _BMC_KEYS if k not in ("customer_segments", "revenue_streams")},
        }
        payload = make_judge_payload(scores_with_n_covered(2), extracted=extracted)
        with patch_client(payload):
            await evaluate_bmc(empty_session)
        assert empty_session.bmc_info.customer_segments == "B2B销售团队"
        assert empty_session.bmc_info.revenue_streams == "席位订阅$99/月"

    async def test_null_extracted_does_not_overwrite_existing(self, partial_session):
        partial_session.bmc_info.customer_segments = "已有值"
        extracted = {k: None for k in _BMC_KEYS}
        payload = make_judge_payload(ALL_ZERO_SCORES, extracted=extracted)
        with patch_client(payload):
            await evaluate_bmc(partial_session)
        assert partial_session.bmc_info.customer_segments == "已有值"

    async def test_session_bmc_accumulates_across_calls(self, empty_session):
        # First call: sets customer_segments
        ext1 = {k: None for k in _BMC_KEYS}
        ext1["customer_segments"] = "销售团队"
        with patch_client(make_judge_payload(scores_with_n_covered(1), extracted=ext1)):
            await evaluate_bmc(empty_session)

        # Second call: adds value_propositions, doesn't clear customer_segments
        ext2 = {k: None for k in _BMC_KEYS}
        ext2["value_propositions"] = "提升效率"
        with patch_client(make_judge_payload(scores_with_n_covered(2), extracted=ext2)):
            await evaluate_bmc(empty_session)

        assert empty_session.bmc_info.customer_segments == "销售团队"
        assert empty_session.bmc_info.value_propositions == "提升效率"


# ── 6. Resilience / error handling ────────────────────────────────────────────

class TestResilience:
    async def test_invalid_json_returns_fallback(self, empty_session):
        with patch_client("这不是JSON"):
            result = await evaluate_bmc(empty_session)
        # Fallback: all zeros, no trigger
        assert result["covered_count"] == 0
        assert result["trigger_canvas"] is False
        assert "missing_items" in result

    async def test_truncated_json_returns_fallback(self, empty_session):
        with patch_client('{"scores": {"customer_segments": 1'):   # truncated
            result = await evaluate_bmc(empty_session)
        assert result["trigger_canvas"] is False

    async def test_markdown_wrapped_json_is_parsed(self, empty_session):
        """Model sometimes wraps output in ```json ... ``` despite instructions."""
        inner = make_judge_payload(scores_with_n_covered(7))
        wrapped = f"```json\n{inner}\n```"
        with patch_client(wrapped):
            result = await evaluate_bmc(empty_session)
        # Should parse correctly, not fall back
        assert result["covered_count"] == 7
        assert result["trigger_canvas"] is True

    async def test_plain_backtick_block_is_parsed(self, empty_session):
        inner = make_judge_payload(scores_with_n_covered(3))
        wrapped = f"```\n{inner}\n```"
        with patch_client(wrapped):
            result = await evaluate_bmc(empty_session)
        assert result["covered_count"] == 3

    async def test_api_called_with_conversation_history(self, partial_session):
        """Verify the conversation history is passed to the API."""
        payload = make_judge_payload(ALL_ZERO_SCORES)
        mock_resp = make_mock_response(payload)
        mock_create = AsyncMock(return_value=mock_resp)
        with patch(
            "backend.agents.bmc_judge._client",
            messages=MagicMock(create=mock_create),
        ):
            await evaluate_bmc(partial_session)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        # The user message content should include conversation history
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert partial_session.get_history_text()[:50] in user_content


# ── 7. Edge cases ──────────────────────────────────────────────────────────────

class TestEdgeCases:
    async def test_empty_conversation_still_calls_api(self, empty_session):
        payload = make_judge_payload(ALL_ZERO_SCORES)
        mock_resp = make_mock_response(payload)
        mock_create = AsyncMock(return_value=mock_resp)
        with patch(
            "backend.agents.bmc_judge._client",
            messages=MagicMock(create=mock_create),
        ):
            await evaluate_bmc(empty_session)
        mock_create.assert_called_once()

    async def test_scores_dict_contains_all_nine_keys(self, empty_session):
        payload = make_judge_payload(ALL_ONE_SCORES)
        with patch_client(payload):
            result = await evaluate_bmc(empty_session)
        assert set(result["scores"].keys()) == set(_BMC_KEYS)

    async def test_result_is_independent_per_session(self, empty_session, partial_session):
        """Two sessions evaluated separately should not share state."""
        payload_empty = make_judge_payload(ALL_ZERO_SCORES)
        payload_partial = make_judge_payload(scores_with_n_covered(5))

        with patch_client(payload_empty):
            result_empty = await evaluate_bmc(empty_session)
        with patch_client(payload_partial):
            result_partial = await evaluate_bmc(partial_session)

        assert result_empty["covered_count"] == 0
        assert result_partial["covered_count"] == 5
