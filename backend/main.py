"""
TokenFounder FastAPI Backend
SSE streaming endpoint for the Agent startup ideation chat.

SSE event schema (each line: "data: <JSON>\n\n"):
  { "type": "text",         "data": { "chunk": "..." } }
  { "type": "redirect",     "data": { "message": "..." } }
  { "type": "bmc_progress", "data": { "covered_count": N, "total": 9,
                                       "missing_items": [...],
                                       "current_stage": "..." } }
  { "type": "canvas_start", "data": { "message": "..." } }
  { "type": "canvas_complete", "data": { ...BusinessCanvas dict... } }
  { "type": "error",        "data": { "message": "..." } }
"""

import asyncio
import json
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import config
from backend.models.session import get_or_create_session, DTStage
from backend.agents.guardrail import check_topic
from backend.agents.orchestrator import orchestrate
from backend.agents.bmc_judge import evaluate_bmc
from backend.agents.canvas_generator import generate_canvas

logger = logging.getLogger(__name__)

app = FastAPI(title="TokenFounder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.frontend_url, "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# SSE response headers required for correct streaming behavior
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",   # prevents nginx from buffering the stream
    "Connection": "keep-alive",
}


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Main chat endpoint — returns an SSE stream.

    Flow per request:
    1. Guardrail: reject off-topic messages immediately
    2. Add user message to session
    3. Stream orchestrator response (token-by-token, with tool-use loop)
    4. Persist assistant reply to session
    5. BMC Judge: evaluate business completeness (parallel-ready)
    6. Optionally trigger Business Canvas generation
    """
    session = get_or_create_session(req.session_id)

    async def event_stream():
        try:
            # ── 1. Guardrail ─────────────────────────────────────────────
            guard = await check_topic(req.message)

            if not guard.get("is_relevant", True):
                redirect = guard.get(
                    "redirect_message",
                    "这个话题有点偏了，我们继续聊你的 Agent 创业想法吧！"
                )
                yield _sse("redirect", {"message": redirect})
                return

            # ── 2. Record user message ────────────────────────────────────
            # Must happen BEFORE calling orchestrate() so the history is complete
            session.add_message("user", req.message)

            # ── 3. Stream orchestrator response ───────────────────────────
            full_response_parts: list[str] = []

            async for chunk in orchestrate(session):
                full_response_parts.append(chunk)
                yield _sse("text", {"chunk": chunk})

            assistant_reply = "".join(full_response_parts)

            # ── 4. Persist assistant reply ────────────────────────────────
            session.add_message("assistant", assistant_reply)

            # ── 5. BMC evaluation (after stream completes) ────────────────
            judge_result = await evaluate_bmc(session)
            covered = judge_result["covered_count"]
            missing = judge_result["missing_items"]

            yield _sse("bmc_progress", {
                "covered_count": covered,
                "total": 9,
                "missing_items": missing,
                "current_stage": session.current_stage.value,
            })

            # ── 6. Canvas generation if threshold reached ─────────────────
            if judge_result["trigger_canvas"] and not session.canvas_generated:
                session.canvas_generated = True
                session.current_stage = DTStage.COMPLETE

                yield _sse("canvas_start", {
                    "message": (
                        "🎉 你的创业想法已具备完整的商业模式框架！"
                        "正在为你生成商业画布，请稍候..."
                    )
                })

                canvas = await generate_canvas(session, judge_result)
                yield _sse("canvas_complete", canvas.to_dict())

        except Exception as exc:
            logger.exception("Error in chat stream for session %s", req.session_id)
            yield _sse("error", {"message": f"服务暂时出现问题，请稍后重试。({type(exc).__name__})"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@app.get("/api/session/{session_id}")
async def get_session_state(session_id: str):
    """Return current session state (for frontend to restore after refresh)."""
    session = get_or_create_session(session_id)
    return {
        "session_id": session.session_id,
        "current_stage": session.current_stage.value,
        "turn_count": session.turn_count,
        "bmc_covered": session.bmc_info.covered_count,
        "canvas_generated": session.canvas_generated,
        "messages": [
            {"role": m.role, "content": m.content}
            for m in session.messages
        ],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse(event_type: str, data: dict) -> str:
    """Format a single SSE event."""
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"
