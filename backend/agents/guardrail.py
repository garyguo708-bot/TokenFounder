"""
Topic Guardrail Agent — fast topic relevance check using Haiku.
Returns whether the user message is relevant to Agent startup ideation.
"""

import json
import anthropic
from backend.config import config

_client = anthropic.Anthropic(api_key=config.anthropic_api_key)

GUARDRAIL_SYSTEM = """你是一个主题守护模块。你的唯一任务是判断用户消息是否与"Agent/AI创业、商业模式、创业想法"相关。

【判断标准】
- 相关：AI/Agent应用、创业方向、商业问题、市场分析、用户痛点、产品设计、竞品分析
- 允许的发散：相关技术探讨、行业背景知识、创业经验分享
- 不相关：天气、娱乐、私人生活、政治、其他无关话题

【输出格式】严格JSON，不要任何额外文字：
{
  "is_relevant": true/false,
  "confidence": 0.0-1.0,
  "redirect_message": "（仅当is_relevant=false时填写，温和友好地将用户引回Agent创业主题，15-30字）"
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
    response = _client.messages.create(
        model=config.model_fast,
        max_tokens=200,
        system=GUARDRAIL_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat as relevant if parsing fails
        result = {"is_relevant": True, "confidence": 0.5, "redirect_message": None}

    return result
