"""
Shared fixtures for TokenFounder test suite.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.models.session import Session, BMCInfo
from backend.models.bmc import BusinessCanvas, CanvasItem


# ── Session fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def empty_session() -> Session:
    """Fresh session with no conversation history."""
    return Session(session_id="test-empty")


@pytest.fixture
def partial_session() -> Session:
    """Session with a few conversation turns — covers ~3 BMC items."""
    s = Session(session_id="test-partial")
    s.add_message("user", "我想做一个帮助销售人员写个性化跟进邮件的AI Agent")
    s.add_message("assistant", "很有意思！销售跟进邮件这个场景，现在的销售人员是怎么处理的？")
    s.add_message("user", "主要靠手动复制粘贴模板，根本没法根据客户情况定制，回复率很低")
    s.add_message("assistant", "问题清晰了。你觉得什么样的用户最需要这个？")
    s.add_message("user", "主要是中大型企业的B2B销售，他们每天要跟进几十个客户")
    s.add_message("assistant", "那收费模式你有没有想过？")
    s.add_message("user", "按席位订阅，每个销售账号每月收费")
    return s


@pytest.fixture
def rich_session() -> Session:
    """Session with full conversation covering all 9 BMC items."""
    s = Session(session_id="test-rich")
    turns = [
        ("user", "我想做一个帮助B2B销售写个性化跟进邮件的AI Agent"),
        ("assistant", "很好！目标用户是谁？"),
        ("user", "中大型企业的销售团队，每人管几十个客户，手动写邮件效率太低"),
        ("assistant", "价值主张是什么？"),
        ("user", "AI根据CRM数据和客户行为自动生成个性化邮件，回复率提升3倍"),
        ("assistant", "怎么触达用户？"),
        ("user", "通过Salesforce AppExchange和LinkedIn广告，直接对接销售总监"),
        ("assistant", "客户关系如何维护？"),
        ("user", "提供CSM一对一服务，月度业务回顾，用数据证明ROI"),
        ("assistant", "收入模式？"),
        ("user", "按席位订阅，每席$99/月，企业版$299/月含高级分析"),
        ("assistant", "核心资源？"),
        ("user", "大量销售邮件训练数据，微调的行业专属模型，CRM集成能力"),
        ("assistant", "关键业务活动？"),
        ("user", "模型持续训练，CRM集成开发，客户成功运营"),
        ("assistant", "合作伙伴？"),
        ("user", "Salesforce、HubSpot集成，数据合规审计机构"),
        ("assistant", "成本结构？"),
        ("user", "API调用成本，工程团队，云服务器，CSM团队"),
    ]
    for role, content in turns:
        s.add_message(role, content)
    return s


# ── Mock API response helpers ──────────────────────────────────────────────────

def make_mock_response(text: str) -> MagicMock:
    """Build a mock Anthropic API response with a single text content block."""
    mock_content = MagicMock()
    mock_content.text = text
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


def make_judge_payload(
    scores: dict[str, int],
    extracted: dict[str, str | None] | None = None,
) -> str:
    """Build the JSON string a BMC Judge model would return."""
    bmc_keys = [
        "customer_segments", "value_propositions", "channels",
        "customer_relationships", "revenue_streams", "key_resources",
        "key_activities", "key_partnerships", "cost_structure",
    ]
    if extracted is None:
        extracted = {k: None for k in bmc_keys}

    covered = sum(1 for k in bmc_keys if scores.get(k, 0) >= 1)
    missing_labels = {
        "customer_segments": "客户细分",
        "value_propositions": "价值主张",
        "channels": "渠道通路",
        "customer_relationships": "客户关系",
        "revenue_streams": "收入来源",
        "key_resources": "核心资源",
        "key_activities": "关键业务",
        "key_partnerships": "重要伙伴",
        "cost_structure": "成本结构",
    }
    missing = [missing_labels[k] for k in bmc_keys if scores.get(k, 0) == 0]
    return json.dumps({
        "scores": scores,
        "covered_count": covered,
        "missing_items": missing,
        "extracted": extracted,
    }, ensure_ascii=False)


def make_canvas_payload(overrides: dict | None = None) -> str:
    """Build the JSON string a Canvas Generator model would return."""
    base = {
        "project_name": "SalesMind AI",
        "tagline": "让每封销售邮件都像手写一样个性化",
        "canvas": {
            "customer_segments": {
                "content": ["中大型企业B2B销售团队", "每人管理50+客户的AE"],
                "is_inferred": False,
            },
            "value_propositions": {
                "content": ["AI生成个性化邮件，回复率提升3倍", "节省80%邮件撰写时间"],
                "is_inferred": False,
            },
            "channels": {
                "content": ["Salesforce AppExchange", "LinkedIn精准广告"],
                "is_inferred": False,
            },
            "customer_relationships": {
                "content": ["CSM一对一服务", "月度ROI业务回顾"],
                "is_inferred": False,
            },
            "revenue_streams": {
                "content": ["席位订阅$99/月", "企业版$299/月"],
                "is_inferred": False,
            },
            "key_resources": {
                "content": ["销售邮件训练数据集", "行业专属微调模型"],
                "is_inferred": False,
            },
            "key_activities": {
                "content": ["模型持续训练", "CRM集成开发"],
                "is_inferred": False,
            },
            "key_partnerships": {
                "content": ["Salesforce/HubSpot集成", "数据合规审计机构"],
                "is_inferred": True,
            },
            "cost_structure": {
                "content": ["LLM API调用成本", "工程与CSM团队薪资"],
                "is_inferred": False,
            },
        },
        "next_steps": [
            "招募10名Beta用户验证回复率提升假设",
            "开发Salesforce插件MVP",
            "完成数据合规评估",
        ],
    }
    if overrides:
        base.update(overrides)
    return json.dumps(base, ensure_ascii=False)
