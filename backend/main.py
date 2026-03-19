"""
TokenFounder FastAPI Backend
SSE streaming endpoint for the Agent startup ideation chat.
"""

import asyncio
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import config
from backend.models.session import get_or_create_session, DTStage
from backend.agents.guardrail import check_topic
from backend.agents.orchestrator import orchestrate
from backend.agents.bmc_judge import evaluate_bmc
from backend.agents.canvas_generator import generate_canvas

app = FastAPI(title="TokenFounder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Main chat endpoint — returns SSE stream.
    Each SSE event is a JSON object with `type` and `data` fields.
    """
    session = get_or_create_session(req.session_id)

    async def event_stream():
        # ── Step 1: Guardrail check ──────────────────────────────────────
        guard = await check_topic(req.message)

        if not guard.get("is_relevant", True):
            redirect = guard.get("redirect_message", "让我们回到Agent创业的讨论吧！")
            yield _sse("redirect", {"message": redirect})
            return

        # ── Step 2: Record user message ──────────────────────────────────
        session.add_message("user", req.message)

        # ── Step 3: Stream orchestrator response ─────────────────────────
        full_response = []
        async for chunk in orchestrate(session, req.message):
            full_response.append(chunk)
            yield _sse("text", {"chunk": chunk})

        assistant_reply = "".join(full_response)
        session.add_message("assistant", assistant_reply)

        # ── Step 4: Parallel BMC evaluation ─────────────────────────────
        judge_result = await evaluate_bmc(session)
        covered = judge_result.get("covered_count", 0)
        missing = judge_result.get("missing_items", [])

        yield _sse("bmc_progress", {
            "covered_count": covered,
            "total": 9,
            "missing_items": missing,
            "current_stage": session.current_stage.value,
        })

        # ── Step 5: Trigger canvas generation if threshold met ────────────
        if judge_result.get("trigger_canvas") and not session.canvas_generated:
            session.canvas_generated = True
            session.current_stage = DTStage.COMPLETE
            yield _sse("canvas_start", {"message": "🎉 恭喜！你的创业想法已具备完整的商业模式框架，正在生成商业画布..."})

            canvas = await generate_canvas(session, judge_result)
            yield _sse("canvas_complete", canvas.to_dict())

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Return current session state."""
    session = get_or_create_session(session_id)
    return {
        "session_id": session.session_id,
        "current_stage": session.current_stage.value,
        "turn_count": session.turn_count,
        "bmc_covered": session.bmc_info.covered_count,
        "canvas_generated": session.canvas_generated,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


def _sse(event_type: str, data: dict) -> str:
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"
