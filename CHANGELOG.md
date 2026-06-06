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
