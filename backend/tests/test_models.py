"""
Unit tests for data models — no mocking needed, pure logic.

Covers:
- BMCInfo.covered_count property
- BMCInfo.update_from_judge()
- Session.add_message() / get_history_text() / get_history_for_api()
- BusinessCanvas.to_dict()
"""

import pytest
from backend.models.session import Session, BMCInfo, DTStage
from backend.models.bmc import BusinessCanvas, CanvasItem


# ── BMCInfo ────────────────────────────────────────────────────────────────────

class TestBMCInfoCoveredCount:
    def test_empty_is_zero(self):
        assert BMCInfo().covered_count == 0

    def test_all_filled_is_nine(self):
        bmc = BMCInfo(
            customer_segments="企业销售团队",
            value_propositions="回复率提升3倍",
            channels="Salesforce AppExchange",
            customer_relationships="CSM服务",
            revenue_streams="席位订阅$99/月",
            key_resources="训练数据集",
            key_activities="模型训练",
            key_partnerships="Salesforce集成",
            cost_structure="API调用成本",
        )
        assert bmc.covered_count == 9

    def test_partial_count(self):
        bmc = BMCInfo(
            customer_segments="销售团队",
            value_propositions="提升效率",
        )
        assert bmc.covered_count == 2

    def test_empty_string_counts_as_covered(self):
        # Empty string is falsy in Python but is not None — still "set"
        bmc = BMCInfo(customer_segments="")
        # covered_count checks `is not None`, so empty string IS counted
        assert bmc.covered_count == 1

    def test_none_fields_not_counted(self):
        bmc = BMCInfo(customer_segments=None, value_propositions="价值")
        assert bmc.covered_count == 1


class TestBMCInfoUpdateFromJudge:
    def test_updates_present_fields(self):
        bmc = BMCInfo()
        bmc.update_from_judge({
            "customer_segments": "B2B销售团队",
            "revenue_streams": "席位订阅",
        })
        assert bmc.customer_segments == "B2B销售团队"
        assert bmc.revenue_streams == "席位订阅"

    def test_null_values_do_not_overwrite(self):
        bmc = BMCInfo(customer_segments="已有值")
        bmc.update_from_judge({"customer_segments": None})
        # None is falsy → skipped by `if value and hasattr(self, key)`
        assert bmc.customer_segments == "已有值"

    def test_unknown_keys_are_ignored(self):
        bmc = BMCInfo()
        bmc.update_from_judge({"nonexistent_field": "value"})
        # Should not raise, unknown key silently ignored
        assert bmc.covered_count == 0

    def test_does_not_overwrite_with_falsy_empty_string(self):
        bmc = BMCInfo(customer_segments="原始值")
        bmc.update_from_judge({"customer_segments": ""})
        assert bmc.customer_segments == "原始值"

    def test_overwrites_when_new_value_is_truthy(self):
        bmc = BMCInfo(customer_segments="旧值")
        bmc.update_from_judge({"customer_segments": "新值"})
        assert bmc.customer_segments == "新值"

    def test_all_nine_keys_updated(self):
        bmc = BMCInfo()
        extracted = {
            "customer_segments": "cs",
            "value_propositions": "vp",
            "channels": "ch",
            "customer_relationships": "cr",
            "revenue_streams": "rs",
            "key_resources": "kr",
            "key_activities": "ka",
            "key_partnerships": "kp",
            "cost_structure": "co",
        }
        bmc.update_from_judge(extracted)
        assert bmc.covered_count == 9


# ── Session ────────────────────────────────────────────────────────────────────

class TestSessionMessages:
    def test_add_user_message_increments_turn_count(self):
        s = Session()
        assert s.turn_count == 0
        s.add_message("user", "你好")
        assert s.turn_count == 1
        s.add_message("user", "再说一遍")
        assert s.turn_count == 2

    def test_add_assistant_message_does_not_increment_turn_count(self):
        s = Session()
        s.add_message("assistant", "你好！")
        assert s.turn_count == 0

    def test_get_history_text_format(self):
        s = Session()
        s.add_message("user", "我有个想法")
        s.add_message("assistant", "说来听听")
        text = s.get_history_text()
        assert "USER: 我有个想法" in text
        assert "ASSISTANT: 说来听听" in text

    def test_get_history_for_api_structure(self):
        s = Session()
        s.add_message("user", "测试")
        s.add_message("assistant", "回复")
        history = s.get_history_for_api()
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "测试"}
        assert history[1] == {"role": "assistant", "content": "回复"}

    def test_empty_history(self):
        s = Session()
        assert s.get_history_text() == ""
        assert s.get_history_for_api() == []

    def test_initial_stage_is_empathize(self):
        s = Session()
        assert s.current_stage == DTStage.EMPATHIZE

    def test_canvas_not_generated_initially(self):
        s = Session()
        assert s.canvas_generated is False


# ── BusinessCanvas ─────────────────────────────────────────────────────────────

class TestBusinessCanvasToDict:
    def _make_canvas(self) -> BusinessCanvas:
        return BusinessCanvas(
            project_name="SalesMind AI",
            tagline="个性化销售邮件引擎",
            customer_segments=CanvasItem(["B2B销售团队"], is_inferred=False),
            value_propositions=CanvasItem(["回复率提升3倍"], is_inferred=False),
            channels=CanvasItem(["Salesforce"], is_inferred=True),
            customer_relationships=CanvasItem(["CSM服务"], is_inferred=False),
            revenue_streams=CanvasItem(["$99/月/席位"], is_inferred=False),
            key_resources=CanvasItem(["训练数据"], is_inferred=False),
            key_activities=CanvasItem(["模型训练"], is_inferred=False),
            key_partnerships=CanvasItem(["数据合规机构"], is_inferred=True),
            cost_structure=CanvasItem(["API调用成本"], is_inferred=False),
            next_steps=["招募Beta用户"],
        )

    def test_top_level_keys(self):
        d = self._make_canvas().to_dict()
        assert set(d.keys()) == {"project_name", "tagline", "canvas", "next_steps"}

    def test_project_name_and_tagline(self):
        d = self._make_canvas().to_dict()
        assert d["project_name"] == "SalesMind AI"
        assert d["tagline"] == "个性化销售邮件引擎"

    def test_canvas_has_nine_sections(self):
        d = self._make_canvas().to_dict()
        assert len(d["canvas"]) == 9

    def test_is_inferred_flag_preserved(self):
        d = self._make_canvas().to_dict()
        assert d["canvas"]["channels"]["is_inferred"] is True
        assert d["canvas"]["customer_segments"]["is_inferred"] is False

    def test_content_lists_preserved(self):
        d = self._make_canvas().to_dict()
        assert d["canvas"]["customer_segments"]["content"] == ["B2B销售团队"]
        assert d["canvas"]["revenue_streams"]["content"] == ["$99/月/席位"]

    def test_next_steps_preserved(self):
        d = self._make_canvas().to_dict()
        assert d["next_steps"] == ["招募Beta用户"]

    def test_empty_canvas_item(self):
        canvas = BusinessCanvas(project_name="Test", tagline="Test tagline")
        d = canvas.to_dict()
        # Default CanvasItem has empty content list
        assert d["canvas"]["customer_segments"]["content"] == []
        assert d["canvas"]["customer_segments"]["is_inferred"] is False
