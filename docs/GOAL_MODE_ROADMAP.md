# Workmate Agent Goal Mode Roadmap

本文档用于指导 Codex Goal 模式持续推进 Workmate Agent。它的重点不是罗列所有想做的功能，而是规定下一阶段的版本顺序、每个版本的验收标准，以及 Goal 模式执行时应遵守的边界。

当前基线版本：V2.2.1。

## 总目标

Workmate Agent 后续开发应服务于一个更清晰的简历项目定位：

```text
Workmate Agent is a local-first productivity agent with explicit agent runtime,
hybrid memory RAG, schema-driven tool calling, multimodal screen supervision,
observable execution traces, and reproducible evaluation.
```

换句话说，后续版本要优先证明它是一个完整 Agent 工程项目，而不是继续把它优化成只贴合个人使用习惯的聊天工具。

## Goal 模式执行原则

- 简历价值优先：每个版本都应强化一个可展示的 Agent / 工程化知识点。
- 闭环优先：每个版本必须有实现、测试或评估、文档记录，避免只堆功能。
- 可观察优先：新增能力应尽量能在 API、前端调试区、trace 或 eval 报告中被看见。
- 少做个人化微调：除非影响核心演示，不继续围绕语气、文案、提醒频率做大量细碎优化。
- 保持一键运行：继续维护 `./run.sh`、`python -m src.web` 和 FastAPI `/docs` 的可用性。
- 保护运行数据：不要提交 `.env`、API Key、`memory/data/chroma/`、eval 临时报表和其它运行缓存。
- 低压力人格边界：Workmate 的提醒仍应是温和监督，不要把系统重新调成压迫式任务管理器。
- Vision Companion 边界：屏幕陪伴提醒以视觉模型自然输出为主，避免重新引入硬编码提醒模板。

## 推荐版本顺序

### V2.3 Agent Observability & Evaluation

状态：进行中。V2.3.0 已完成首个 observability 切片，新增 `observability` 摘要层、FastAPI schema 字段、前端 `OBSERVABILITY SUMMARY` 展示、`observability_trace` eval 类别，以及更适合展示的 eval coverage report。V2.3.1 已补充 provider trace，覆盖 LLM、Vision、Embedding、TTS 的调用次数、耗时、错误摘要和 fallback 路径。V2.3.2 已补充 provider usage snapshot，展示真实 usage tokens 或基于字符/图片/音频规模的估算 token。V2.3.3 已补充 API schema smoke eval，自动审计 OpenAPI 路径、响应模型和 observability/provider 字段。V2.3.4 已补充 RAG explainability snapshot，展示检索注入决策、score coverage、top sources、score breakdown 和文本预览。V2.3.5 已补充 tool trace detail snapshot，展示工具调用序列、读写模式、输入输出摘要、schema 键、错误和副作用。V2.3.6 已补充 provider detail snapshot，展示单条 provider 调用序列、metadata keys、usage、慢调用、fallback 时间线和错误摘要。后续可以开始进入 V2.4 工具行动层加固。

目标：把当前 Agent 的运行过程变得更可审计、更像成熟工程项目。

优先级最高。原因是项目已经有 Agent Runtime、工具、RAG、监督事件和 Vision 能力，但简历展示时还需要证明这些能力“可追踪、可复现、可评估”。

建议实现：

- 已完成：新增 observability summary，展示每轮 `turn_trace` 的阶段时间线、最慢阶段、模型调用概览、RAG 摘要、工具读写统计、记忆写回状态和错误列表。
- 已完成：`/api/memory`、`/api/context`、`/api/chat` 流式 done 事件和前端 `MODEL CONTEXT` 均能查看 observability 摘要。
- 已完成：扩展 eval runner，新增 `observability_trace` 类别，覆盖 trace 摘要、RAG 命中、工具错误、记忆写回和监督事件更新。
- 已完成：扩展 eval Markdown/JSON 报告，新增 Coverage Map、Category Notes、Observability Trace Cases 和 Report Use 区块，方便把评估结果包装成简历项目证据。
- 已完成：记录并展示 LLM、Vision、Embedding、TTS 调用次数、耗时、失败原因和降级路径，provider trace 汇入 `turn_trace`、`observability`、前端和 eval。
- 已完成：进一步记录 provider usage tokens、估算 tokens、输入/输出字符数、图片数、图片 base64 字节、音频字节和 embedding 维度，便于展示成本意识。
- 已完成：补充 `api_schema_smoke` eval，检查关键 FastAPI 路径、响应模型和 observability/provider 字段，并在 Markdown 报告展示 API Schema Smoke Cases。
- 已完成：进一步强化 RAG 检索计划、top results、score breakdown、上下文注入原因的可视化，并将 RAG explainability 纳入 observability、前端、FastAPI schema 和 eval。
- 已完成：进一步展示工具调用链路，包括工具名、读写属性、输入输出摘要、schema 键、耗时、错误和副作用，并将 tool trace detail 纳入 observability、前端、FastAPI schema 和 eval。
- 已完成：进一步打磨 provider 调用详情展示，例如单条调用列表、fallback 时间线和错误归因摘要，并将 provider detail 纳入 observability、前端、FastAPI schema 和 eval。

验收标准：

- `python -m pytest -q` 通过。
- `python evals/run_eval.py --report-dir /tmp/workmate-eval-reports` 通过。
- 前端或 API 能看到一轮 Agent 的完整执行链路。
- README 或文档能说明如何查看 trace / eval 报告。

简历亮点：

```text
Built a lightweight observability layer for a local-first agent, exposing runtime traces,
model calls, retrieval decisions, tool execution, and reproducible eval reports.
```

### V2.4 Tool Calling / Action Layer Hardening

状态：进行中。V2.4.0 已补充 `tool_plan` 与 planner trace，能够记录工具规划来源、解析数量、选择数量、执行数量、max calls、截断状态，并把 `decision_source`、`planner_call_index` 写入每条工具调用。V2.4.1 已为写状态工具补充结构化 `audit_record`，记录工具名、状态、决策来源、planner 序号、side effects、参数键和输出键。V2.4.2 已补充工具失败可恢复语义，trace 中会展示 `recoverable` 与 `recovery_hint`。V2.4.3 已将监督提醒偏好纳入 Tool Registry，补齐任务、记忆、专注、监督偏好四类工具覆盖。

目标：让工具调用从“内部状态操作”升级为更标准的 Agent action layer。

建议实现：

- 已完成：统一 Tool Registry 的 schema、权限、读写属性和副作用声明，并覆盖任务、记忆、专注、监督偏好四类内部状态工具。
- 已完成：设计轻量 Tool Planner trace，先记录是否需要工具、选择了多少工具、执行了多少工具，以及是否被 max calls 截断。
- 已完成：在 trace 中清楚标记工具调用来自模型决策、planner 错误、无 registry 等来源。
- 已完成：为状态写入类工具增加更明确的审计记录，例如任务创建、任务更新、专注会话、记忆写入、提醒偏好修改。
- 已完成：为工具调用失败设计可恢复路径，保证失败不会中断普通回复，并在 trace 中展示 recovery hint。

验收标准：

- 工具 schema 可导出或在 API 中查看。
- 每次工具调用都有 trace。
- 至少覆盖任务、记忆、专注、监督偏好这四类工具的测试。
- 写状态工具必须能说明 side effects。

简历亮点：

```text
Designed a schema-driven agent action layer with permission-aware state tools,
execution tracing, failure isolation, and side-effect auditing.
```

### V2.5 RAG & Memory Retrieval Maturity

状态：进行中。V2.5.0 已补充 retrieval metadata filters、source attribution 和 Memory Retrieval Cases 报告，能按类型、状态、任务关联、显著度和时间收窄召回，并在前端/报告中解释每条上下文来源。V2.5.1 已将 ChromaDB 同步从全量删除重建改为增量 delete/upsert。V2.5.2 已补充任务相关性评分和可替换 rerank hook。

目标：让记忆系统从“已经接入向量库”升级为更成熟的长期记忆检索系统。

建议实现：

- 已完成：将 ChromaDB 刷新从删除重建优化为真实增量 upsert / delete。
- 已完成：支持按 memory type、时间、重要度、任务关联进行 metadata filter。
- 已完成：强化 hybrid scoring：向量相似度、关键词、时间衰减、显著度、任务相关性分别可解释。
- 已完成：引入轻量 rerank，可用 LLM rerank，也可先做可替换的 rerank 接口。
- 已完成：为召回结果增加 citation / source attribution，说明每条上下文来自哪个记忆源。
- 已完成：增加 retrieval eval 指标，固定 query 验证召回命中率、citation 和 filter 覆盖。

验收标准：

- 无 ChromaDB 或无 embedding 配置时仍能降级运行。
- ChromaDB 路径不污染 Git。
- eval 报告中能看到 memory retrieval 指标。
- 前端能看懂为什么某条记忆被注入上下文。

简历亮点：

```text
Implemented a hybrid long-term memory RAG system with incremental vector indexing,
metadata filtering, source attribution, and retrieval quality evaluation.
```

### V2.6 Proactive Supervision Closed Loop

状态：已完成。V2.6.0 已将监督事件生命周期显式整理为状态机，补充 `dismissed` 终态、`transition_history`、最近迁移原因、状态计数和最近迁移摘要，并在 API/前端/eval 中暴露这些闭环信号。V2.6.1 已拆分只读快照与主动推进边界，GET 状态接口不再刷新监督事件，后台 scheduler 和 `/api/scheduler/tick` 负责推进事件与发送通知。V2.6.2 已为自适应提醒策略补充 explanations，记录每条策略建议的反馈证据、影响字段、置信度和是否可应用。V2.6.3 已将屏幕监督提醒改为 transient supervision messages，保持页面可见但不写入长期 `records.json` 或记忆提炼链路。

目标：把主动监督从“能提醒”升级为可解释的闭环状态机。

建议实现：

- 已完成：将任务、承诺、专注会话、屏幕观察和监督事件统一映射到监督状态机。
- 已完成：区分 `detected`、`notified`、`acknowledged`、`snoozed`、`muted`、`resolved`、`dismissed` 等状态，并记录迁移历史。
- 已完成：避免纯读取接口产生监督推进副作用，后台 scheduler 与 `/api/scheduler/tick` 负责主动检查与状态推进。
- 已完成：根据用户反馈动态调整提醒策略，并保留 explainable strategy reasons、反馈证据和影响字段。
- 已完成：屏幕陪伴保持轻量，Vision 提醒只进入 transient supervision messages，不强行写入长期记忆。

验收标准：

- 同一事件不会重复提醒。
- 用户完成、稍后、关闭、静音都能形成明确状态迁移。
- 测试覆盖关键状态迁移。
- API 能返回当前监督状态和最近迁移原因。

简历亮点：

```text
Built a proactive supervision loop that connects task state, focus sessions,
screen observations, reminder policies, and user feedback into an auditable state machine.
```

### V2.7 Packaging & Demo Readiness

状态：已完成。V2.7.0 已加固 `run.sh` 一键启动入口，补充项目根目录检查、端口占用提示、自定义端口方式、依赖安装失败提示和 OpenAPI 文档地址输出。V2.7.1 已新增 demo 数据重置脚本，可备份当前本地数据并写入覆盖任务、RAG、工具展示、监督事件和 transient Vision 提醒的可复现演示状态。V2.7.2 已新增面试架构 walkthrough，覆盖系统架构图、Agent Loop、RAG、工具调用、监督状态机和 3-5 分钟 demo script。V2.7.3 已将 README 首屏改为 reviewer quick view，突出项目定位、技术亮点、demo 路线、证据地图和简历 bullet。桌面包装保留为非阻塞探索项，不影响本阶段验收。

目标：把项目包装成招聘者或面试官可以快速理解、快速运行、快速看到亮点的作品。

建议实现：

- 已完成：优化 `./run.sh` 的环境检查、端口占用提示、浏览器自动打开和错误提示。
- 已完成：准备 demo 数据重置脚本，能一键进入可展示状态。
- 已完成：补充架构图、Agent Loop 图、RAG 流程图、工具调用流程图。
- 已完成：准备一段 3 到 5 分钟 demo script。
- 已完成：README 首页聚焦项目亮点、运行方式、API 文档、评估方式和简历 bullet。
- 可选：探索 PyInstaller + pywebview 或 Tauri + Python sidecar 的桌面包装。

验收标准：

- 全新 clone 后按 README 能跑起来。
- 没有真实 API Key 或私人记忆数据进入仓库。
- Demo 能展示 Agent Loop、RAG、tool calling、Vision supervision、trace/eval。
- 文档能让面试官在 2 分钟内理解项目技术含量。

简历亮点：

```text
Packaged a local-first agent into a reproducible demo with one-command startup,
OpenAPI docs, evaluation reports, and an interview-ready architecture walkthrough.
```

### V2.8 Privacy, Security & Provider Abstraction

状态：进行中。V2.8.0 已完成本地数据清单与安全导出切片，提供隐私清单、可移植 ZIP、manifest、Web 导出入口和路径安全边界。

目标：补齐本地 Agent 项目的隐私与模型供应商工程化能力。

建议实现：

- 已完成：本地数据 inventory 与记忆导出；明确排除 API Key、截图、屏幕观察内容和可重建索引。
- 待完成：受确认保护的记忆删除、选择性删除与完整重置。
- 屏幕截图敏感信息提示或本地过滤。
- LLM / Vision / Embedding / TTS provider 统一抽象。
- API Key 配置检查与启动时诊断。
- OpenRouter、OpenAI、讯飞、Ollama 等 provider 的统一错误分类。

验收标准：

- 用户能查看本地持久化数据范围，并安全导出或删除自己的数据。
- 敏感截图、API Key 与可重建索引不会混入默认导出包。
- Provider 配置、健康状态、错误类型和 fallback 路径能通过统一接口查看。
- 无云端配置时，本地状态读取、数据治理和已有降级路径仍可工作。

简历亮点：

```text
Designed privacy and provider boundaries for a local-first multimodal agent,
including auditable data portability, sensitive-data controls, and unified provider diagnostics.
```

### V2.9 State-centric Hierarchical Memory

状态：已完成首个架构切片。V2.9.0 已建立权威状态、分层 Markdown 长期认知与 episodic RAG 的职责边界。

目标：让记忆系统按 Workmate 的监督用途组织，而不是把所有长期数据都交给模糊检索。

已完成：

- 当前任务、承诺、专注会话和监督状态继续确定性读取。
- 用户、目标、偏好、模式和洞察形成可审阅 Markdown 长期认知层。
- RAG 收紧为历史情景召回，不再索引权威状态与稳定认知。
- 上下文规划按意图选择长期认知，并减少重复上下文块。
- 数据导出纳入 Markdown 长期认知文件。

后续可选增强：为用户手工编辑 Markdown 增加受控合并区，以及为已完成任务生成独立 task episode。

## Goal 模式每轮执行流程

每次 Goal 模式继续推进时，按以下顺序执行：

1. 读取 `CHANGELOG.md`、`README.md` 和本文件，确认当前版本与下一目标版本。
2. 只选择当前推荐版本中的一个最小完整切片，不跨版本发散。
3. 开始修改前检查 `git status --short`，识别用户已有改动和运行缓存。
4. 更新 `CHANGELOG.md`，必要时更新 `README.md` 或相关 docs。
5. 汇报改动文件、验证结果、未解决风险。
6. 若用户要求提交版本，再按正常版本号提交并推送；不要提交运行缓存、密钥或私人数据。

## 当前下一步

下一步回到 V2.8 Privacy, Security & Provider Abstraction，优先补充受确认保护的数据删除/重置，再进入截图敏感信息控制与 provider 抽象。V2.9.0 的记忆边界已完成，不继续扩张为新的存储系统。

不要先做更多提醒文案、语音音色或个人偏好细节。那些会改善体验，但不能明显提升这个项目作为简历 Agent 工程的含金量。
