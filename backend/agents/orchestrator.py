"""
Main Orchestrator Agent — the core Design Thinking facilitator.
Uses Sonnet with tool_use for web search and diagram generation.
Streams responses via SSE.
"""

from typing import AsyncGenerator
import anthropic
from backend.config import config
from backend.models.session import Session, DTStage
from backend.tools.web_search import web_search, WEB_SEARCH_TOOL
from backend.tools.diagram import generate_diagram, DIAGRAM_TOOL

_client = anthropic.Anthropic(api_key=config.anthropic_api_key)

# Stage-specific guidance injected into system prompt
_STAGE_GUIDES = {
    DTStage.EMPATHIZE: """【当前阶段：Empathize 共情】
目标：挖掘真实痛点和受影响人群
引导方向：
- "你注意到什么场景下人们在重复做低效的事？"
- "这个问题影响了哪些人？他们现在是怎么解决的？"
工具：当用户提到具体行业时，用web_search搜索行业痛点；用generate_diagram(pain_point_map)可视化痛点""",

    DTStage.DEFINE: """【当前阶段：Define 定义】
目标：将痛点凝练为清晰的问题陈述
引导方向：
- "用一句话描述：[用户群体]需要[需求]，但[障碍]导致他们无法实现[目标]"
- "这个问题的根本原因是什么？"
工具：用generate_diagram(pain_point_map)帮用户可视化问题定义""",

    DTStage.IDEATE: """【当前阶段：Ideate 构想】
目标：设计 AI Agent 解决方案
引导方向：
- "如果有个 AI Agent 7×24小时处理这件事，它需要能做什么？"
- "这个 Agent 的核心能力是什么？数据？推理？执行？"
工具：用web_search搜索竞品；用generate_diagram(agent_solution)展示方案架构""",

    DTStage.PROTOTYPE: """【当前阶段：Prototype 原型】
目标：构建商业模式框架
引导方向：
- "谁会为这个 Agent 服务付费？付多少？"
- "你如何触达你的第一批用户？"
工具：用generate_diagram(business_model)展示商业模式；用web_search搜索定价参考""",

    DTStage.VALIDATE: """【当前阶段：Validate 验证】
目标：验证市场可行性
引导方向：
- "这个市场有多大？你能找到数据支撑吗？"
- "你凭什么能赢？护城河是什么？"
工具：用web_search搜索市场规模数据""",
}

_BASE_SYSTEM = """你是 TokenFounder，一个专注于帮助用户孵化 AI Agent 创业想法的智能顾问。
你的方法论基于 Design Thinking 五阶段。

【你的角色】
- 像经验丰富的创业导师，用苏格拉底式提问引发用户深度思考
- 不直接给答案，而是通过问题帮用户自己发现洞察
- 保持聚焦：每次回复最多提1-2个引导问题
- 语气：亲切、充满好奇心、鼓励探索

【回复格式】
- 长度：150-300字（不含图形代码块）
- 结构：简短回应用户→核心洞察或信息→1-2个引导问题
- Mermaid图形用```mermaid代码块包裹

{stage_guide}

【当前状态】
- 对话轮次：{turn_count}
- 已识别商业信息：{bmc_summary}"""


async def orchestrate(
    session: Session,
    user_message: str,
) -> AsyncGenerator[str, None]:
    """
    Stream the orchestrator's response token by token.
    Yields SSE-compatible text chunks.
    """
    stage_guide = _STAGE_GUIDES.get(session.current_stage, "")
    bmc_summary = _format_bmc_summary(session)

    system_prompt = _BASE_SYSTEM.format(
        stage_guide=stage_guide,
        turn_count=session.turn_count,
        bmc_summary=bmc_summary,
    )

    messages = session.get_history_for_api()
    messages.append({"role": "user", "content": user_message})

    # First LLM call — may trigger tool use
    response = _client.messages.create(
        model=config.model_main,
        max_tokens=1500,
        system=system_prompt,
        tools=[WEB_SEARCH_TOOL, DIAGRAM_TOOL],
        messages=messages,
    )

    # Agentic tool-use loop
    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_result = await _execute_tool(block.name, block.input)
                yield f"\n\n{tool_result}\n\n"
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_result,
                })

        # Continue with tool results
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = _client.messages.create(
            model=config.model_main,
            max_tokens=1500,
            system=system_prompt,
            tools=[WEB_SEARCH_TOOL, DIAGRAM_TOOL],
            messages=messages,
        )

    # Yield final text response
    for block in response.content:
        if hasattr(block, "text"):
            yield block.text

    # Update DT stage based on conversation progress
    _maybe_advance_stage(session, response)


async def _execute_tool(name: str, input_data: dict) -> str:
    if name == "web_search":
        return await web_search(input_data.get("query", ""))
    elif name == "generate_diagram":
        return generate_diagram(
            input_data.get("diagram_type", ""),
            input_data.get("data", {}),
        )
    return f"[未知工具: {name}]"


def _maybe_advance_stage(session: Session, response) -> None:
    """Heuristic stage advancement based on BMC coverage."""
    bmc = session.bmc_info
    stage = session.current_stage

    if stage == DTStage.EMPATHIZE and bmc.customer_segments and bmc.value_propositions:
        session.current_stage = DTStage.DEFINE
    elif stage == DTStage.DEFINE and bmc.covered_count >= 2:
        session.current_stage = DTStage.IDEATE
    elif stage == DTStage.IDEATE and bmc.covered_count >= 4:
        session.current_stage = DTStage.PROTOTYPE
    elif stage == DTStage.PROTOTYPE and bmc.covered_count >= 6:
        session.current_stage = DTStage.VALIDATE


def _format_bmc_summary(session: Session) -> str:
    bmc = session.bmc_info
    items = []
    if bmc.customer_segments:
        items.append(f"客户: {bmc.customer_segments[:50]}")
    if bmc.value_propositions:
        items.append(f"价值: {bmc.value_propositions[:50]}")
    if bmc.revenue_streams:
        items.append(f"收入: {bmc.revenue_streams[:50]}")
    return "、".join(items) if items else "尚未提取"
