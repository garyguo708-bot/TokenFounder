"""
Topic Guardrail Agent — fast topic relevance check using Haiku.
Returns whether the user message is relevant to Agent startup ideation.
"""

import json
import anthropic
from backend.config import config

# AsyncAnthropic: non-blocking I/O, safe for FastAPI async handlers
_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

GUARDRAIL_SYSTEM = """你是一个主题守护模块。你的唯一任务是判断用户消息是否与"Agent/AI创业、商业模式、创业想法"相关。

【判断标准】
- 相关：AI/Agent应用、创业方向、商业问题、市场分析、用户痛点、产品设计、竞品分析
- 允许的发散：相关技术探讨、行业背景知识、创业经验分享
- 不相关：天气、娱乐、私人生活、政治、其他无关话题

【输出格式】严格JSON，不要任何额外文字：
{
  "is_relevant": true,
  "confidence": 0.95,
  "redirect_message": null
}"""


async def check_topic(user_message: str) -> dict:
    """
    Returns:
        {
            "is_relevant": bool,
            "confidence": float,
            "redirect_message": str | None
        }
    """
    response = await _client.messages.create(
        model=config.model_fast,
        max_tokens=200,
        system=GUARDRAIL_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code block if model wraps output
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fail open: treat as relevant so we never block valid ideas
        return {"is_relevant": True, "confidence": 0.5, "redirect_message": None}
