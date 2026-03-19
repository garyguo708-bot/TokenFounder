"""
Business Canvas Generator — produces the final Business Model Canvas.
Triggered only when BMC Judge confirms threshold is met.
"""

import json
import re
import anthropic
from backend.config import config
from backend.models.session import Session
from backend.models.bmc import BusinessCanvas, CanvasItem

_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

CANVAS_SYSTEM = """你是商业画布生成专家。基于对话中提取的信息，生成一份完整的 AI Agent 创业项目商业画布。

【要求】
- 对已有信息进行精炼和专业化表达
- 对信息不足的部分，基于上下文做合理补全，并将该项的 is_inferred 设为 true
- 语言简洁有力，每项3-5个要点，每个要点15字以内
- 体现 AI Agent 产品的独特性（自动化、规模化、持续学习等）

【输出格式】严格JSON，不要任何额外文字或代码块：
{
  "project_name": "项目名称（简洁有力，4-8字）",
  "tagline": "一句话描述项目价值（20字以内）",
  "canvas": {
    "customer_segments": {"content": ["要点1", "要点2", "要点3"], "is_inferred": false},
    "value_propositions": {"content": ["要点1", "要点2", "要点3"], "is_inferred": false},
    "channels": {"content": ["要点1", "要点2"], "is_inferred": false},
    "customer_relationships": {"content": ["要点1", "要点2"], "is_inferred": false},
    "revenue_streams": {"content": ["要点1", "要点2"], "is_inferred": false},
    "key_resources": {"content": ["要点1", "要点2"], "is_inferred": false},
    "key_activities": {"content": ["要点1", "要点2"], "is_inferred": false},
    "key_partnerships": {"content": ["要点1", "要点2"], "is_inferred": true},
    "cost_structure": {"content": ["要点1", "要点2"], "is_inferred": false}
  },
  "next_steps": ["建议的下一步行动1", "建议2", "建议3"]
}"""


async def generate_canvas(session: Session, judge_result: dict) -> BusinessCanvas:
    """Generate a complete Business Model Canvas from session data."""
    history_summary = session.get_history_text()[-3000:]

    prompt = (
        "根据以下对话历史和已提取信息，生成完整的商业画布JSON：\n\n"
        f"【对话历史】\n{history_summary}\n\n"
        f"【已提取的商业信息】\n"
        f"{json.dumps(judge_result.get('extracted', {}), ensure_ascii=False, indent=2)}\n\n"
        "请直接输出JSON，不要任何额外说明："
    )

    response = await _client.messages.create(
        model=config.model_main,
        max_tokens=2000,
        system=CANVAS_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code block if model adds one despite instructions
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    canvas_data = data.get("canvas", {})

    def parse_item(key: str) -> CanvasItem:
        item = canvas_data.get(key, {})
        return CanvasItem(
            content=item.get("content", []),
            is_inferred=item.get("is_inferred", False),
        )

    return BusinessCanvas(
        project_name=data.get("project_name", "未命名项目"),
        tagline=data.get("tagline", ""),
        customer_segments=parse_item("customer_segments"),
        value_propositions=parse_item("value_propositions"),
        channels=parse_item("channels"),
        customer_relationships=parse_item("customer_relationships"),
        revenue_streams=parse_item("revenue_streams"),
        key_resources=parse_item("key_resources"),
        key_activities=parse_item("key_activities"),
        key_partnerships=parse_item("key_partnerships"),
        cost_structure=parse_item("cost_structure"),
        next_steps=data.get("next_steps", []),
    )
