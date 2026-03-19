"""
BMC Judge — evaluates Business Model Canvas completeness from conversation history.
Uses Haiku for cost efficiency; called in parallel after each assistant reply.
"""

import json
import anthropic
from backend.config import config
from backend.models.session import Session

_client = anthropic.Anthropic(api_key=config.anthropic_api_key)

JUDGE_SYSTEM = """你是商业画布信息提取器。分析对话历史，提取用户已确认的商业模式信息。

【商业画布九要素评分标准】
每项评分：0=未提及，1=模糊提及，2=清晰描述

1. customer_segments（客户细分）：具体的目标用户群体
2. value_propositions（价值主张）：为客户解决什么问题/提供什么价值
3. channels（渠道通路）：如何触达客户
4. customer_relationships（客户关系）：获客、留存、增长方式
5. revenue_streams（收入来源）：如何赚钱，定价模型
6. key_resources（核心资源）：核心数据、技术、人才
7. key_activities（关键业务）：核心业务活动
8. key_partnerships（重要伙伴）：关键合作方
9. cost_structure（成本结构）：主要成本构成

【满足阈值】单项>=1分计为"已覆盖"，已覆盖项目数>=7即触发画布生成

【输出格式】严格JSON：
{
  "scores": {
    "customer_segments": 0,
    "value_propositions": 0,
    "channels": 0,
    "customer_relationships": 0,
    "revenue_streams": 0,
    "key_resources": 0,
    "key_activities": 0,
    "key_partnerships": 0,
    "cost_structure": 0
  },
  "covered_count": 0,
  "trigger_canvas": false,
  "missing_items": [],
  "extracted": {
    "customer_segments": null,
    "value_propositions": null,
    "channels": null,
    "customer_relationships": null,
    "revenue_streams": null,
    "key_resources": null,
    "key_activities": null,
    "key_partnerships": null,
    "cost_structure": null
  }
}"""


async def evaluate_bmc(session: Session) -> dict:
    """
    Evaluate BMC completeness from session conversation history.

    Returns judge result dict with scores, covered_count, trigger_canvas, etc.
    """
    history_text = session.get_history_text()

    response = _client.messages.create(
        model=config.model_fast,
        max_tokens=1000,
        system=JUDGE_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"请分析以下对话历史，提取商业画布信息：\n\n{history_text}"
        }],
    )

    raw = response.content[0].text.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "scores": {k: 0 for k in [
                "customer_segments", "value_propositions", "channels",
                "customer_relationships", "revenue_streams", "key_resources",
                "key_activities", "key_partnerships", "cost_structure"
            ]},
            "covered_count": 0,
            "trigger_canvas": False,
            "missing_items": ["解析失败"],
            "extracted": {},
        }

    # Override trigger based on config threshold
    result["trigger_canvas"] = result.get("covered_count", 0) >= config.bmc_trigger_threshold

    # Update session BMC info
    session.bmc_info.update_from_judge(result.get("extracted", {}))

    return result
