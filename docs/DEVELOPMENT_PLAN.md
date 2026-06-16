# Workmate Agent Development Plan

本文档用于指导 Workmate Agent 下一阶段开发。

项目目标从“持续贴合个人使用”调整为“成为一个可以放入简历的完整 Agent 工程项目”。后续开发优先展示 Agent 技术能力、工程可复现性和可验证性，而不是继续堆叠个人化功能。

## 项目定位

Workmate Agent 是一个本地优先的个人生产力 Agent，核心能力包括长期记忆、任务状态追踪、工具增强推理、自适应上下文规划和主动监督闭环。

英文简历表述建议：

```text
Workmate Agent is a local-first productivity agent with hybrid memory RAG,
tool-augmented reasoning, long-term task-state tracking, adaptive context planning,
and proactive supervision.
```

## 开发原则

- Agent 特征显性化：让项目看起来不是 API 聊天窗口，而是有明确感知、规划、行动、观察和记忆更新循环的 Agent 系统。
- 工程证明优先：测试、评估、trace、文档、API schema 的优先级高于继续增加个人体验小功能。
- 复用现有资产：保留当前记忆系统、任务生命周期、监督事件和 Web 调试台，在此基础上做架构化包装。
- 本地可运行：继续保持 `./run.sh` 一键启动；新增 Docker / CI / eval 时也要保证本地开发体验简单。
- 避免过度框架化：暂不强依赖 LangChain / AutoGen。项目亮点应是自研 memory、state management、supervision 和 agent loop。

## 当前基础

当前项目已经具备以下能力：

- 长期记忆：对话记录、结构化记忆项、语义压缩、高阶洞察、自我反省、记忆治理
- 状态管理：任务生命周期、子任务、承诺、专注会话、行为统计
- 主动监督：监督事件、提醒偏好、后台 scheduler、多渠道通知、用户反馈闭环
- 上下文系统：意图识别、上下文规划、检索计划、上下文压缩
- 工具调用：内部状态工具层，可读写任务、承诺、记忆和专注会话
- Web 调试台：对话、记忆、任务、dashboard、监督事件、模型上下文可视化

下一阶段重点不是继续增加提醒功能，而是把这些能力整理成清晰、可验证、可展示的 Agent 项目。

## 版本路线

### V1.4 Agent Runtime 显性化

状态：已实现。

目标：把当前分散在 `src/core.py`、`memory/manager.py`、`tools/` 中的流程整理成清晰的 Agent Loop。

要做：

- 新增 `agent/` 或 `runtime/` 目录，封装核心运行时
- 引入 `AgentRuntime` / `AgentLoop`
- 明确每轮执行阶段：
  - receive user input
  - classify intent
  - plan context
  - retrieve memory
  - decide tool calls
  - execute tools
  - generate response
  - write memory
  - update supervision state
- 为每轮生成 `turn_id`
- 把 `last_context_messages`、`last_tool_calls`、`last_pipeline_result` 整合为统一 `turn_trace`
- 保持现有 CLI / Web 行为不破坏

验收标准：

- README 或 architecture 文档中能说明完整 Agent Loop
- Web API 能返回最近一轮 `turn_trace`
- 现有 `/api/chat` 流式响应正常工作
- 旧的 `WorkmateAgent.invoke()` 仍可用

实现记录：

- 新增 `agent/runtime.py`，由 `AgentRuntime` 统一执行单轮 Agent Loop
- `src/core.py` 继续提供 `WorkmateAgent.invoke()`、`invoke_stream()` 和 CLI，但内部委托 Runtime
- `turn_trace` 统一记录 `turn_id`、执行阶段、上下文规模、工具调用、记忆写回和耗时
- `/api/chat`、流式 done 事件、`/api/memory`、`/api/context` 暴露 `turn_trace`
- Web 左侧 `MEMORY` 面板新增 `runtime` 摘要，方便观察最近一轮 Agent 执行链路

简历亮点：

```text
Designed an explicit agent runtime loop covering intent analysis, memory retrieval,
tool execution, response generation, memory writeback, and proactive supervision.
```

### V1.5 Hybrid Memory RAG

状态：已实现。

目标：把当前关键词检索升级为更标准的 Memory RAG，使长期记忆检索成为项目的核心 Agent 特征。

要做：

- 设计 `MemoryRetriever`
- 保留现有关键词检索，新增可选向量检索
- 支持 hybrid scoring：
  - keyword score
  - recency score
  - memory type weight
  - importance / salience score
- 检索对象至少覆盖：
  - conversation records
  - memory_items
  - memory_categories
  - commitments
  - tasks
  - high_level_insights
  - behavior_patterns
- 检索结果包含 `source_type`、`source_id`、`score`、`reason`
- 前端 `MODEL CONTEXT` 展示本轮 RAG 召回结果和选择原因
- 向量检索可作为可选能力，未配置 embedding 时自动退回关键词检索

验收标准：

- 给定一组固定 query，检索能返回相关记忆并说明原因
- 没有 embedding 配置时项目仍可运行
- `retrieval_plan` 能展示是否检索、检索来源和 top results
- 有最小单元测试覆盖 hybrid scoring

实现记录：

- 新增 `memory/retriever.py`，实现 `MemoryRetriever`
- `SearchManager` 继续保留兼容 API，内部委托 Hybrid Retriever 计算评分
- 检索评分拆解为 `keyword`、`recency`、`salience`、`type_weight`、可选 `vector`
- 检索结果统一返回 `source_type`、`source_id`、`score`、`reason` 和 `score_breakdown`
- 检索来源扩展到 `tasks` 和 `behavior_patterns`
- `retrieval_plan` 新增 `mode`、`vector_status`、`top_results`
- Web `MODEL CONTEXT` 顶部展示本轮 RAG 召回结果和评分原因
- 新增 `tests/test_memory_retriever.py`，覆盖 hybrid scoring 与索引构建

简历亮点：

```text
Built a hybrid memory RAG system for long-term personalized context retrieval,
combining keyword recall, recency weighting, memory type weighting, and traceable source attribution.
```

### V1.6 Tool Calling 与 Trace 工程化

状态：已实现。

目标：让内部工具调用从“能用”升级为“可观察、可测试、可解释”的 Agent tool-use 模块。

要做：

- 为每个工具补齐 schema：
  - name
  - description
  - input schema
  - output schema
  - side effects
- 工具调用统一记录：
  - tool name
  - input
  - output
  - status
  - error
  - duration_ms
- 限制每轮最大工具调用次数
- 明确哪些工具只读、哪些工具会写状态
- 在 Web `MODEL CONTEXT` 或新 `TRACE` 面板展示工具调用轨迹
- 编写工具调用测试

验收标准：

- 工具调用失败不会中断整个对话
- 工具调用 trace 可在 API 中读取
- 至少覆盖任务、承诺、专注会话、记忆检索相关工具测试
- 工具 schema 可被独立打印或导出

实现记录：

- `ToolSpec` 新增 `output_schema`、`side_effects`、`read_only`
- `ToolRegistry.export_schemas()` 支持独立导出工具 schema
- `ToolExecutor` 记录 `call_id`、调用原因、耗时、读写模式、副作用、输入输出 schema 和错误
- 工具规划失败会生成 `__tool_planning__` error trace，避免静默失败
- Workmate 内部工具补齐任务、承诺、记忆、专注会话相关 schema 和副作用说明
- Web/API 暴露 `tool_schemas`，`MODEL CONTEXT` 展示 `TOOL TRACE`
- 新增 `tests/test_tool_executor.py`，覆盖工具 schema、trace、失败隔离和 max_calls

简历亮点：

```text
Implemented schema-driven internal tools with execution tracing, bounded tool calls,
error isolation, and state mutation auditing.
```

### V1.7 Evaluation Suite

状态：已实现。

目标：补齐 Agent 项目最关键的工程证明：可复现评估。

要做：

- 新增 `evals/`
- 新增固定评估用例：
  - memory recall
  - task tracking
  - commitment extraction
  - reminder control
  - tool calling
  - context planning
  - supervision event lifecycle
- 新增 `evals/run_eval.py`
- 输出 Markdown 或 JSON 报告
- 设计基础指标：
  - intent accuracy
  - memory recall hit rate
  - task state correctness
  - tool call correctness
  - supervision event transition correctness
- 支持无真实 API Key 的 rule / fake LLM 模式

验收标准：

- `python evals/run_eval.py` 可以在本地跑通
- 至少 20 条固定用例
- 报告输出到 `evals/reports/`
- CI 中可以运行不依赖真实 LLM 的 eval smoke test

实现记录：

- 新增 `evals/cases.json`，内置 24 条固定评估用例
- 新增 `evals/run_eval.py`，使用 rule / fake LLM 模式运行，不依赖真实 API Key
- 覆盖 memory recall、task tracking、commitment extraction、reminder control、tool calling、context planning、supervision event lifecycle
- 输出 JSON 和 Markdown 报告到 `evals/reports/`
- 默认 `--min-score 1.0`，可直接作为后续 CI smoke test 命令
- `.gitignore` 忽略本地生成的 eval 报告，只保留 `evals/reports/.gitkeep`

简历亮点：

```text
Created an evaluation suite for long-term memory recall, task-state tracking,
tool-use correctness, and proactive supervision lifecycle transitions.
```

### V1.8 Tests 与 CI

目标：让项目从个人原型提升为可信工程项目。

要做：

- 新增 `tests/`
- 引入 `pytest`
- 覆盖核心模块：
  - memory pipeline
  - context planner
  - memory retriever
  - task lifecycle
  - supervision event state machine
  - reminder preference strategy
  - tool executor
  - web API smoke tests
- 新增 GitHub Actions
- CI 至少运行：
  - Python syntax check
  - pytest
  - eval smoke test
- 避免测试写入真实 `memory/data`

验收标准：

- `pytest` 本地可跑
- CI 绿色
- 测试使用临时目录或 fixture 隔离状态
- README 展示测试命令

简历亮点：

```text
Added automated unit tests, evaluation smoke tests, and CI to validate memory,
tool-use, context planning, and supervision state transitions.
```

### V1.9 FastAPI 与 API Schema

目标：把当前 Web API 从原型 HTTP handler 升级为更标准的后端服务。

要做：

- 引入 FastAPI
- 保留现有前端路径和功能
- 定义 Pydantic schema：
  - ChatRequest / ChatResponse
  - Stream event schema
  - MemoryState
  - TaskState
  - SupervisionEvent
  - ToolTrace
  - TurnTrace
- 提供 OpenAPI 文档
- 保留 `python -m src.web` 或改为兼容入口

验收标准：

- `./run.sh` 仍可启动项目
- `/docs` 可查看 API schema
- 前端对话、记忆、dashboard、监督事件正常工作
- 旧接口路径尽量兼容

简历亮点：

```text
Migrated the local agent backend to FastAPI with typed request/response schemas
and OpenAPI documentation.
```

### V2.0 Demo Packaging

目标：把项目包装成招聘者可以快速理解和运行的作品。

要做：

- 新增 `docs/architecture.md`
- 新增 `docs/agent-loop.md`
- 新增 `docs/memory-rag.md`
- 新增 `docs/evaluation.md`
- 新增架构图
- 新增 demo seed data
- 新增一键重置 demo 数据脚本
- 新增 Dockerfile 或 docker-compose
- README 首页重写为简历项目风格：
  - 一句话项目定位
  - Agent architecture
  - Core technical highlights
  - Quick start
  - Demo screenshots
  - Evaluation results

验收标准：

- 新用户可以 5 分钟内跑起来
- README 能清楚展示 Agent 技术亮点
- 有截图、架构图、评估结果
- 不暴露 `.env`、API Key 或个人记忆数据

简历亮点：

```text
Packaged the project with reproducible demos, architecture documentation,
evaluation reports, and Docker-based local deployment.
```

## 推荐开发顺序

严格按以下顺序推进：

1. V1.4 Agent Runtime 显性化
2. V1.5 Hybrid Memory RAG
3. V1.6 Tool Calling 与 Trace 工程化
4. V1.7 Evaluation Suite
5. V1.8 Tests 与 CI
6. V1.9 FastAPI 与 API Schema
7. V2.0 Demo Packaging

原因：

- 先明确 Agent Loop，后续 RAG、工具、trace、eval 才有统一挂载点
- 先补 RAG 和工具 trace，再做 eval，评估对象才清晰
- 先有 eval 和 tests，再做 FastAPI 迁移，避免重构破坏核心行为
- 最后做 demo packaging，避免过早包装一个还不稳定的架构

## 暂缓事项

以下事项对个人使用有价值，但对简历项目优先级较低，暂缓：

- 更细腻的情绪陪伴语气
- 更多前端视觉优化
- 更复杂的提醒文案个性化
- 更强的个人自律方法论库
- 多用户系统
- 商业化账户体系
- 复杂日历集成

## 简历项目完成标准

当以下条件满足时，Workmate Agent 可以作为简历项目重点展示：

- 有明确 Agent Loop 文档和代码结构
- 有 Memory RAG，且检索结果可追踪
- 有工具调用 schema、trace 和测试
- 有 eval suite 和报告
- 有 pytest / CI
- 有标准 API schema
- README 能在 2 分钟内让招聘者理解技术亮点
- demo 可一键运行，不依赖个人数据
