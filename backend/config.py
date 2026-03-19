import os
from dataclasses import dataclass


@dataclass
class Config:
    # Claude API
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model_main: str = "claude-sonnet-4-6"       # Orchestrator + Canvas Generator
    model_fast: str = "claude-haiku-4-5-20251001"  # Guardrail + BMC Judge

    # Search
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # BMC threshold
    bmc_trigger_threshold: int = 7  # 9项中满足几项触发画布生成

    # CORS
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")


config = Config()
