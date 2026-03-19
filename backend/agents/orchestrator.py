"""
Main Orchestrator Agent — the core Design Thinking facilitator.

Key design decisions:
- Uses AsyncAnthropic + messages.stream() for true token-by-token streaming.
- Implements an agentic tool-use loop: stream → detect tool_use → execute tools
  → feed results back → continue streaming, until stop_reason == "end_turn".
- Session history is the single source of truth for messages; the user message
  is added by main.py BEFORE calling orchestrate(), so we never append it again.
"""

from typing import AsyncGenerator
import anthropic
from backend.config import config
from backend.models.session import Session, DTStage
from backend.tools.web_search import web_search, WEB_SEARCH_TOOL
from backend.tools.diagram import generate_diagram, DIAGRAM_TOOL

_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

# ── Stage-specific guidance ────────────────────────────────────────────────────

_STAGE_GUIDES: dict[DTStage, str] = {
    DTStage.EMPATHIZE: """【当前阶段：Empathize 共情 · 第1/5阶段】
目标：挖掘真实痛点和受影响人群
引导方向：
- "你注意到什么场景下人们在重复做低效的事？"
- "这个问题影响了哪些人？他们现在是怎么解决的？"
工具使用时机：
- 用户提到具体行业/市场 → web_search("该行业痛点 OR 用户需求 2025")
- 痛点轮廓清晰后 → generate_diagram(pain_point_map) 可视化""",

    DTStage.DEFINE: """【当前阶段：Define 定义 · 第2/5阶段】
目标：将痛点凝练为一句清晰的问题陈述
引导方向：
- 模板："[用户群体] 需要 [需求]，但 [障碍] 导致他们无法实现 [目标]"
- "这个问题的根本原因是什么？"
工具使用时机：
- 问题陈述成型后 → generate_diagram(pain_point_map) 帮用户确认理解""",

    DTStage.IDEATE: """【当前阶段：Ideate 构想 · 第3/5阶段】
目标：设计 AI Agent 解决方案，挖掘差异化
引导方向：
- "如果有个 AI Agent 7×24小时处理这件事，它需要能做什么？"
- "这个 Agent 的核心能力是什么？数据？推理？执行？"
- "现有竞品怎么做？你的差异化在哪里？"
工具使用时机：
- 提到竞品/行业 → web_search("竞品名 OR 类似产品 Agent AI")
- Agent能力清晰后 → generate_diagram(agent_solution) 展示方案架构""",

    DTStage.PROTOTYPE: """【当前阶段：Prototype 原型 · 第4/5阶段】
目标：构建商业模式框架，明确价值交付和收入路径
引导方向：
- "谁会为这个 Agent 服务付费？企业还是个人？付多少？"
- "你如何触达你的第一批用户？"
- "交付价值的方式：订阅、按次计费、还是分成？"
工具使用时机：
- 讨论定价 → web_search("类似SaaS产品定价 2025")
- 商业模式成型后 → generate_diagram(business_model) 展示框架""",

    DTStage.VALIDATE: """【当前阶段：Validate 验证 · 第5/5阶段】
目标：用数据验证市场可行性，明确护城河
引导方向：
- "这个市场有多大？TAM/SAM/SOM 估算？"
- "你凭什么能赢？护城河是什么？"
- "获客成本 (CAC) 和用户生命周期价值 (LTV) 比例合理吗？"
工具使用时机：
- 估算市场规模 → web_search("市场名 market size 2025 TAM")
- 分析完成后 → generate_diagram(business_model) 最终确认""",
}

_BASE_SYSTEM = """\
你是 TokenFounder，一个专注于帮助用户孵化 AI Agent 创业想法的智能顾问。
你的方法论基于 Design Thinking 五阶段，引导用户从模糊想法走向完整商业模式。

【你的角色】
- 像经验丰富的创业导师，用苏格拉底式提问引发用户深度思考
- 不直接给答案，而是通过问题帮用户自己发现洞察
- 保持聚焦：每次回复最多提 1-2 个引导问题，避免信息轰炸
- 语气：亲切、充满好奇心、对用户的想法真诚鼓励

【回复格式】
- 长度：150-300 字（不含图形代码块）
- 结构：① 简短回应用户 → ② 核心洞察或信息 → ③ 1-2 个引导问题
- 当模型决定生成图形，直接调用 generate_diagram 工具，不要在文字里描述图形

{stage_guide}

【当前状态】
- 对话轮次：{turn_count}
- 已识别商业信息：{bmc_summary}\
"""


# ── Public interface ───────────────────────────────────────────────────────────

async def orchestrate(session: Session) -> AsyncGenerator[str, None]:
    """
    Stream the orchestrator's response, handling the tool-use loop internally.

    Yields text chunks directly. Tool outputs are also yielded as formatted
    text so the frontend can render them inline (e.g. Mermaid diagrams).

    IMPORTANT: caller (main.py) must add the user message to session BEFORE
    calling this function. The history is the single source of truth.
    """
    system_prompt = _BASE_SYSTEM.format(
        stage_guide=_STAGE_GUIDES.get(session.current_stage, ""),
        turn_count=session.turn_count,
        bmc_summary=_format_bmc_summary(session),
    )

    # Build messages from session history (already includes the latest user msg)
    messages: list[dict] = session.get_history_for_api()

    # Agentic loop: stream → tool_use → continue until end_turn
    while True:
        collected_text, tool_calls = await _stream_once(
            system_prompt, messages, session
        )

        # Yield the text we collected during this stream pass
        for chunk in collected_text:
            yield chunk

        if not tool_calls:
            # stop_reason == "end_turn" — we're done
            break

        # Execute tools and yield their output inline
        tool_results = []
        for tc in tool_calls:
            result_text = await _execute_tool(tc["name"], tc["input"])
            yield result_text  # frontend renders Mermaid / search snippet
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc["id"],
                "content": result_text,
            })

        # Append assistant turn (with tool_use blocks) and tool results
        messages.append({"role": "assistant", "content": tc["assistant_content"]})
        messages.append({"role": "user", "content": tool_results})

    # Advance DT stage based on BMC coverage after full response
    _maybe_advance_stage(session)


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _stream_once(
    system: str,
    messages: list[dict],
    session: Session,
) -> tuple[list[str], list[dict]]:
    """
    Run one streaming call. Returns (text_chunks, tool_calls).
    text_chunks: list of text strings yielded during the stream.
    tool_calls:  list of {id, name, input, assistant_content} dicts if any tools
                 were called; empty list if stop_reason == "end_turn".
    """
    text_chunks: list[str] = []
    tool_calls: list[dict] = []

    async with _client.messages.stream(
        model=config.model_main,
        max_tokens=1500,
        system=system,
        tools=[WEB_SEARCH_TOOL, DIAGRAM_TOOL],
        messages=messages,
    ) as stream:
        # True token-by-token streaming
        async for text in stream.text_stream:
            text_chunks.append(text)

        # After stream completes, inspect the final message
        final = await stream.get_final_message()

    if final.stop_reason == "tool_use":
        # Collect tool_use blocks; also preserve the full content list so we
        # can append it back as the assistant message in the next loop iteration.
        assistant_content = final.content  # list[ContentBlock]
        for block in assistant_content:
            if block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                    "assistant_content": assistant_content,  # shared ref, fine
                })

    return text_chunks, tool_calls


async def _execute_tool(name: str, input_data: dict) -> str:
    if name == "web_search":
        return await web_search(input_data.get("query", ""))
    if name == "generate_diagram":
        return generate_diagram(
            input_data.get("diagram_type", ""),
            input_data.get("data", {}),
        )
    return f"[未知工具: {name}]"


def _maybe_advance_stage(session: Session) -> None:
    """Advance DT stage based on BMC coverage accumulated so far."""
    bmc = session.bmc_info
    stage = session.current_stage

    # Advancement thresholds (BMC items covered)
    transitions = [
        (DTStage.EMPATHIZE, DTStage.DEFINE, lambda: bool(bmc.customer_segments and bmc.value_propositions)),
        (DTStage.DEFINE, DTStage.IDEATE, lambda: bmc.covered_count >= 2),
        (DTStage.IDEATE, DTStage.PROTOTYPE, lambda: bmc.covered_count >= 4),
        (DTStage.PROTOTYPE, DTStage.VALIDATE, lambda: bmc.covered_count >= 6),
    ]
    for from_stage, to_stage, condition in transitions:
        if stage == from_stage and condition():
            session.current_stage = to_stage
            break


def _format_bmc_summary(session: Session) -> str:
    bmc = session.bmc_info
    parts = []
    if bmc.customer_segments:
        parts.append(f"客户: {bmc.customer_segments[:40]}")
    if bmc.value_propositions:
        parts.append(f"价值: {bmc.value_propositions[:40]}")
    if bmc.revenue_streams:
        parts.append(f"收入: {bmc.revenue_streams[:40]}")
    return "、".join(parts) if parts else "尚未提取"
