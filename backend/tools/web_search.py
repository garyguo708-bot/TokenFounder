"""
Web Search Tool — powered by Tavily API.
Returns a concise summary suitable for injection into LLM context.
"""

import httpx
from backend.config import config


async def web_search(query: str, max_results: int = 3) -> str:
    """Search the web and return a formatted summary."""
    if not config.tavily_api_key:
        return f"[搜索工具未配置，跳过搜索: {query}]"

    payload = {
        "api_key": config.tavily_api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": True,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post("https://api.tavily.com/search", json=payload)
        resp.raise_for_status()
        data = resp.json()

    lines = [f"🔍 搜索：{query}\n"]

    if data.get("answer"):
        lines.append(f"**摘要**: {data['answer']}\n")

    for i, result in enumerate(data.get("results", [])[:max_results], 1):
        lines.append(f"{i}. **{result.get('title', '')}**")
        lines.append(f"   {result.get('content', '')[:200]}...")

    return "\n".join(lines)


# Tool definition for Claude's tool_use API
WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": "搜索互联网获取市场数据、竞品信息、行业趋势等最新信息。当用户提到具体行业、市场或竞品时使用。",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，建议用英文以获得更好结果，例如 'AI sales email agent market size 2025'",
            }
        },
        "required": ["query"],
    },
}
