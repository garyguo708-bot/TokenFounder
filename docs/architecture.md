# TokenFounder 系统架构设计

## 1. 整体架构概览

```mermaid
flowchart TD
    subgraph Client["前端 Next.js"]
        UI[Chat Interface]
        MD[Mermaid Renderer]
        BC[Business Canvas Viewer]
    end

    subgraph Backend["后端 Python / FastAPI"]
        API["/api/chat\nSSE Stream"]

        subgraph Pipeline["对话处理流水线"]
            GRD[Topic Guardrail\nHaiku · 每轮调用]
            ORC[Main Orchestrator\nSonnet · 主引导]
            MEM[Session Memory\n状态管理]
            JDG[BMC Judge\nHaiku · 并行调用]
        end

        subgraph Tools["工具层"]
            WST[Web Search\nTavily API]
            DGT[Diagram Generator\nMermaid模板引擎]
            BCG[Canvas Generator\n画布结构化输出]
        end
    end

    subgraph External["外部服务"]
        CLD[Claude API\nAnthropic]
        TAV[Tavily Search API]
    end

    UI -->|用户消息| API
    API --> GRD
    GRD -->|偏题| API
    GRD -->|聚焦| ORC
    ORC <--> MEM
    ORC --> WST
    ORC --> DGT
    ORC --> API
    API -->|并行| JDG
    JDG -->|未满足| MEM
    JDG -->|已满足≥7项| BCG
    BCG --> API
    API -->|SSE流式| UI
    UI --> MD
    UI --> BC

    ORC <-->|LLM调用| CLD
    GRD <-->|LLM调用| CLD
    JDG <-->|LLM调用| CLD
    WST <-->|搜索| TAV
```

---

## 2. 对话状态机（DT五阶段）

```mermaid
stateDiagram-v2
    [*] --> Empathize : 对话开始

    Empathize : 🔍 Empathize\n共情·挖掘痛点
    Define : 📌 Define\n定义·聚焦问题
    Ideate : 💡 Ideate\n构想·Agent方案
    Prototype : 🛠️ Prototype\n原型·商业模式
    Validate : 📊 Validate\n验证·市场数据

    Empathize --> Define : 识别到明确痛点+用户群
    Define --> Ideate : 问题陈述清晰
    Ideate --> Prototype : Agent解决方案成型
    Prototype --> Validate : 商业模式框架形成
    Validate --> [*] : BMC Judge满足≥7项

    Define --> Empathize : 发现新痛点（回溯）
    Ideate --> Define : 方案偏离问题（回溯）
    Prototype --> Ideate : 商业模型需重构（回溯）

    note right of Empathize
        工具：Web搜索行业报告
        图形：用户痛点地图
    end note

    note right of Ideate
        工具：Web搜索竞品
        图形：解决方案架构图
    end note

    note right of Validate
        工具：Web搜索市场数据
        图形：商业模式画布预览
    end note
```

---

## 3. 单轮对话处理时序

```mermaid
sequenceDiagram
    actor User as 用户
    participant FE as Next.js前端
    participant API as FastAPI
    participant GRD as Topic Guardrail<br/>(Haiku)
    participant ORC as Orchestrator<br/>(Sonnet)
    participant TOOL as Tools<br/>(Search/Diagram)
    participant JDG as BMC Judge<br/>(Haiku)
    participant BCG as Canvas Generator<br/>(Sonnet)

    User->>FE: 发送消息
    FE->>API: POST /api/chat (stream)
    API->>GRD: 判断主题相关性

    alt 偏题
        GRD-->>API: is_relevant=false + redirect_hint
        API-->>FE: SSE: 重定向回复
        FE-->>User: 温和引回提示
    else 聚焦
        GRD-->>API: is_relevant=true + current_stage
        API->>ORC: 传入消息 + 状态 + DT阶段

        ORC->>ORC: 决策是否调用工具

        opt 需要搜索
            ORC->>TOOL: web_search(query)
            TOOL-->>ORC: 搜索结果摘要
        end

        opt 需要图形
            ORC->>TOOL: generate_diagram(type, data)
            TOOL-->>ORC: Mermaid代码块
        end

        ORC-->>API: SSE流式回复
        API-->>FE: SSE chunks (含Mermaid)
        FE-->>User: 渲染回复 + 图形

        par 并行BMC判断
            API->>JDG: 传入完整对话历史
            JDG-->>API: BMC完整度报告 (score + missing)
        end

        alt score < 7
            API->>ORC: 更新DT阶段状态
            API-->>FE: SSE: 进度提示 (x/9项已完成)
        else score >= 7
            API->>BCG: 生成完整商业画布
            BCG-->>API: 结构化BMC JSON
            API-->>FE: SSE: BMC数据
            FE-->>User: 渲染完整商业画布
        end
    end
```

---

## 4. 商业完整度判断逻辑

```mermaid
flowchart LR
    subgraph Input
        H[对话历史\nfull_history]
    end

    subgraph BMCJudge["BMC Judge (Haiku)"]
        direction TB
        C1[客户细分\nCustomer Segments]
        C2[价值主张\nValue Propositions]
        C3[渠道通路\nChannels]
        C4[客户关系\nCustomer Relationships]
        C5[收入来源\nRevenue Streams]
        C6[核心资源\nKey Resources]
        C7[关键业务\nKey Activities]
        C8[重要伙伴\nKey Partnerships]
        C9[成本结构\nCost Structure]
    end

    subgraph Output
        SC[score: 0-9\nmissing: list\nextracted: dict]
    end

    H --> BMCJudge
    BMCJudge --> SC

    SC -->|score >= 7| GEN[触发画布生成]
    SC -->|score < 7| CONT[继续引导\n提示缺失项]

    style GEN fill:#5cb85c,color:#fff
    style CONT fill:#f0ad4e,color:#000
```

---

## 5. 项目目录结构

```
TokenFounder/
├── docs/
│   ├── architecture.md          # 本文件：系统架构
│   └── prompts.md               # 所有Agent提示词
│
├── backend/
│   ├── pyproject.toml           # 依赖管理 (uv)
│   ├── main.py                  # FastAPI入口
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── orchestrator.py      # 主编排Agent (Sonnet)
│   │   ├── guardrail.py         # 主题守护 (Haiku)
│   │   ├── bmc_judge.py         # 商业完整度判断 (Haiku)
│   │   └── canvas_generator.py  # 商业画布生成 (Sonnet)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── web_search.py        # Tavily搜索工具
│   │   └── diagram.py           # Mermaid模板生成
│   ├── models/
│   │   ├── __init__.py
│   │   ├── session.py           # 会话状态 (DT阶段 + BMC积累)
│   │   └── bmc.py               # 商业画布数据模型
│   └── config.py                # 环境变量 & 常量
│
├── frontend/
│   ├── package.json
│   ├── app/
│   │   ├── layout.tsx
│   │   └── page.tsx             # 主聊天页面
│   └── components/
│       ├── ChatWindow.tsx       # 对话窗口
│       ├── MessageBubble.tsx    # 消息气泡(支持Mermaid)
│       ├── ProgressBar.tsx      # BMC完整度进度条
│       └── BusinessCanvas.tsx   # 商业画布展示组件
│
└── README.md
```

---

## 6. 技术选型说明

| 层级 | 技术 | 选择理由 |
|------|------|---------|
| 主引导LLM | claude-sonnet-4-6 | 高质量对话推理，工具调用能力强 |
| 守护/判断LLM | claude-haiku-4-5 | 低延迟低成本，每轮并行调用 |
| 后端框架 | FastAPI + SSE | 原生支持流式输出，Python生态丰富 |
| 前端框架 | Next.js 14 (App Router) | React生态，易集成Mermaid.js |
| 搜索工具 | Tavily API | 专为LLM设计，返回结构化摘要 |
| 图形渲染 | Mermaid.js | 纯文本描述图形，LLM天然友好 |
| 状态存储 | 内存 (dict) → Redis | MVP阶段内存，后续扩展Redis |
| 依赖管理 | uv (Python) | 现代Python包管理，速度快 |
