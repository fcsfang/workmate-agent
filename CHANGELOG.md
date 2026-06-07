## V0.5.3
### 目标
- 继续优化记忆系统
- 目前的几个问题：
- 搜索引擎太"笨"——纯关键词匹配（优化方向： 引入向量搜索（Embedding Search）。把文本转成数字向量，用语义相似度而不是字面匹配来排序。这是目前工业界 RAG（检索增强生成）系统的标准做法。）
- 搜索索引每次都重新构建，每次调用 search_related_memories，都会在内部调用 build_index，把所有记忆重新处理一遍，然后再搜索，然后再把结果写入文件。（优化方向： 索引应该增量更新——只在 process_turn 写入新记忆后更新索引，而不是每次读取时重建。或者把索引缓存在内存里，只有数据变化时才刷新。）
- 意图识别太脆弱——关键词命中即判断（优化方向： 用一次小的 LLM 调用（比如便宜的小模型）来做意图分类，而不是关键词匹配。）
- build_context中的available_context{} 无论如何都格式化全部 16 个数据块（优化方向： 先做意图判断，再按需加载。比如判断是 chat 意图，就只加载 3 个必要块，不加载 reflections、memory_summary 等昂贵的数据。）
- 压缩是"一刀切截断"，可能切断关键信息(优化方向： 截断前先提取摘要（用 LLM 压缩），或者按句子边界截断，保证信息的完整性。)

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
