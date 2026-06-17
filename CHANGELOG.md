## V2.1.5
### 架构调整
- 将屏幕监督从单次 Vision JSON 输出改为“两段式”链路：Vision 只负责结构化观察与偏航判断，语言模型单独负责生成自然提醒
- 移除 Vision 结构化输出中的 `tone_suggestion` 字段，避免把用户可见文案塞进 JSON 模板里
- 新增屏幕提醒表达层：基于 `activity_summary`、`deviation_reason`、`deviation_level` 和 `intervention_hint` 生成最终 `display_message`
- 保留 JSON 作为内部状态管理边界，同时让最终提醒回到自然语言输出，提升工位搭子的真实陪伴感

## V2.1.4
### 调整
- 放宽屏幕提醒的 Vision 提示词，不再要求提醒必须是固定长度、固定语气或“一句话短提醒”
- 保留 JSON 结构化输出用于程序解析，但将提醒文案风格交给模型根据屏幕、目标和偏航程度临场判断
- 明确工位搭子的提醒可以短也可以稍长、可以温柔也可以在明显偏航时更坚定，避免把人格写成固定模板

## V2.1.3
### 调整
- 移除屏幕提醒文案中的硬编码替换表、模板标记列表和本地多样化变体，避免用代码规则制造新的死板感
- 将提醒文案多样化交还给 Vision 模型，通过更明确的 `tone_suggestion` 提示词约束生成自然、短、低压力、非模板化的一句话提醒
- 屏幕提醒事件现在优先尊重模型生成的 `tone_suggestion`；代码仅负责缺失文案时的极短 fallback 与长度控制

## V2.1.2
### 优化
- 优化屏幕监督消息提醒文案，减少“加油 / 方向很对 / 继续顺着 / 围绕某任务推进”等固定模板感
- Vision Prompt 示例改为更短、更像同桌轻声提醒的表达，避免模型继续学习播报腔与固定鼓励句式
- 新增屏幕提醒文案后处理：清理旧称呼、识别模板化句子，并根据偏航/陪伴事件生成多组短提醒变体
- 屏幕事件的具体窗口与活动信息继续保留在结构化 `message` / `metadata` 中，用户可见 `display_message` 更偏轻提醒

## V2.1.1
### 修复
- 修复讯飞 TTS 在 `conda agent` 环境中可能误导入旧版 `websocket` 包导致 `/api/tts/speech` 返回 500 的部署问题
- 为讯飞 TTS 增加依赖冲突诊断提示，要求使用 `websocket-client` 提供的 `create_connection`

## V2.1
### 目标
- 接入讯飞开放平台在线语音合成，让监督事件语音从浏览器系统朗读升级为可选云端 TTS，改善声音自然度

### 已实现
#### 讯飞 TTS Provider
- 新增 `tts/` 模块，提供 `synthesize_speech()` 统一入口和 `XFYunTTSClient` WebSocket 客户端
- 支持讯飞在线语音合成流式 WebAPI：通过 HMAC-SHA256 生成鉴权 URL，发送 base64 文本，拼接返回的 base64 mp3 音频片段
- 新增 `/api/tts/speech` FastAPI 接口，前端可传入短提醒文案并接收 `audio/mpeg`
- `.env.example` 新增 `TTS_PROVIDER`、`XFYUN_TTS_APP_ID`、`XFYUN_TTS_API_KEY`、`XFYUN_TTS_API_SECRET`、`XFYUN_TTS_VOICE` 等配置项
- `requirements.txt` 新增 `websocket-client`

#### 前端语音 Provider
- `SUPERVISION EVENTS` 偏好面板新增 `provider` 选项，支持 `browser` 和 `xfyun`
- 选择 `xfyun` 时，前端调用 `/api/tts/speech` 获取 mp3，并通过 `Audio` 播放
- 讯飞请求失败时自动 fallback 到浏览器 Web Speech，保证提醒链路不中断
- `voice_provider` 纳入监督偏好并自动保存；如果 `.env` 中 `TTS_PROVIDER=xfyun`，默认 provider 会跟随环境配置

#### 测试与验证
- 新增 TTS provider 单元测试，覆盖讯飞 payload 文本编码和 FastAPI TTS 音频响应
- 已使用本地讯飞开放平台认证信息完成真实合成验证，成功生成 mp3 测试音频

## V2.0.2
### 修复
- 修复用户只勾选 `voice` 后刷新页面又恢复关闭的问题：语音相关控件现在会自动保存到 `/api/supervision/preferences`
- 调整语音偏好提示文案，明确语音设置自动保存，其他提醒配置仍通过 `SAVE` 保存

## V2.0.1
### 修复
- 修复语音提醒容易被浏览器通知状态流转错过的问题：监督事件从 `detected` 被标记为 `notified` 后，仍允许在未播报过时补播语音
- 优化 `TEST VOICE` 行为：点击测试语音会自动勾选并保存 `voice` 设置，避免用户只试播或只勾选但没有保存导致后续监督事件无语音
- 在 Preferences 面板补充语音保存提示，说明 `TEST VOICE` 会自动打开并保存语音提醒，其他修改仍使用 `SAVE`

## V2.0
### 目标
- 新增浏览器端语音提醒能力，让监督事件可以通过轻量语音播报触达用户，降低只看页面文字的感知摩擦

### 已实现
#### Web Speech API 语音提醒
- 前端 `SUPERVISION EVENTS` 偏好面板新增语音提醒开关、语音最低播报等级、音量、语速、陪伴事件播报开关和 `TEST VOICE` 测试按钮
- 语音提醒基于浏览器原生 `SpeechSynthesis`，不引入服务端音频依赖、不增加 API 成本，也不影响 `run.sh` 一键启动
- 语音只播报监督事件短文案，优先使用 `display_message`，不会朗读普通聊天回复或整段 Markdown 回复
- 默认关闭语音提醒，避免用户打开页面时突然出声；用户需要主动打开并可用测试按钮确认浏览器支持
- 与现有提醒偏好联动：尊重总开关、静默时段、事件类型开关、事件严重度和 `event_type_min_severity` 覆盖
- 使用 `spoken_supervision_<event_id>` 写入 `localStorage`，同一监督事件在浏览器中只播报一次，避免重复打扰
- 默认不播报 `screen_accompaniment` 低压力陪伴事件，除非用户显式开启陪伴播报

#### 后端偏好持久化
- `SupervisionEventManager` 新增 `voice_enabled`、`voice_min_severity`、`voice_volume`、`voice_rate` 和 `voice_include_accompaniment` 偏好字段
- FastAPI `SupervisionPreferencesRequest` 补齐语音偏好 schema，`/docs` 和 `/openapi.json` 可直接看到语音配置字段
- `event_type_min_severity` 支持新增 `voice` 渠道，方便未来对不同监督事件单独控制语音播报门槛

#### 测试
- 新增语音偏好归一化与持久化测试，覆盖音量、语速边界和 voice 渠道事件类型覆盖

## V1.10
### 目标
- 将 Web 后端从手写 `http.server` 路由升级为 FastAPI，提升 API 工程化、可展示性和后续扩展能力

### 已实现
#### FastAPI + OpenAPI
- `src/web.py` 改为 FastAPI ASGI 应用，保留 `WorkmateWebApp` 作为业务编排层，避免影响 Agent Runtime、记忆系统和监督事件核心逻辑
- 保留现有前端依赖的 `/api/chat`、`/api/memory`、`/api/context`、`/api/dashboard`、`/api/focus`、`/api/task/update-status`、`/api/supervision/events`、`/api/supervision/preferences`、`/api/notify/status` 和 `/api/notify/test` 接口契约
- `/api/chat` 继续使用 `text/event-stream` 流式输出，前端无需改变现有 SSE 解析逻辑
- 新增 Pydantic 请求模型，用于聊天、专注会话、任务状态、监督事件和监督偏好配置接口的参数声明
- 自动提供 `/docs`、`/redoc` 和 `/openapi.json`，方便在简历展示、接口调试和后续客户端接入时说明系统边界
- 保留 `python -m src.web` 一键启动方式，并在 `run_web()` 中直接传入 FastAPI app，避免字符串导入导致后台 scheduler 被重复初始化

#### 文档与测试
- `requirements.txt` 新增 `fastapi` 和 `uvicorn`
- `README.md` 补充 FastAPI API 文档入口和可选 `uvicorn` 启动方式
- `tests/test_web_api.py` 改为使用 FastAPI `TestClient`，并新增 `/openapi.json` smoke test
- `pytest` 全量 26 项测试通过

## V1.9
### 目标
- 升级智能屏幕监督系统，支持温和陪伴跟进、状态转换自动解决、免控制权限弹窗以及可视化参数配置

### 已实现
#### 智能屏幕监督系统
- **陪伴鼓励提醒 (`screen_accompaniment`)**：新增类型为 `screen_accompaniment`、严重度为 `low` 的陪伴提醒事件。当用户正在白名单应用正常工作时，Agent 在对话历史中默默插入鼓励消息（如提醒喝水、温和鼓励等），在不打扰用户的前提下提升陪伴感。对于灰色地带应用，结合多模态截图及当前任务，由 Vision 大模型根据当前情绪设定比例动态生成极低压力的温暖陪伴语。
- **状态机自动双向解决 (Auto-resolution)**：优化监督事件的自动流转。当用户从“专注于正常工作”转为“娱乐偏航”时，之前的 `screen_accompaniment` 事件自动标记为 `resolved`（已解决），并检测出新的 `screen_deviation`；反之，当用户从“偏航”回归到“专心工作”时，原有的 `screen_deviation` 自动解决，并产生新的陪伴事件。
- **多模态分离 API 支持**：在 `.env` 与 `src/LLMClient.py` 中新增 `VISION_MODEL_ID`、`VISION_API_KEY`、`VISION_BASE_URL` 配置。若主语言模型不支持多模态，可单独配置第三方 Vision API 实施屏幕截图分析，节省主 API 成本。
- **免 App 控制权限弹窗优化**：重构 AppleScript 系统交互，使用 `System Events` 的 `frontmostProcess` 探测活跃窗口，在 macOS 下仅需一次性授予“辅助功能”权限，后续切换到任何新软件都绝对不会触发频繁控制弹窗，保证极佳体验。
- **自定义黑/白名单过滤**：前端新增自定义黑名单/白名单关键词输入，逗号分隔，比对活跃窗口具有最高优先级，命中时直接拦截/放行，**绕过 Vision 多模态模型**，实现零延时和零 API 扣费。
- **前端偏好设置面板**：在 Web 页面的 "SUPERVISION EVENTS" 标题右侧增加 `⚙️ 配置` 折叠/展开按钮。支持可视化配置屏幕监测开关、冷却时间（测试阶段硬编码强制 1 分钟）、工作时间自动激活及时间起止范围、自定义黑白名单关键词。
- **中转 API 防火墙伪装与绕过**：针对官方 OpenAI SDK 流量易被部分中转 API 站（如 `ccapi.us`）的 Cloudflare / WAF 防火墙误杀拦截（报错 `Your request was blocked`）的问题，在 [src/LLMClient.py](file:///Users/joey/01 Projects/实习/workmate-agent/src/LLMClient.py) 中重构了客户端初始化逻辑，强制注入标准的 macOS 浏览器 `User-Agent` 请求头成功实施伪装绕过，实现充值账户高可用。
- **检测逻辑优先级优化**：配置大模型时，检测始终**优先调用 Vision 多模态模型**分析屏幕内容，生成高度定制化、情境相关的陪伴跟进或偏航警报文案，而将本地白名单/黑名单仅作为免配大模型/网络异常时的无缝降级（Fallback）防线；同时扩展默认白名单以屏蔽 Agent 看板自身的误识别。
- **单元测试与防抖时间 Mock 优化**：同步调整 [tests/test_screen_monitor.py](file:///Users/joey/01 Projects/实习/workmate-agent/tests/test_screen_monitor.py) 以支持优先级变更和无 API 降级拦截覆盖；解决了测试由于系统当前真实时间与 patch 时间冲突导致的负差时间防抖拦截漏洞。运行 `pytest` 所有 26 项单元测试全部通过。

## V1.8
### 目标
- 将项目从个人原型进一步提升为可验证工程项目
- 引入 pytest 与 GitHub Actions，让核心 Agent 模块可以自动化验证

### 已实现
#### Pytest 测试体系
- 新增 `pytest.ini`
- `requirements.txt` 新增 `pytest`
- 新增 `tests/conftest.py`，提供使用临时目录的 `tmp_memory_manager` fixture，避免测试写入真实 `memory/data`
- 现有 unittest 风格测试继续可被 pytest 收集运行

#### 核心模块测试覆盖
- 新增 `tests/test_memory_pipeline.py`，覆盖记忆流水线阶段契约和端到端写入流程
- 新增 `tests/test_context_planner.py`，覆盖任务、周报和低能量支持性知识上下文规划
- 新增 `tests/test_task_lifecycle.py`，覆盖任务创建、子任务和状态流转
- 新增 `tests/test_supervision_events.py`，覆盖监督事件检测、确认、稍后、关闭和提醒策略建议
- 新增 `tests/test_web_api.py`，覆盖 Web `/api/context` 与 `/api/memory` smoke test
- V1.5/V1.6 的 memory retriever 与 tool executor 测试继续保留

#### CI
- 新增 `.github/workflows/ci.yml`
- CI 运行 Python 3.12
- CI 步骤包括依赖安装、Python syntax check、`pytest`、`evals/run_eval.py` smoke test
- eval 报告输出到 `/tmp/workmate-eval-reports`，不污染仓库

## V1.7
### 目标
- 为 Agent 项目补齐可复现评估体系
- 支持无真实 API Key 的 rule / fake LLM 模式，方便本地和后续 CI 运行

### 已实现
#### Evaluation Suite
- 新增 `evals/`
- 新增 `evals/cases.json`，内置 24 条固定评估用例
- 新增 `evals/run_eval.py`，支持直接运行评估并输出报告
- 评估报告会输出到 `evals/reports/`，同时生成 JSON 和 Markdown 两种格式
- `evals/reports/*.json` 和 `*.md` 默认不提交，避免时间戳报告污染版本库

#### 评估覆盖
- `intent_accuracy`：意图识别准确率
- `memory_recall`：长期记忆召回命中率
- `task_tracking`：任务状态更新正确性
- `commitment_extraction`：承诺新增、关闭和 deadline 识别
- `reminder_control`：自然语言提醒控制
- `tool_calling`：工具调用正确性、只读/写状态和最大调用次数
- `context_planning`：上下文规划是否注入必要模块
- `supervision_lifecycle`：监督事件检测、确认、稍后和关闭状态流转

#### 运行方式
- `conda run -n agent python evals/run_eval.py`
- 支持 `--cases`、`--report-dir` 和 `--min-score`
- 默认 `--min-score 1.0`，适合作为后续 CI smoke test 的基础

## V1.6
### 目标
- 将内部状态工具调用升级为可观察、可测试、可审计的 Agent tool-use 模块
- 明确每个工具的输入输出 schema、只读/写状态边界和副作用

### 已实现
#### Schema-driven Tools
- `ToolSpec` 新增 `output_schema`、`side_effects`、`read_only`
- `ToolRegistry.register()` 保持兼容原有参数，同时支持补充工具输出和副作用信息
- 新增 `ToolRegistry.export_schemas()`，可独立导出所有工具 schema
- Workmate 内部工具补齐输出 schema 和读写边界，包括任务、承诺、记忆检索、记忆备注和专注会话工具

#### Tool Trace
- `ToolExecutor.execute()` 统一记录 `call_id`、`reason`、`duration_ms`、`read_only`、`side_effects`、`input_schema`、`output_schema`
- 工具规划失败会返回 `__tool_planning__` error trace，而不是静默吞掉错误
- 工具 handler 异常继续被隔离在单条工具结果中，不中断整轮对话
- 每轮最大工具调用次数继续由 `max_calls` 控制

#### Web/API 可观察性
- `WorkmateAgent.get_tool_schemas()` 暴露工具 schema
- `/api/chat`、流式 done 事件、`/api/memory` 和 `/api/context` 返回 `tool_schemas`
- Web 左侧工具摘要展示读写模式、耗时和副作用
- `MODEL CONTEXT` 顶部新增 `TOOL TRACE` 区块，展示工具调用状态、耗时、原因、错误和副作用

#### 测试
- 新增 `tests/test_tool_executor.py`
- 覆盖工具 schema 导出、任务状态写工具、承诺只读工具、记忆检索工具、专注会话工具、规划失败隔离和最大调用次数限制

## V1.5
### 目标
- 将长期记忆检索升级为可解释的 Hybrid Memory RAG
- 让记忆召回覆盖更多内部状态，并在 Web 调试台展示召回原因

### 已实现
#### MemoryRetriever
- 新增 `memory/retriever.py`
- 引入 `MemoryRetriever`，统一计算 keyword、recency、salience、type weight 和可选 vector score
- 每条检索结果返回 `source_type`、`source_id`、`score`、`reason` 和 `score_breakdown`
- 向量检索通过 `WORKMATE_VECTOR_RETRIEVAL` 可选启用；未配置 embedding client 时自动降级为非向量 hybrid scoring

#### 检索来源扩展
- `SearchManager` 保持原有调用方式，但内部委托 `MemoryRetriever` 评分
- 检索索引新增覆盖 `tasks` 和 `behavior_patterns`
- 原有 conversation records、memory_items、memory_categories、commitments、high_level_insights、semantic_dialogues 等来源继续保留
- `MemoryManager.refresh_search_index()` 会把任务生命周期和行为模式同步纳入索引

#### Retrieval Plan 可观察性
- `retrieval_plan` 新增 `mode`、`vector_status`、`top_results` 和每条结果的评分拆解
- `MODEL CONTEXT` 顶部展示 RAG 检索计划、召回结果、分数与原因，方便判断本轮上下文为什么注入某些记忆
- `/api/chat` 流式完成后的 `context` 会携带本轮 prompt 对应的 `retrieval_plan`

#### 测试
- 新增 `tests/test_memory_retriever.py`
- 覆盖相关任务记忆排序、向量未启用时的降级状态、任务和行为模式索引构建
- 测试使用临时目录，不写入真实 `memory/data`

## V1.4
### 目标
- 将现有“上下文规划、内部工具调用、模型回复、记忆写回”流程显性化为可观察的 Agent Runtime
- 让项目从 API 聊天窗口进一步升级为具备清晰 Agent Loop 和运行轨迹的工程项目

### 已实现
#### Agent Runtime
- 新增 `agent/runtime.py`，封装单轮 Agent 执行流程
- 每轮统一生成 `turn_id`，并记录 `started_at`、`completed_at`、`duration_ms`、`status` 和 `streaming`
- 执行阶段拆分为 `apply_reminder_control`、`plan_context`、`execute_tools`、`generate_response`、`write_memory`、`update_supervision_state`
- 每个阶段记录状态、耗时、摘要 metadata 和错误信息，用于观察 Agent Loop 是否正常执行
- `src/core.py` 改为委托 `AgentRuntime` 执行，保留原有 `WorkmateAgent.invoke()`、`invoke_stream()`、CLI 行为

#### Turn Trace
- 将原有 `last_context_messages`、`last_tool_calls`、`last_pipeline_result` 整合为统一的 `turn_trace`
- `turn_trace` 记录上下文消息数、上下文估算、工具调用结果、工具观察、记忆写回结果和回复摘要
- 新增 `WorkmateAgent.get_last_turn_trace()`，方便 Web/API 读取最近一轮运行轨迹
- trace 只暴露执行过程，不记录或展示模型隐藏推理链

#### Web/API 可观察性
- `/api/chat`、流式 done 事件、`/api/memory` 和 `/api/context` 均返回最近一轮 `turn_trace`
- Web 左侧 `MEMORY` 面板新增 `runtime` 字段，展示 turn id、执行状态、耗时、消息数量和主要阶段
- 保持原有 `tool_calls`、`MODEL CONTEXT` 和记忆调试信息不变

## V1.3
### 目标
- 让主动提醒策略开始参考用户反馈，而不是所有提醒长期使用同一套强度
- 保持用户可控：系统只给策略建议，不在后台悄悄改变提醒边界

### 已实现
#### 提醒策略建议层
- `SupervisionEventManager.build_state()` 新增 `strategy`
- 策略层会基于 `feedback_stats` 分析用户更常确认/关闭提醒，还是更常稍后/静音提醒
- 当用户多次选择 `snoozed` 或 `muted` 时，会建议提高 `push_min_severity` 或延长默认稍后提醒间隔
- 当用户近期更常确认或关闭提醒，且当前推送门槛过高时，会建议把 `push_min_severity` 从 `high` 调回 `medium`
- 策略层会输出 `recommendations`、`preference_updates` 和按事件类型统计的 `type_friction`

#### 压力感知语气策略
- `strategy` 新增 `tone_policy`
- 复用支持性知识层识别到的 `anxious / tired / avoidant / stuck / scattered / overplanning` 等状态，自动建议降低监督语气
- 深夜或清晨等休息时段会进入 `soften` 策略，提示模型只做状态确认和一个很小的提示，不追问、不催促、不展开长建议
- 前端 `APPLY STRATEGY` 会同时合并普通策略建议和语气策略建议，例如把 `reminder_strength` 调整为 `soft`、把 `push_min_severity` 调整为 `high`
- 语气策略进入模型上下文，用于减少用户低能量状态下的压力感

#### 个性化提醒文案
- `strategy` 新增 `copy_policy`
- 监督事件刷新时会读取长期用户画像中的 `communication_preference` 和 `effective_interventions`
- 根据“先帮用户记住和整理”“低压力回应”“只给一个小建议”“不要要求证明”等偏好，为事件生成用户可见的 `display_message`
- 原始 `message` 继续保留用于结构化调试，Web 事件卡片、浏览器通知和后台推送优先使用 `display_message`
- 模型上下文会标注当前提醒文案策略，避免监督事件在低压力偏好下显得生硬

#### 分渠道提醒门槛
- 提醒偏好新增 `page_min_severity`、`browser_min_severity` 和 `background_min_severity`
- 保留 `push_min_severity` 作为兼容字段，并映射到浏览器通知门槛
- 页面内监督事件列表按 `page_min_severity` 过滤，默认仍显示低优先级事件
- 浏览器 Notification API 使用 `browser_min_severity`，默认从中等级事件开始弹出
- 后台常驻推送使用 `background_min_severity`，默认只推送高优先级事件，减少 macOS/Bark/飞书等渠道的打扰
- 自适应策略和自然语言控制会同步更新浏览器/后台门槛，例如“今天安静一点”会把两个主动推送渠道都调到 `high`

#### 事件类型反馈策略
- 提醒偏好新增 `event_type_min_severity`
- 策略层会根据 `feedback_stats.by_type` 观察不同监督事件类型的反馈，例如 `focus_expired`、`task_stale`、`commitment_due_today`
- 如果某类提醒更常被 `snoozed` 或 `muted`，策略会只提高这一类事件的浏览器/后台门槛，而不粗暴降低所有提醒
- 如果某类提醒更常被确认或关闭，策略会允许这一类事件保持中等级浏览器提醒
- 前端策略卡片新增 `type_preference_signals` 展示，让用户点击 `APPLY STRATEGY` 前能看到是哪类提醒触发了调整

#### 自然语言提醒控制
- 新增 `SupervisionEventManager.apply_natural_language_control()`
- `WorkmateAgent` 在构建上下文前会先识别用户输入中的显式提醒控制短语
- 支持“今天安静一点”“今天别提醒”“暂停提醒”“恢复提醒”“只提醒承诺”“只提醒专注”“只提醒任务”“提醒全部”“少提醒”“多提醒”等轻量控制
- V1.3 后续增强为 LLM 优先分类、规则兜底：当输入看起来像提醒/通知/推送控制时，会先调用 `LLMClient.invoke_raw()` 识别意图和安全偏好更新
- LLM 输出只允许白名单字段生效，包括启停提醒、三类渠道门槛、默认稍后分钟数和事件类型开关；置信度不足或 JSON 不合法时自动回退到规则短语
- 新增偏好字段 `quiet_until`，用于支持“今天安静一点”这类临时静音，不需要关闭整个监督系统
- `/api/memory` 和 `/api/context` 暴露 `last_reminder_control`，方便调试最近一次自然语言控制是否生效

#### Web 交互
- `SUPERVISION EVENTS / PREFERENCES` 区域新增 adaptive reminder strategy 卡片
- 前端展示当前策略模式、推荐改动和事件类型摩擦说明
- 前端会展示自然语言临时静音状态，例如安静到当天几点
- 新增 `APPLY STRATEGY` 按钮，用户点击后才会把推荐值写入提醒偏好
- 保持原有手动偏好设置不变，策略建议只是辅助用户调整提醒强度

## V1.2
### 目标
- 让用户打开页面后，不需要翻聊天记录就能看到当前主线、今日进展和本周节奏
- 把任务、专注、承诺、监督事件和行为模式聚合成一个低压力行动仪表盘

### 已实现
#### 个人自律仪表盘
- 新增 `DashboardManager`
- 新增 GET `/api/dashboard`
- `/api/memory` 和 `/api/context` 暴露 `dashboard`
- 仪表盘聚合今日专注次数/分钟数、今日完成任务、今日关闭承诺、未关闭承诺、到期承诺、活跃监督事件、当前主线、任务分散度、本周专注分钟、本周完成任务、本周活跃天数和承诺履行率
- 仪表盘生成一条轻量 `gentle cue`，只用于帮助用户回到主线，不做评分或压力提示

#### Web 交互
- `EXECUTION` 面板顶部新增 `TODAY DASHBOARD`
- 展示 `today focus`、`today done`、`open loops`、`mainline`、`week rhythm`、`load` 和 `gentle cue`
- 新增快速操作按钮：`FOCUS` 使用当前主线开启专注，`DONE` 完成当前主线，`REMINDERS` 滚动到监督事件区域
- `ContextPlanner` 在任务、监督、复盘和周报场景注入 dashboard 摘要，让模型回复更贴近用户当前行动状态

## V1.1
### 目标
- 从“发生了什么提醒”推进到“用户经常怎样行动”
- 让 Agent 能根据任务、专注、承诺和监督事件识别长期行为模式，但不做心理诊断或人格标签

### 已实现
#### 行为模式分析
- 新增 `BehaviorPatternManager`
- 新增运行时文件 `memory/data/behavior_patterns.json`
- 基于本地 JSON 数据分析专注完成率、专注超时、承诺积压、承诺履行率、任务分散、任务停滞和提醒反馈摩擦
- 每个行为模式包含 `title`、`summary`、`tone`、`severity`、`frequency`、`evidence` 和 `suggested_intervention`
- 行为模式只作为观察线索进入上下文，提示 Agent 在相关时给一句轻量建议，不把单次行为当成长期结论

#### 上下文与 Web
- `MemoryManager` 每轮派生记忆后刷新行为模式
- `ContextPlanner` 在任务、监督、复盘和周报场景注入 `behavior_patterns`
- `/api/memory` 和 `/api/context` 暴露 `behavior_patterns`
- Web 的 `MEMORY` 面板新增 `patterns` 字段，展示当前最相关的行为模式

## V1.0
### 目标
- 启动主动监督闭环建设
- 将专注超时、承诺到期、任务停滞等提醒从临时判断升级为可追踪的监督事件
- 为后续“确认、静音、关闭、稍后提醒”等用户可控监督策略打基础

### 已实现
#### 统一监督事件模型
- 新增 `SupervisionEventManager`
- 新增运行时文件 `memory/data/supervision_events.json`
- 支持事件状态：`detected / notified / acknowledged / snoozed / resolved / muted`
- 支持 `snoozed` 稍后提醒状态，到期后自动重新变为 `detected`
- 支持监督事件类型：专注会话超时、承诺今日到期、承诺逾期、当前任务久未更新
- 同一事件使用 `dedupe_key` 去重，避免短时间重复生成和重复推送
- 当对应问题不再存在时，活跃事件会自动转为 `resolved`
- 监督事件记录 `feedback_history` 和 `linked_updates`，用于追踪用户如何处理提醒，以及 DONE 是否同步影响了关联对象

#### 状态联动
- 用户对专注超时事件执行 `DONE` 时，会尝试同步完成当前专注会话
- 用户对承诺今日到期或逾期事件执行 `DONE` 时，会尝试同步关闭对应承诺
- 用户对当前任务久未更新事件执行 `DONE` 时，会尝试同步将对应任务标记为完成
- 关联对象已经不存在或不再是当前对象时，不会报错中断，而是把跳过原因写入事件的 `linked_updates`

#### 提醒偏好
- 新增运行时文件 `memory/data/supervision_preferences.json`
- 支持总开关、默认稍后提醒分钟数、默认静音小时数、静默时段、最低提醒严重程度
- 支持 `push_min_severity`，低严重度事件可以只进入页面，不触发桌面或后台推送
- 支持按事件类型启停提醒：专注、承诺、任务停滞
- 后台 scheduler 和浏览器桌面通知都会尊重提醒偏好；事件仍会记录，但不一定主动推送

#### 后台调度与 API
- `WorkmateWebApp` 的后台 scheduler 改为先刷新监督事件，再只对 `detected` 状态事件发送推送，并将其标记为 `notified`
- `/api/memory`、`/api/context` 暴露 `supervision_events`
- 新增 GET `/api/supervision/events` 刷新并读取监督事件
- 新增 POST `/api/supervision/events`，支持 `acknowledge`、`snooze`、`mute`、`resolve`、`mark_notified`
- 新增 GET/POST `/api/supervision/preferences`，用于读取和保存监督偏好
- 修正推送自检读取的环境变量名：Bark 使用 `BARK_KEY`，飞书使用 `LARK_WEBHOOK_URL`

#### Web 交互
- `EXECUTION` 面板新增 `SUPERVISION EVENTS`
- 用户可以在前端对监督事件执行 `SNOOZE`、`ACK`、`MUTE`、`DONE`
- `SUPERVISION EVENTS` 面板新增提醒偏好设置：启用状态、默认稍后分钟数、推送最低等级、静默时间段、专注/承诺/任务提醒开关
- `SUPERVISION EVENTS` 面板展示反馈统计，方便观察用户是更常确认、稍后提醒、静音还是关闭事件
- 浏览器桌面通知改为基于统一监督事件触发，而不是分别读取 focus session 和 commitments 裸数据

## V0.9.2
### 目标
- 优化任务提取阶段的匹配算法，解决因语序颠倒、多余助词或修饰语引起的 TODO LIST 重复任务提取问题。

### 已实现
#### 任务匹配去重升级
- **Jaccard 相似度算法匹配**：在 `TaskManager` (`memory/task_manager.py`) 中升级了 `_same_task`。除了精确匹配和子串匹配外，新增了基于 Jaccard 相似度匹配逻辑，以大于等于 `0.5` 相似度判定为同一任务并执行更新去重。
- **语义 Token 切词器**：新增 `_get_semantic_tokens` 辅助方法，使用正则提取所有英文单词/数字，并将中文拆分为汉字级别 Token，同时剔除常用的中文虚词、助词及代词（如：`的, 了, 和, 与, 在, 于, 是`），生成特征集合。
- **广泛的去重测试覆盖**：成功解决 `"LLM wiki的实现"` 与 `"实现LLM wiki"` 等倒装中英文混排情况，以及 `"学习了解现有Agent框架"` 与 `"了解现有Agent框架"` 等同义修饰情况下的任务重复合并。

## V0.9.0
### 目标
- 在左侧栏的 `🎯 EXECUTION` 面板中新增可视化待办列表（Todo List），实现“用户说出计划安排 -> 模型自动提炼任务并同步展示在列表中 -> 用户点击复选框标记完成/重新激活 -> 数据实时双向同步”的完整任务闭环。

### 已实现
#### 任务管理器与状态一致性同步
- **核心逻辑改造**：在 `TaskManager` (`memory/task_manager.py`) 中新增 `update_task_status(task_id, status)` 方法，实现对单项任务状态的持久化更新，自动设置 `completed_at`/`abandoned_at` 时间戳，并在父任务标记为 `done`/`abandoned` 时，自动将其下所有未完成的子任务标记为对应的状态。
- **状态一致性保证**：在 `TaskState` (`memory/task_state.py`) 中联动 `TaskStateManager`，当被修改的任务是当前的活跃任务（Active Task）时，自动同步将 `task_state.json` 中的状态、当前进度和更新时间戳置为一致，同时向 `task_events.json` 写入 `status_changed` 状态流转事件（标注 `via: "web_ui"`）。

#### Web API 支持
- **同步更新接口**：在 `src/web.py` 中新增 POST `/api/task/update-status` 接口，接收任务 ID 和新状态，调用底层同步修改后，返回最新的 `task_view`、`memory` 和 `context` 状态字典。

#### 前端 GUI 待办列表可视化
- **任务待办面板 HTML/CSS**：在左侧栏 `🎯 EXECUTION` 选项卡中新增 `TODO LIST` 卡片面板。为其编写了完美融入“复古手账/记账本”风格的 Vanilla CSS（包含复古卡片阴影、圆角、苔绿色打勾复选框、已完成任务的朱砂红删除线样式）。
- **动态渲染与交互逻辑**：
  - 合并展示 `taskView.active` 与 `taskView.recent_completed` 的所有待办事项，按状态（`active`, `blocked`, `planned`, `inbox`）渲染对应的半透明高对比度色彩徽章，同时友好格式化展示其最近更新时间（`MM-DD HH:MM`）以及其子任务完成进度（如 `子任务: 2/3`）。
  - 实现点击复选框或条目的 toggle 动作：自动请求后端 `/api/task/update-status` 修改状态并驱动整个 Web 页面数据流的重新加载，达成瞬间同步。

## V0.8.6
### 目标
- 专注于系统交互与体验层面优化，全面美化 Web 调试界面（支持 Markdown 表格、代码高亮、一键复制），并新增推送通道连接状态自检与测试面板，提升可用性与调试效率。

### 已实现
#### 后台 API 增强
- **配置与测试接口**：在 `src/web.py` 中新增 GET `/api/notify/status` 获取已启用的通知通道（macOS 原生弹窗、Bark 推送、飞书 Bot）及其参数配置状态，新增 POST `/api/notify/test` 触发测试推送并返回响应结果，方便随时验证推送连通性。

#### 前端 Web 调试界面重构与美化
- **渲染器升级**：引入 `marked.js` 和 `Prism.js` (Okaidia 主题) CDN，替换了原有的手写 Markdown 解析器，实现 100% 完美的 GFM Markdown 渲染，全面支持多级嵌套列表和语法高亮。
- **表格与代码块美化**：
  - 设计并适配了优雅的表格样式（浅色边框与斑马纹底色），使周报数据概览表格清晰精美。
  - 为所有代码块增加了悬浮显示的 `COPY`（一键复制）按钮，并提供防重与成功 Toast 状态。
- **系统配置与推送自检折叠面板**：
  - 在侧边栏底部新增了「SYSTEM CONFIG & PUSH TEST」折叠面板。
  - 支持动态展示本地弹窗、Bark 推送、飞书机器人的启用与配置状态（通过绿色/红色指示灯标识）。
  - 集成了「发送测试通知 🔔」交互按钮，一键发送测试通知并获取即时反馈。
- **平滑滚动优化**：对聊天内容区域 `.transcript` 开启 CSS `scroll-behavior: smooth`，使流式 Delta 响应追加时的滚动效果极其丝滑自然。

## V0.8.5
### 目标
- 实现周度自律诊断与“偏航/拖延”模式报告（Weekly Review），当用户提出“生成周报”、“周度复盘”等诉求时，系统会深度汇总过去 7 天的专注会话状态、承诺履约表现以及长期画像，为用户生成一份具有“成长性思维”且极具诊断价值的 Markdown 总结。

### 已实现
#### 意图分类与上下文规划更新
- **意图分类器支持 `"weekly_report"`**：在 `IntentManager`（`memory/interpreter.py`）中新增合法意图 `"weekly_report"`，在规则分类器中增加“周报、周复盘、每周总结、每周回顾、本周总结、本周复盘”等关键字检测，并更新了大模型意图分类的 Prompt 提示词与 JSON schema，确保能准确识别用户的周报/周复盘请求。
- **上下文规划器更新**：`ContextPlanner` (`memory/context_planner.py`) 在 `required_context_keys` 中加入 `"weekly_report"` 处理分支，智能规划并延伸引入 `"weekly_report_data"`, `"high_level_insights"`, `"behavior_stats"`, `"commitments"`, `"reflections"` 等必要上下文数据块。

#### 周度数据汇总与回复策略指引
- **新增周报数据提取与回复指引**：`BehaviorStatsManager` (`memory/stats.py`) 中新增 `format_weekly_review_context(memory_manager)` 方法，动态计算过去 7 天专注会话（次数、完成、超时、放弃、总时长、平均时长、完成率）、承诺履行（新增、关闭、履行率、逾期遗留）及活跃打卡情况，并附加 【Agent 回复策略指引】。
- **无交互摩擦的回复策略**：在回复指引中，指导 Agent 撰写温暖、亲和、具有成长性思维的【周度自律诊断报告】（包含数据概览表格、注意力诊断、长期拖延预警和下周自律指南等模块），且要求以纯自然语言/Markdown 流畅收尾，默认不以问句结尾，避免给用户造成打扰。

#### 上下文加载与加载流集成
- **上下文引擎对接**：`ContextEngine` (`memory/context_engine.py`) 在 `load_context_blocks` 中补全了对 `"weekly_report_data"` 键的解析，并在加载上下文时通过调用 `stats_manager.format_weekly_review_context` 组装对应的数据块并注入到大模型的上下文提示中。

## V0.8.4
### 目标
- 脱离网页一直打开的限制，实现后台守护线程常驻调度和多通道通知（Mac系统弹窗 / iOS手机推送 / 飞书机器人），降低交互摩擦并强化主动陪伴能力

### 已实现
#### 后台推送模块
- 新增 `Notifier` 推送模块（`memory/notifier.py`），封装了三类推送渠道：
  - **Local macOS Native Alert**：使用 `subprocess` 调用 macOS AppleScript 原生通知弹窗，免三方库安装。
  - **Bark Push**：发送 HTTP GET 请求，直接推送通知到用户 iOS 手机上，点击可跳转。
  - **Lark/Feishu Webhook**：通过飞书自定义群机器人 Webhook 以 JSON POST 请求形式推送卡片信息。
- 提供配置化设计，用户可通过修改 `.env` 决定启用哪些通知通道（如 `PUSH_CHANNELS=local,bark`）并配置对应的 Key/Webhook。

#### 后台守护线程与状态监控 (Scheduler)
- 在 Web 服务类 `WorkmateWebApp` 载入时自动开启一个 `daemon` 守护线程作为后台调度器，每 60 秒执行一次全自动状态检查。
- **专注超时监测**：自动检测进行中或超时的 focus session。一旦超时，立即触发推送。
- **承诺到期监测**：自动检测所有 open 状态的承诺，如果在今天到期或已经逾期，触发推送。
- 后台自主维护已通知 focus session ID 和 commitment 每日通知 Key（`id_date`），防范重复弹窗打扰。

## V0.8.3
### 目标
- 实现浏览器桌面主动弹窗通知，强化自律监督并降低用户交互负担

### 已实现
#### 桌面主动通知
- 前端自动检测并请求浏览器 `Notification` API 权限
- 实现 `checkAndNotify` 桌面提醒逻辑，集成于 1 分钟的前端数据轮询流水线中
- 支持专注会话超时提醒：当专注状态为 `expired` 时触发弹窗
- 支持承诺到期/逾期提醒：当存在今天到期或已逾期的 open 承诺时触发弹窗
- 引入本地防重复打扰机制，利用 `localStorage` 记录已通知的会话 ID 以及承诺当天已通知状态，避免重复触发弹窗

## V0.8.2
### 目标
- 感知时间间隔、今日对话状态和下班收工行为，为用户回归、早晨开启和晚间收工提供更柔和、具有情境感的自适应反馈策略

### 已实现
#### 首次对话早间简报 (C)
- `BehaviorStatsManager` 新增 `is_first_message_today()`，判断当前对话是否为今天首次交流
- 新增 `format_morning_briefing()` 格式化组件：汇总昨日遗留承诺、今天到期/逾期承诺、今日主线任务、本周专注及承诺统计指标，并提供温和问候与轻量启动建议的 Agent 回应指引
- 在 Context 规划中动态引入 `morning_briefing` 数据块

#### 纯自然语言晚间总结复盘 (C)
- `BehaviorStatsManager` 新增 `format_evening_review()`：在傍晚/夜间时间段，当检测到用户输入包含“下班/收工/走啦/明天见”等收工意向时，自动开启晚间总结复盘
- 动态汇总今日累计完成专注次数、累计时长、今日关闭承诺、当前卡点阻塞项目，并注入上下文引导指令
- 约束 Agent 以纯自然语言（不带表格、列表或分隔符）流畅温暖地对今天的工作进行总结复盘并告别，严禁提问，实现无交互摩擦的轻量自然收尾

#### 间隔与专注超时感知 (B)
- `BehaviorStatsManager` 新增 `get_conversation_gap_minutes()` 计算对话静默时长
- 新增 `format_gap_context()` 格式化组件：当两次对话间隔超过 30 分钟或当前专注会话超时，向上下文注入具体的静默间隔与超时时间，指引 Agent 更加人性化地询问进展或引导继续话题
- 在 Context 规划中动态引入 `gap_context` 数据块

## V0.8.1
### 目标
- 基于 V0.8 的专注会话和时间感知数据，补全"有量化数据"和"有时间情境"两层能力
- 让承诺追踪真正具备时效性，不再只是文字记录
- 把工具层与专注会话打通，降低会话操作摩擦

### 已实现
#### 承诺 Deadline 感知
- `CommitmentManager` 新增 `_extract_deadline()`，从承诺文本中用关键词规则提取 deadline
- 支持识别：今天/今晚/今日、明天/明日、后天、这周/本周/周末、下周
- 每条新承诺自动写入 `deadline` 字段（ISO 8601 格式）
- `format_for_context()` 展示时标注 `[⚠ 已逾期]`、`[今天到期]`、`[截止 MM/DD]`
- `SupervisionManager` 新增 `overdue_commitment`（medium）和 `due_today`（low）两类监督信号，优先于泛化承诺提醒触发

#### 行为统计层
- 新增 `BehaviorStatsManager`（`memory/stats.py`）
- 实时从已有 JSON 文件计算，不新增存储文件
- 统计维度：专注会话完成率和累计时长、承诺本周履行率、连续活跃天数
- 上午和傍晚对话、用户触发 `review` 意图时，行为统计自动注入上下文

#### 时间情境感知
- `ContextPlanner` 新增 `time_period()` 方法，按时段返回 `morning / afternoon / evening / night`
- `time_context` 成为基础上下文块（每次对话都注入），包含当前时段、今日专注情况和 Agent 应对策略提示
- 深夜（23:00–06:00）自动屏蔽 `supervision` 信号，避免在休息时段加压
- 上午和傍晚额外注入 `behavior_stats`，支持更具体的启动和收束建议

#### 工具层接入专注会话
- `tools/workmate_tools.py` 新增三个工具：`start_focus_session`、`complete_focus_session`、`abandon_focus_session`
- AI 在对话中判断用户明确说"去做某事"时可直接启动专注会话，无需用户手动操作 UI
- 工具描述内置触发约束，避免在普通聊天或计划讨论中误触发
- `complete` / `abandon` 在无进行中会话时返回 `{completed: false}` 而非报错

## V0.8
### 目标
- 从“被动等待用户汇报”迈向轻量主动陪伴的第一步
- 增加专注会话状态，让 Agent 理解用户离开对话后的执行片段
- 建立基础时间间隔感知，为后续主动监督和提醒能力铺底

### 已实现
#### 专注会话
- 新增 `FocusSessionManager`
- 新增 `memory/data/focus_sessions.json`
- 支持开始、完成、停止当前专注会话
- 记录专注目标、计划分钟数、开始时间、预计结束时间、结束时间、实际经过分钟数和结果状态
- 进行中的会话超过预计结束时间后会自动标记为 `expired`
- 开始新的专注会话时，会自动收束上一段仍在进行中的会话

#### 上下文注入
- `ContextPlanner` 默认将 `focus_session` 纳入基础上下文
- `ContextEngine` 按需格式化专注会话状态
- 专注会话上下文强调“理解用户执行片段”，不作为强制证明、考核或压力来源

#### Web 调试
- `/api/memory` 和 `/api/context` 暴露 `focus_session`
- 新增 `/api/focus`，支持 `start`、`complete`、`abandon` 三类动作
- 前端左侧新增 `FOCUS SESSION` 面板
- 用户可以在页面中直接填写接下来这一段要做的事、设置计划时长，并标记完成或停止
- 页面会显示当前专注目标、状态、已进行时间和最近会话间隔

## V0.7
### 目标
- 为 Workmate Agent 增加受控的内部状态工具层
- 工具调用只用于读取和更新任务、承诺、记忆等内部状态，不做外部自动化
- 不采用完整 ReAct 文本框架，改用结构化 JSON tool call loop，降低工具误用风险

### 已实现
#### 内部状态工具层
- 新增 `tools/registry.py`
- 新增 `tools/executor.py`
- 新增 `tools/workmate_tools.py`
- 支持工具：`get_current_task`、`list_open_tasks`、`update_task_status`、`list_open_commitments`、`search_memory`、`add_memory_note`
- 工具层禁止访问外部网页、任意文件、shell、GitHub 或其他外部自动化能力
- 工具选择失败时自动降级为空工具调用，不影响普通对话

#### Agent 调用链
- `WorkmateAgent` 在生成最终回复前先执行最多 3 次内部状态工具调用
- 工具 observation 作为 system context 注入最终回复
- 流式输出同样先完成工具调用，再流式生成自然语言回复
- 保留现有记忆流水线；工具层作为内部状态辅助，不替代记忆提取和任务生命周期管理

#### Web 调试
- `/api/chat`、`/api/memory`、`/api/context` 暴露本轮 `tool_calls`
- 前端侧栏新增 `tools` 区域，显示最近工具调用状态

## V0.6.1
### 目标
- 降低 GitHub clone 后的本地启动门槛
- 让用户按“复制配置、填写 API Key、运行脚本、自动打开页面”的路径使用 Workmate Agent

### 已实现
#### 一键启动
- 新增 `.env.example`，提供 OpenRouter/Kimi 的 OpenAI-compatible 配置示例
- 新增 `run.sh`
- `run.sh` 会检查 `.env` 和 `LLM_API_KEY`
- 优先使用本机 conda `agent` 环境；没有该环境时自动创建本地 `.venv`
- 自动安装/检查依赖，启动 `src.web`，并打开 `http://127.0.0.1:7860`
- `.gitignore` 新增 `.venv/`，避免提交本地虚拟环境

#### 文档
- README 新增快速启动路径：`cp .env.example .env` -> 填 API Key -> `./run.sh`
- README 保留手动 conda 启动和命令行模式作为备用方式

## V0.6
### 目标
- 引入轻量支持性知识层，在用户焦虑、分散、拖延、疲惫或卡住时提供温和支撑
- 用注意力、时间管理、学习方法和情绪调节类短卡片辅助回应
- 保持 Workmate Agent 的边界：不做心理诊断，不做治疗，不讲大道理，不把方法论变成新压力

### 已实现
#### 支持性知识层
- 新增 `knowledge/support_notes.json`
- 首批支持卡片覆盖专注、启动阻力、分心、开放循环、自我攻击、灾难化念头、读书、刷题、写作整理和调试卡点
- 卡片使用短原则和温和应用说明，不直接注入长篇书籍内容

#### 轻量检索与注入
- 新增 `SupportKnowledgeManager`
- 支持基于用户输入识别 `anxious`、`scattered`、`tired`、`avoidant`、`overplanning`、`stuck` 等状态
- 仅在相关状态出现时检索支持性卡片，并通过 `ContextPlanner` / `ContextEngine` 注入模型上下文
- 支持性知识只作为辅助，不要求用户证明、汇报或完成额外标准

#### Web 调试
- `/api/memory` 暴露本轮支持性知识状态
- 前端侧栏新增 `support` 区域，用于查看当前是否触发支持性知识层及对应轻柔提示

## V0.5.5
### 目标
- 优化 Workmate Agent 的回复收束方式，让用户同步计划后可以直接去执行
- 减少默认追问带来的对话负担，避免用户被问句拖回聊天
- 在用户准备开始任务时，偶尔给出轻柔的执行焦点，帮助用户带着注意力线索进入任务

### 已实现
#### 回复收尾体验
- `systemPrompt` 新增“收尾策略”：默认不以问句结尾
- 当用户同步计划、汇报进展、让我记住某事或准备开始执行时，优先用“已记录 / 计划整理 / 下一步提醒”收束
- 只有缺少关键信息、无法建立任务状态或无法判断用户真实意图时，才提出最多一个必要问题
- 将启发性内容改写为陈述式小建议，减少为了延续对话而产生的追问

#### 执行焦点提示
- `systemPrompt` 新增“执行焦点提示”
- 当用户明确表示接下来要做一件事时，Agent 可以偶尔给一个轻柔的注意力线索
- 执行焦点用于帮助用户进入任务，不作为验收标准、完成指标、证明要求或回来汇报要求
- 提示要求自然融入对话，避免“成果锚点”“完成标准”等模板化、命令式表达
- 按读书、刷题、写作整理、开发调试等场景给出柔和示例

#### 记忆上下文清洗
- 监督信号不再建议“询问是否需要更新进展”，改为“温和提醒用户回来同步进展”
- 记忆检索和记忆项清洗中，将“质疑”柔化为“必要时澄清一个关键信息”，避免长期上下文诱导追问式回复

## V0.5.4
### 目标
- 将 V0.5.3 后续的架构整理工作独立成版本
- 降低 `memory/` 目录的文件噪音，明确代码模块、运行时数据和聚合边界
- 保持外部调用兼容，避免架构整理影响 `from memory import MemoryManager` 等现有入口

### 已实现
#### 架构轻量化
- 新增 `TaskState` 聚合 `TaskManager`、`TaskStateManager` 和 `CommitmentManager`
- 新增 `ContextEngine` 聚合 `SearchManager`、`ContextPlanner` 和 `ContextCompressor`
- `MemoryManager` 改为通过 `TaskState` 更新任务、承诺和当前状态，降低任务相关职责分散
- `MemoryManager` 改为通过 `ContextEngine` 构建模型上下文，检索、规划、压缩和消息拼装集中在一个模块
- 新增 `MemoryStore`，物理合并 `MemoryResourceManager`、`MemoryItemManager` 和 `MemoryCategoryManager`
- 新增 `MemoryInterpreter`，物理合并 `MemoryExtractor`、`SemanticDialogueManager`、`SummaryManager`、`InsightManager` 和 `IntentManager`
- 删除已合并的旧 Manager 单文件，只保留聚合后的代码文件；公共类名和缓存 JSON 格式保持兼容
- 新增 `memory/paths.py` 统一管理运行时记忆路径，默认数据目录迁移为 `memory/data/`
- 运行时 JSON、检索索引和每日摘要从 `memory/` 根目录移入 `memory/data/`，避免代码文件和记忆缓存混放
- 将 `memory/` 下保留的 Python 模块统一改为 snake_case 命名，例如 `manager.py`、`pipeline.py`、`store.py`、`interpreter.py`
- `memory/__init__.py` 继续导出原有类名，保持 `from memory import MemoryManager` 等外部调用方式不变

## V0.5.3
### 目标
- 继续优化记忆系统
- 目前的几个问题：
- 搜索引擎太"笨"——纯关键词匹配（优化方向： 引入向量搜索（Embedding Search）。把文本转成数字向量，用语义相似度而不是字面匹配来排序。这是目前工业界 RAG（检索增强生成）系统的标准做法。）
- 搜索索引每次都重新构建，每次调用 search_related_memories，都会在内部调用 build_index，把所有记忆重新处理一遍，然后再搜索，然后再把结果写入文件。（优化方向： 索引应该增量更新——只在 process_turn 写入新记忆后更新索引，而不是每次读取时重建。或者把索引缓存在内存里，只有数据变化时才刷新。）
- 意图识别太脆弱——关键词命中即判断（优化方向： 用一次小的 LLM 调用（比如便宜的小模型）来做意图分类，而不是关键词匹配。）
- build_context中的available_context{} 无论如何都格式化全部 16 个数据块（优化方向： 先做意图判断，再按需加载。比如判断是 chat 意图，就只加载 3 个必要块，不加载 reflections、memory_summary 等昂贵的数据。）
- 压缩是"一刀切截断"，可能切断关键信息(优化方向： 截断前先提取摘要（用 LLM 压缩），或者按句子边界截断，保证信息的完整性。)

### 已实现
#### 第一批优化
- `SearchManager.search()` 改为优先读取 `memory/data/retrieval_index.json`，不再每次检索都重建索引
- `refresh_search_index()` 继续作为记忆写入后的索引刷新入口，保持写入和检索分离
- 检索索引保存 `salience`、`confidence`、`status` 和 `updated_at` 等排序元数据，避免检索时依赖原始 payload
- `ContextPlanner` 新增 `required_context_keys()`，先判断输入意图，再返回需要加载的上下文块
- `MemoryManager.build_context_messages()` 改为按需加载和格式化上下文，普通聊天不再预先格式化全部记忆块
- `ContextCompressor` 改为按换行和句子边界压缩，降低截断关键信息的概率

#### 第二批优化
- 新增 `IntentManager`，用于本轮输入意图识别
- 意图识别优先调用 LLM 输出结构化 JSON，支持 `chat`、`task`、`review`、`supervision`、`search` 五类
- 当 LLM 不可用、输出非法或分类异常时，自动回退到规则分类
- `ContextPlanner` 支持接收外部意图分类结果，避免同一轮重复判断
- `MemoryManager.build_context_messages()` 会先执行意图分类，再根据分类结果按需加载上下文
- `build_context_debug()` 暴露本轮 `intent`，方便调试分类来源和置信度
- `CommitmentManager` 改为 LLM 优先判断承诺新增和关闭，规则逻辑作为兜底
- `TaskManager` 改为 LLM 优先解释任务生命周期和子任务状态变化，规则状态推断作为兜底
- `UserProfileManager` 改为 LLM 优先提取稳定用户画像增量，默认低压力沟通偏好继续作为产品约束保留
- `MemoryGovernanceManager` 改为 LLM 优先识别陈旧事实、冲突事实、低价值记忆和显著性提升，规则治理作为兜底

## V0.5.2
### 目标
- 继续优化记忆系统，不跳到 V0.6
- 引入自我反省机制：让 Agent 在若干轮对话后或空闲时回看历史记忆，提炼高阶 Insights
- 引入记忆治理机制：识别陈旧事实、冲突事实和低价值记忆，并优先降权或归档，而不是直接删除

### 已实现
#### 自我反省
- 新增 `ReflectionManager`
- 新增 `memory/reflections.json`
- 支持按轮次触发：默认每 5 轮对话分析一次
- 支持手动触发：用户要求“复盘一下最近状态”“自我反省”等时触发
- 反省结果记录触发原因、活跃 Insight 数量、治理变更数量和最近洞察

#### 高阶洞察
- 新增 `InsightManager`
- 新增 `memory/high_level_insights.json`
- 从 `Resource / MemoryItem / MemoryCategory` 中提炼长期行为模式和任务推进模式
- Insight 不等同于摘要，重点关注：反复偏航、过度规划、伪努力、有效推进方式、任务结构变化
- 支持 LLM 提炼；模型不可用时使用规则兜底

#### 原始对话语义压缩
- 新增 `SemanticDialogueManager`
- 新增 `memory/semantic_dialogues.json`
- 每轮对话都会把原始对话压缩成更短的核心语义
- 压缩结果保留：用户真实意图、任务/进展/阻塞、关键承诺、重要上下文和必要时间信息
- 压缩结果不保留：寒暄、重复表达、低价值解释、与长期监督无关的细节
- 原始对话仍保留在 `records.json`，压缩版本作为上下文注入优先使用，目标是节省上下文窗口
- 支持 LLM 压缩；模型不可用时根据结构化提取结果规则生成

#### 冲突与陈旧记忆治理
- 新增 `MemoryGovernanceManager`
- 新增 `memory/memory_conflicts.json`
- 识别类似“当前版本是 V0.4”和“当前版本是 V0.5.1 / V0.5.2”的冲突事实
- 采用 `active -> stale -> archived` 的生命周期，先降权和隐藏，再考虑归档
- 不默认物理删除历史记忆，保留来源以便追溯
- `MemoryItemManager` 和 `SearchManager` 会避开 archived 记忆，并对 stale 记忆降权

#### 上下文注入策略
- `ContextPlanner` 优先注入高阶 Insight、语义压缩对话和记忆治理状态，再注入低层记忆项
- `SearchManager` 索引 `high_level_insight` 和 `semantic_dialogue`
- Web API 和前端侧栏暴露高阶洞察、语义压缩、反省记录和记忆冲突

## V0.5.1
### 目标
- 对照ReMe 和 MemU 等市面成熟记忆系统架构，补强 V0.5 记忆系统的细节严谨性和架构可靠性
- 在不引入重型数据库/向量库依赖的前提下，吸收 ReMe 的上下文治理和 MemU 的三层记忆模型、流水线契约思想

### 已实现
#### 三层记忆模型
- 新增 `MemoryResourceManager` 和 `memory/memory_resources.json`
- 新增 `MemoryCategoryManager` 和 `memory/memory_categories.json`
- 当前记忆分层为：`Resource` 原始对话来源、`MemoryItem` 原子记忆、`MemoryCategory` 分类摘要
- 每轮对话会同时更新资源层、记忆项层和分类层，方便后续追溯来源和按类别召回

#### 流水线契约
- `MemoryPipeline` 升级为带 `requires / produces` 的阶段契约
- 每轮处理包括 `record_turn -> extract_items -> update_task_state -> persist_record -> update_derived_memory -> build_response`
- 流水线结果暴露每个阶段的状态、产物和错误信息，便于排查记忆写入故障

#### 检索计划和充分性诊断
- `SearchManager` 支持索引 `memory_category` 和 `memory_resource`
- 新增 `build_retrieval_plan()`，输出是否需要检索、偏好召回类型、命中数量、命中类型、最高分和简要原因
- `ContextPlanner` 会在任务、复盘、监督、历史查询场景注入检索计划和分类摘要

#### 稳定标识和去重
- `MemoryItemManager` 的内容标识改为稳定 SHA 摘要，不再依赖进程随机化的 Python `hash()`
- `MemoryManager` 的 record id 也改为稳定摘要后缀

#### Web 调试
- `/api/memory` 和 `/api/context` 暴露 `memory_categories`、`memory_resources`、`retrieval_plan` 和 `last_pipeline_result`
- 前端侧栏新增记忆分类摘要展示

## V0.5
### 目标
- 优化记忆系统，使其从多个分散 JSON 缓存升级为更成熟的分层记忆架构
- 借鉴 ReMe 的上下文压缩治理、文件式记忆和推理前上下文控制
- 借鉴 MemU 的 Resource / Item / Category 思路和 memorize / retrieve 流水线

### 已实现
#### 统一记忆项
- 新增 `MemoryItemManager`
- 新增 `memory/memory_items.json`
- 将任务、子任务、进展、阻塞、下一步、承诺、用户偏好、行为模式和监督建议统一沉淀为 `memory_item`
- 记忆项包含 `type`、`category`、`content`、`task_id`、`source_record_ids`、`confidence`、`salience`、`usage_count` 等治理字段

#### 写入流水线
- 新增 `MemoryPipeline`
- 每轮对话保存统一经过 `extract_items -> update_task_state -> persist_record -> update_memory_items -> refresh_index`
- `src/core.py` 改为调用 `memory_manager.process_turn()`，避免主流程散落调用多个 Manager

#### 检索与上下文注入
- `SearchManager` 支持把统一记忆项加入检索索引
- 检索结果加入类型偏好和显著性加权，任务/承诺/画像类查询会优先召回对应内容
- `ContextPlanner` 在任务、复盘、监督场景优先注入统一记忆项和主动监督信号

#### 上下文压缩治理
- 新增 `ContextCompressor`
- 系统记忆和最近对话分别有独立字符预算，避免长历史撑爆上下文
- `build_context_debug()` 暴露 `context_stats`，方便观察实际注入规模

#### 主动监督
- 新增 `SupervisionManager`
- 根据当前任务停滞、未关闭承诺、反复阻塞和未关闭任务数量生成监督信号
- 监督信号只用于自然提醒，不强制证据，不设置时间限制，不扩展技术路线

#### Web 调试
- `/api/memory` 和 `/api/context` 暴露 `memory_items`、`supervision`、`memory_pipeline` 和 `context_stats`
- 前端侧栏新增统一记忆项和主动监督信号展示

## V0.4.2
### 目标
- 收窄 Workmate Agent 的角色边界：只做任务结构整理和监督判断，不做技术帮助、不主动设时间限制
- 防止 Agent 自己制造子任务或承诺，任务结构应主要来自用户自己提出的内容

### 已实现
#### 监督边界
- system prompt 明确：不解释技术细节、不提供专业路线、不主动设置时间盒或 deadline
- 多任务列表只整理用户自己提出的任务/子任务，不主动扩展技术路线

#### 子任务来源收紧
- `MemoryExtractor` 提示明确：`subtasks` 只能来自 `user_input` 中用户明确提出的子任务
- `TaskManager` 不再把 `next_actions` 自动补成 `subtasks`
- `TaskManager.format_for_context()` 不再注入 `next_check_at`，避免模型主动输出时间限制

#### 承诺来源收紧
- `CommitmentManager` 不再把 Agent 的 `next_actions` 写成 open commitments
- 当前只记录用户明确承诺的事项

## V0.4.1
### 目标
- 支持任务/子任务结构，避免把一个大任务下的多个动作拆成多个平级任务
- 优化 Agent 输出格式：只在多任务或多子任务场景使用无序列表整理思路，避免回复变成固定模板

### 已实现
#### 子任务提取
- `MemoryExtractor` 新增 `subtasks`
- LLM 提取提示明确区分主任务和子任务
- 规则兜底会从多事项输入中提取子任务候选

#### 任务生命周期
- `TaskManager` 的任务实体新增 `subtasks`
- 子任务支持 `inbox`、`planned`、`active`、`blocked`、`done`、`abandoned`
- 每轮对话后会合并新增子任务，并根据阻塞、完成、放弃等信号更新子任务状态
- `TaskStateManager` 和 Web API 当前任务视图同步暴露子任务

#### 输出策略
- 主 Agent system prompt 新增多任务输出规则
- 仅当用户一次性提出多个任务、多个优化方向或一个主任务下多个子任务时，优先用无序列表整理
- 单任务汇报、普通聊天和情绪表达仍保持自然短回复

## V0.4
### 目标
- 任务管理：把 `task_state.json` 从当前状态快照升级为任务生命周期视图
- 优化上下文注入策略：不再每轮全量注入所有上下文，根据当前输入选择任务、摘要、承诺或检索结果
- 为后续主动监督打基础：先生成 `next_check_at` 等检查信号，后续再接主动消息通道
- 调整监督语气：不再默认要求用户每次汇报都强制证明

### 已实现
#### 任务生命周期
- 新增 `TaskManager`
- 维护 `memory/tasks.json` 和 `memory/task_events.json`
- 支持 `inbox`、`planned`、`active`、`blocked`、`done`、`abandoned` 状态
- 每轮对话后根据结构化记忆更新任务实体、进展、阻塞、下一步和任务事件
- `TaskStateManager` 降级为当前任务视图缓存，并兼容旧的 `task_state.json`

#### 上下文规划
- 新增 `ContextPlanner`
- `MemoryManager.build_context_messages()` 改为按输入意图选择上下文
- 普通闲聊减少摘要注入；任务汇报优先注入任务生命周期、当前状态、承诺、近期摘要和相关历史；复盘请求再注入完整历史摘要

#### 去除强制证据语义
- `MemoryExtractor` 不再输出 `evidence_required`
- `SummaryManager` 不再汇总待验证证据，也不再生成“继续要求证据”的监督模式
- `CommitmentManager` 不再把截图、证据、验证要求自动变成未关闭承诺
- `UserProfileManager` 不再把“要求用户提供可验证证据”写入有效干预
- 加载旧画像、旧承诺、旧任务状态和旧日摘要时，会过滤强制证据相关内容

## V0.3
### 目标
- 从 `records.json` 中提取结构化事实，并形成可复用记忆
- 让 Agent 能够基于最近若干天记录进行监督
- 自动生成长期摘要和每日摘要
- 识别重复拖延、分心等模式
- 能够引用历史记录、未关闭承诺和长期用户画像

### 已实现
#### 记忆提取
- 新增 `MemoryExtractor`
- 每轮对话后调用模型提取结构化记忆，输出 `categories`、`task`、`progress`、`blockers`、`next_actions`、`user_commitments`、`signals`
- 模型输出异常或 JSON 不合法时，自动回退到规则提取
- 提取结果写入每条 `records.json` 记录的 `extracted` 字段

#### 当前任务状态
- 新增 `TaskStateManager`
- 维护 `memory/task_state.json`
- 跟踪 `active_task`、`status`、`current_progress`、`next_action`、`blockers`
- 每轮对话后根据结构化记忆更新当前主线任务状态

#### 摘要系统
- 新增模型优先的 `SummaryManager`
- 每日调用模型生成 JSON 摘要，写入 `memory/daily_summaries/`
- 摘要内容包括主要任务、已完成事项、进行中事项、进展、阻塞、下一步、行为模式、监督建议
- 模型摘要失败时自动使用规则摘要兜底
- 聚合最近 7 天摘要，用于识别主线任务、反复阻塞、行为模式和下一步监督策略

#### 承诺与画像
- 新增 `CommitmentManager`
- 维护 `memory/commitments.json`
- 追踪用户承诺、未关闭待办和已关闭承诺
- 新增 `UserProfileManager`
- 维护 `memory/user_profile.json`
- 记录长期目标、工作风格、常见风险、有效干预方式和沟通偏好

#### 历史检索
- 新增 `SearchManager`
- 维护 `memory/retrieval_index.json`
- 对 `records.json`、每日摘要、用户画像、承诺记录建立轻量关键词索引
- 每轮对话根据当前输入检索相关历史，并注入模型上下文

#### 上下文注入
- `MemoryManager` 统一组装模型上下文
- 当前上下文包含：长期用户画像、原始历史摘要、当前任务状态、结构化记忆摘要、最近 7 天摘要、未关闭承诺、相关历史检索、最近几轮对话、当前输入
- `LLMClient` 新增 `invoke_raw(messages)`，用于摘要和结构化提取，避免混入主 Agent 的长 system prompt

#### 前端调试
- Web 前端新增当前任务面板、最近 7 天摘要、未关闭承诺、用户画像摘要
- 新增 `MODEL CONTEXT` 调试区，可查看实际发送给模型的 messages
- Agent 回复支持 Markdown 渲染

## V0.2
### 改动
加入了前端页面


## V0.1
### 架构
输入今天做了什么
↓
保存到 records.json
↓
读取最近5条记录
↓
拼Prompt
↓
调用模型
↓
输出评价
### 需要解决的问题
- 能够记忆我的提问、记忆自己的回答
- 能够连续对话

### 已实现
- 新增 `MemoryManager`，负责读写 `memory/records.json`
- 每轮对话后自动保存用户输入和模型回复
- 每次调用前自动注入长期记忆摘要和最近几轮对话
- `LLMClient.invoke` 支持传入完整 `messages`，保留原有 `prompt` 调用方式
