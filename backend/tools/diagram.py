"""
Diagram Generator Tool — produces Mermaid.js code from structured data.
No LLM call needed; pure template-based generation.
"""

from enum import Enum


class DiagramType(str, Enum):
    PAIN_POINT_MAP = "pain_point_map"
    AGENT_SOLUTION = "agent_solution"
    BUSINESS_MODEL = "business_model"
    DT_PROGRESS = "dt_progress"


def generate_diagram(diagram_type: str, data: dict) -> str:
    """Return a Mermaid code block string ready for frontend rendering."""
    generators = {
        DiagramType.PAIN_POINT_MAP: _pain_point_map,
        DiagramType.AGENT_SOLUTION: _agent_solution,
        DiagramType.BUSINESS_MODEL: _business_model,
        DiagramType.DT_PROGRESS: _dt_progress,
    }
    fn = generators.get(DiagramType(diagram_type))
    if not fn:
        return f"[不支持的图形类型: {diagram_type}]"

    mermaid_code = fn(data)
    return f"```mermaid\n{mermaid_code}\n```"


def _pain_point_map(data: dict) -> str:
    pain = data.get("pain_point", "核心痛点")
    segments = data.get("segments", ["用户群体A", "用户群体B"])
    solutions = data.get("current_solutions", ["现有方案A", "现有方案B"])
    gaps = data.get("gaps", ["缺陷A", "缺陷B"])

    lines = ["graph TD", f'    P["😣 {pain}"]']
    for i, seg in enumerate(segments[:3]):
        sid = f"U{i}"
        lines.append(f'    P --> {sid}["👤 {seg}"]')
        sol = solutions[i] if i < len(solutions) else "无明确方案"
        gap = gaps[i] if i < len(gaps) else "效率低下"
        lines.append(f'    {sid} --> S{i}["现有方案\\n{sol}"]')
        lines.append(f'    S{i} --> G{i}["❌ {gap}"]')
    return "\n".join(lines)


def _agent_solution(data: dict) -> str:
    input_desc = data.get("input", "用户请求")
    agent_name = data.get("agent_name", "AI Agent")
    capabilities = data.get("capabilities", ["能力1", "能力2", "能力3"])
    output_desc = data.get("output", "结果输出")
    value = data.get("value", "核心价值")

    lines = [
        "graph LR",
        f'    I["📥 {input_desc}"] --> A["🤖 {agent_name}"]',
    ]
    for i, cap in enumerate(capabilities[:4]):
        lines.append(f'    A --> T{i}["⚙️ {cap}"]')
        lines.append(f'    T{i} --> O')
    lines.append(f'    O["📤 {output_desc}"] --> V["💎 {value}"]')
    return "\n".join(lines)


def _business_model(data: dict) -> str:
    customer = data.get("customer", "目标客户")
    revenue = data.get("revenue", "收入模式")
    value_prop = data.get("value_prop", "价值主张")
    key_activity = data.get("key_activity", "关键活动")
    key_resource = data.get("key_resource", "核心资源")
    partner = data.get("partner", "合作伙伴")
    cost = data.get("cost", "主要成本")

    return f"""graph TD
    CS["👥 {customer}"] -->|付费| RS["💰 {revenue}"]
    VP["✨ {value_prop}"] --> CS
    KA["⚙️ {key_activity}"] --> VP
    KR["🔑 {key_resource}"] --> KA
    KP["🤝 {partner}"] --> KA
    CO["💸 {cost}"] --> KA"""


def _dt_progress(data: dict) -> str:
    scores = data.get("scores", {})

    def score_to_emoji(stage: str) -> str:
        s = scores.get(stage, 0)
        return {0: "1", 1: "3", 2: "5"}.get(s, "1")

    return f"""journey
    title Agent创业想法 - Design Thinking进程
    section Empathize
      挖掘痛点: {score_to_emoji("empathize")}: 你
    section Define
      定义问题: {score_to_emoji("define")}: 你
    section Ideate
      构想方案: {score_to_emoji("ideate")}: 你
    section Prototype
      商业原型: {score_to_emoji("prototype")}: 你
    section Validate
      市场验证: {score_to_emoji("validate")}: 你"""


# Tool definition for Claude's tool_use API
DIAGRAM_TOOL = {
    "name": "generate_diagram",
    "description": "生成Mermaid图形来可视化展示痛点地图、Agent架构、商业模式等。在解释复杂概念或帮用户梳理思路时使用。",
    "input_schema": {
        "type": "object",
        "properties": {
            "diagram_type": {
                "type": "string",
                "enum": ["pain_point_map", "agent_solution", "business_model", "dt_progress"],
                "description": "图形类型",
            },
            "data": {
                "type": "object",
                "description": "图形数据，根据diagram_type填入对应字段",
            },
        },
        "required": ["diagram_type", "data"],
    },
}
