# Changelog

本文档记录 Workmate Agent 的重要能力演进与架构决策。当前版本保留较详细说明；早期版本按工程阶段归档，细粒度修复可通过 Git history 查询。

## V2.9.0 - State-centric Hierarchical Memory

### 核心变化

- 新增 `LongTermKnowledgeManager`，将稳定用户认知投影为 `USER.md`、`GOALS.md`、`PREFERENCES.md`、`PATTERNS.md` 和 `INSIGHTS.md`。
- 明确四层记忆边界：最近对话属于工作记忆，任务等属于权威状态，稳定认知使用 Markdown，历史经历使用 Episodic RAG。
- `ContextPlanner` 直接注入当前任务、承诺、专注状态和相关长期认知，减少画像、洞察和原子记忆的重复上下文。
- `SearchManager` 改为 `episodic_only`：RAG 只索引历史对话、摘要、语义片段、资源和历史记忆项。
- 当前任务、承诺、画像、洞察和行为模式不再进入向量索引；旧索引中的相关条目会在读取时过滤，并在增量同步时删除。
- Retrieval plan 新增 `source_policy`，明确历史召回不能覆盖当前执行状态。
- 本地数据 inventory、ZIP export 和 OpenAPI schema 纳入 Markdown 长期认知文件。

### 工程证据

- 新增分层知识、上下文边界、旧索引兼容和数据可移植性测试。
- API 的 memory/context 快照暴露长期认知文件状态。
- README 与架构 walkthrough 更新为分层记忆设计。

## V2.8 - Privacy & Local Data Control

- 新增本地数据 inventory，按 conversation、execution state、derived profile、memory index、supervision 和 screen observation 分类。
- 新增 `/api/privacy/inventory`、`/api/privacy/export` 和受控 ZIP 下载端点。
- 导出包包含 manifest，并通过路径边界检查防止目录穿越。
- 默认排除 `.env`、API Key、截图、屏幕观察内容、ChromaDB 索引和缓存元数据。
- Web `SYSTEM CONFIG` 增加本地数据统计和导出入口。

## V2.7 - Demo & Interview Readiness

- 加固 `run.sh`：检查项目目录、API Key、依赖和端口，支持 conda `agent` 与本地 `.venv`。
- 新增 `scripts/reset_demo_data.py`，备份私人数据后生成可复现演示状态。
- 新增 `docs/ARCHITECTURE_WALKTHROUGH.md`，覆盖系统架构、Agent Loop、RAG、工具调用、监督状态机和讲解脚本。
- README 增加 reviewer quick view、能力证据表、5 分钟 Demo 路线和简历表述。

## V2.6 - Proactive Supervision Closed Loop

- 将监督事件整理为显式状态机：`detected / notified / acknowledged / snoozed / muted / resolved / dismissed`。
- 新增 `transition_history`、迁移原因、状态统计和最近迁移摘要。
- 分离只读快照与主动推进：GET API 不产生副作用，scheduler 和 `/api/scheduler/tick` 负责推进事件。
- 自适应提醒策略增加 evidence、affected fields、confidence 和 explanation。
- Vision 提醒改为 transient supervision messages，不再进入长期对话、画像或 RAG。

## V2.5 - RAG Maturity

- Hybrid scoring 综合关键词、时间衰减、显著度、向量相似度和任务相关性。
- 增加 metadata filter、source attribution、score breakdown 和检索充分性诊断。
- ChromaDB 从全量重建升级为增量 delete/upsert，并复用未变化 embedding。
- 增加可替换 reranker hook 和 Memory Retrieval eval cases。

## V2.4 - Tool Action Layer Hardening

- Tool planner trace 记录候选工具、选择数量、执行数量、max calls 和截断状态。
- 写状态工具生成 audit record，记录决策来源、参数、输出、耗时和副作用。
- 工具失败增加 recoverable 语义与 recovery hint，避免普通对话被内部工具故障中断。
- 监督偏好进入 Tool Registry，工具覆盖任务、记忆、专注会话和监督配置。

## V2.3 - Agent Observability & Evaluation

- 在 `turn_trace` 上增加 observability summary，聚合阶段时间线、慢阶段、RAG、工具、记忆写回和错误。
- Provider trace 覆盖 LLM、Vision、Embedding 和 TTS 的调用次数、耗时、usage、fallback 和错误摘要。
- 增加 RAG explainability、tool trace detail 与 provider detail snapshot。
- Evaluation Suite 增加 observability trace 和 OpenAPI schema smoke cases。
- Web `MODEL CONTEXT` 与 FastAPI response schema 暴露完整可观察信息。

## V2.0-V2.2 - API, Voice & Multimodal Platform

### FastAPI 与接口工程化

- Web 后端迁移至 FastAPI，保留 SSE 流式对话并提供 `/docs`、`/redoc` 和 `/openapi.json`。
- 核心响应升级为嵌套 Pydantic schema，覆盖任务、承诺、监督事件、工具调用和运行轨迹。
- 增加 API contract tests 与 TestClient smoke tests。

### Voice 与 Vision

- 增加浏览器 Web Speech API 和讯飞 TTS provider，语音偏好持久化到后端。
- Vision 使用独立模型配置，支持 OpenAI-compatible 多模态 API。
- 屏幕监督逐步从硬编码分类器演进为 Vision Screen Companion，模型直接生成自然提醒。
- 修复提醒二次截断、重复模型调用、异常尾字符和浏览器偏好不同步等问题。

### Vector Store

- 引入嵌入式 ChromaDB，并保留无 embedding 或无向量依赖时的 JSON/关键词降级路径。

## V1.4-V1.9 - Agent Engineering Foundation

### Agent Runtime

- 将上下文规划、工具执行、模型回复、记忆写回和监督更新显式组织为 `AgentRuntime`。
- 每轮生成 `turn_trace`，记录阶段状态、耗时、上下文规模和执行结果。

### Memory RAG

- 引入 `MemoryRetriever`、检索计划、类型权重、关键词/近期性/显著度评分和可选向量相似度。
- 扩展召回来源并在 Web 中展示 top results、分数和原因。

### Tool Calling

- 建立 Tool Registry、schema-driven executor、读写边界、副作用声明和 Tool Trace。
- 工具主要用于读取和更新 Workmate 内部状态，不执行任意外部操作。

### Evaluation & CI

- 增加固定 Evaluation Suite，覆盖意图、记忆、任务、承诺、提醒、工具和监督生命周期。
- 引入 pytest 与 GitHub Actions，自动运行语法检查、测试和 eval smoke test。

### Screen Supervision

- 增加多模态屏幕观察、应用黑白名单、Vision fallback 和陪伴/偏航状态转换。

## V1.0-V1.3 - Supervision Product Loop

- 建立统一监督事件模型，连接专注超时、承诺到期和任务停滞。
- 增加事件确认、稍后提醒、静音、完成、关闭和关联状态联动。
- 增加提醒偏好、静默时段、分渠道门槛和事件类型门槛。
- 根据用户反馈生成自适应提醒策略，应用前需要用户确认。
- 增加个人自律仪表盘、行为统计和行为模式分析。
- 调整 Agent 人格为低压力监督：优先记住和整理，必要时只给一个轻量建议。

## V0.4-V0.9 - Task & Memory Foundation

### Task Lifecycle

- 从单一 `task_state.json` 扩展为任务、子任务和事件流水。
- 任务状态支持 `inbox / planned / active / blocked / done / abandoned`。
- 增加 Todo UI、任务相似度去重、承诺 deadline 和专注会话。

### Memory Pipeline

- 从最近对话缓存演进为 Resource / MemoryItem / MemoryCategory 三层模型。
- 每轮完成 LLM 记忆提取、摘要、画像更新、语义压缩、索引刷新和上下文规划。
- 增加高阶洞察、自我反省、冲突/陈旧记忆治理和上下文预算。
- 参考 ReMe 与 MemU 的文件式记忆、上下文治理和流水线契约思想。

### Product Experience

- 增加 Web 连续对话、Markdown 渲染、页面会话恢复和流式输出。
- 增加后台 scheduler、桌面通知、Bark/飞书推送和周度复盘。
- 提醒策略逐步移除强制证明、技术指导和时间施压，聚焦总体规划与温和监督。

## V0.1-V0.3 - Prototype

- 建立 OpenAI-compatible LLM client 与连续对话入口。
- 增加本地对话记录、近期上下文、每日摘要、任务快照、承诺和用户画像。
- 从终端交互扩展为本地 Web 调试页面，并支持 Markdown 回复和 SSE 流式输出。

## Release Policy

- 新版本只记录影响架构、行为、接口或验证证据的变化。
- 文案微调、实验性提示词和单点修复合并到对应里程碑，不再单独占用版本章节。
- 运行数据、API Key、截图、向量索引和本地 eval reports 不进入版本库。
