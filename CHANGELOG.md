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
