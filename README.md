# TokenFounder

> Unlock the commercial productivity of Token, enabling everyone to launch an AI-managed, self-operating, and sustainably profitable digital company with just a single idea.

**TokenFounder** 是一个基于 Design Thinking 方法论的 AI Agent 创业想法孵化智能体。通过多轮引导对话，帮助用户从模糊的想法逐步形成完整的商业模式，最终自动生成 Business Model Canvas（商业画布）。

---

## 核心特性

- **DT五阶段引导** — Empathize → Define → Ideate → Prototype → Validate，状态机驱动的聚焦式对话
- **双模型分层** — Sonnet 负责高质量主引导，Haiku 负责低成本主题守护和商业完整度判断
- **工具辅助** — 联网搜索（Tavily）+ Mermaid 图形生成，实时可视化思路
- **主题守护** — 偏题时温和拉回，始终聚焦 Agent 创业方向
- **自动画布生成** — 商业模式满足 7/9 项阈值后，自动生成完整商业画布

## 文档

- [系统架构设计](./docs/architecture.md) — 架构图、状态机、时序图
- [Agent提示词设计](./docs/prompts.md) — 所有模块的 System Prompt

## 项目结构

```
TokenFounder/
├── docs/                    # 架构与提示词设计文档
├── backend/                 # Python FastAPI 后端
│   ├── agents/              # 四个智能体模块
│   ├── tools/               # 搜索 & 图形工具
│   ├── models/              # 数据模型
│   └── main.py              # FastAPI + SSE 入口
└── frontend/                # Next.js 前端
    ├── app/                 # App Router 页面
    └── components/          # 聊天、进度条、画布组件
```

## 快速启动

### 1. 配置环境变量
```bash
cp .env.example .env
# 填入 ANTHROPIC_API_KEY 和 TAVILY_API_KEY
```

### 2. 启动后端
```bash
cd backend
pip install uv
uv sync
uv run uvicorn main:app --reload
```

### 3. 启动前端
```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000 开始你的创业想法孵化之旅。

## 技术栈

| 层级 | 技术 |
|------|------|
| 主引导 LLM | claude-sonnet-4-6 |
| 守护/判断 LLM | claude-haiku-4-5 |
| 后端 | Python + FastAPI + SSE |
| 前端 | Next.js 14 + Tailwind CSS |
| 搜索 | Tavily API |
| 图形 | Mermaid.js |
