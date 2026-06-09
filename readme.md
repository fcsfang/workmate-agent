# Workmate Agent

Workmate Agent 是一个面向个人学习和工作执行的长期工位搭子。它不是一次性问答助手，而是通过本地记忆记录用户的任务汇报、模型回复和时间线，在连续对话中判断进度、提醒偏航、整理任务结构。

当前项目重点解决一个问题：让大模型 API 调用具备可持续的上下文记忆，并能在命令行和 Web 页面里进行连续对话。

## 项目背景

目标用户是容易拖延、注意力分散，或者刚开始推进一个项目但缺少外部监督的人。用户可以把当天目标、当前进展、卡住的问题告诉 Agent；Agent 会结合历史记录判断用户是否真的在推进，而不是只根据单次消息给出泛泛建议。

典型场景：

- 求职准备：收集 JD、提炼高频技能词、推进作品集或项目
- 学习监督：汇报学习进度，识别过度输入和伪努力
- 任务执行：把模糊目标拆成下一步可执行动作
- 长期复盘：基于历史记录观察任务推进和时间投入是否匹配

## 功能

- 连续对话：命令行启动后可以多轮输入，直到用户主动退出
- 本地记忆：每轮用户输入和 Agent 回复都会保存到 `memory/data/records.json`
- 上下文注入：下一轮调用模型前，会读取最近几轮对话并生成长期记忆摘要
- 统一记忆项：V0.5 起会把任务、进展、阻塞、承诺、用户偏好和监督模式沉淀到 `memory/data/memory_items.json`
- 三层记忆模型：V0.5.1 起增加 `Resource / MemoryItem / MemoryCategory`，分别追踪原始来源、原子记忆和分类摘要
- 语义压缩：V0.5.2 起把原始对话提炼为 `semantic_dialogues`，上下文注入优先使用核心语义以节省窗口
- 自我反省：V0.5.2 起每若干轮对话或用户手动要求复盘时，提炼高阶洞察并记录反省结果
- 记忆治理：识别陈旧/冲突事实，对旧记忆降权或归档，而不是直接删除
- 记忆流水线：每轮对话统一经过提取、任务更新、记录保存、记忆项写入和索引刷新
- 流水线契约：每个记忆阶段都有 `requires / produces` 诊断信息，方便定位提取、保存、索引等故障
- 任务生命周期：把任务从当前快照升级为 `inbox / planned / active / blocked / done / abandoned` 的完整状态流，并支持主任务下的子任务
- 上下文规划：根据用户输入选择注入任务、摘要、承诺、统一记忆项或相关历史，减少每轮全量上下文
- 上下文压缩：系统记忆和最近对话分别控制预算，避免长对话让模型上下文膨胀
- 主动监督信号：根据任务停滞、未关闭承诺、反复阻塞和任务过散生成监督提醒
- 支持性知识层：V0.6 起在用户焦虑、分散、拖延、疲惫、卡住或准备执行学习任务时，按需注入轻量方法论卡片
- 内部状态工具层：V0.7 起支持受控工具调用，用于读取和更新任务、承诺、记忆等 Workmate 内部状态
- 专注会话：V0.8 起支持记录用户“离开对话后要执行的一段任务”，追踪当前专注、计划时长、实际经过时间和最近会话间隔
- 时间感：当前输入会附带当前时间，历史输入会附带历史记录时间
- 进度监督：Agent 关注任务进展、偏航和伪努力；多任务场景会用无序列表帮用户理顺主任务和子任务，但不会主动提供技术路线或设置时间限制
- 角色边界：Agent 负责总体规划和监督，不负责替用户解释技术细节、设计专业方案或完成任务

## 项目结构

```text
workmate-agent/
├── memory/
│   ├── manager.py         # 记忆读写、摘要和上下文组装入口
│   ├── store.py           # 资源层、统一记忆项、分类摘要
│   ├── interpreter.py     # 提取、语义压缩、摘要、洞察、意图识别
│   ├── task_state.py      # 任务、当前状态、承诺聚合入口
│   ├── context_engine.py  # 检索、上下文规划、上下文压缩聚合入口
│   ├── reflection.py      # v0.5.2 自我反省触发和记录
│   ├── governance.py      # v0.5.2 陈旧/冲突记忆治理
│   ├── pipeline.py        # v0.5 每轮对话记忆写入流水线
│   ├── context_compressor.py # v0.5 上下文预算和压缩
│   ├── context_planner.py # 根据当前输入选择需要注入的上下文
│   ├── commitment.py      # 承诺和未关闭待办追踪
│   ├── profile.py         # 长期用户画像
│   ├── search.py          # 轻量关键词历史检索
│   ├── supervision.py     # v0.5 主动监督信号
│   ├── support_knowledge.py # v0.6 支持性知识层检索
│   ├── focus_session.py   # v0.8 专注会话和时间间隔感知
│   ├── task_manager.py    # v0.4.2 任务/子任务生命周期和事件流水
│   ├── task_state_manager.py # 当前任务状态维护
│   ├── paths.py           # 运行时记忆数据目录配置
│   ├── __init__.py
│   └── data/              # 运行时记忆文件，默认不提交
│       ├── records.json
│       ├── memory_resources.json
│       ├── memory_items.json
│       ├── memory_categories.json
│       ├── semantic_dialogues.json
│       ├── high_level_insights.json
│       ├── memory_conflicts.json
│       ├── reflections.json
│       ├── tasks.json
│       ├── task_events.json
│       ├── task_state.json
│       ├── commitments.json
│       ├── user_profile.json
│       ├── retrieval_index.json
│       ├── focus_sessions.json
│       └── daily_summaries/
├── knowledge/
│   └── support_notes.json # 注意力、学习、时间管理和情绪调节短卡片
├── tools/
│   ├── registry.py        # 内部工具注册表
│   ├── executor.py        # 结构化工具调用执行器
│   └── workmate_tools.py  # 任务、承诺、记忆等内部状态工具
├── src/
│   ├── LLMClient.py       # 大模型 API 客户端
│   ├── core.py            # WorkmateAgent 和命令行连续对话入口
│   └── web.py             # 本地 Web 调试服务
├── web/
│   ├── assets/
│   └── index.html         # 前端调试界面
├── demo.md                # 示例交互
├── requirements.txt
└── README.md
```

## 环境准备

### 快速启动

```bash
git clone https://github.com/fcsfang/workmate-agent.git
cd workmate-agent
cp .env.example .env
```

打开 `.env`，填写你的模型 API 配置。OpenRouter 示例：

```env
LLM_MODEL_ID=moonshotai/kimi-k2.6:free
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://openrouter.ai/api/v1
```

然后运行：

```bash
./run.sh
```

脚本会自动：

- 检查 `.env` 是否存在
- 检查 `LLM_API_KEY` 是否已填写
- 优先使用本机已有的 conda `agent` 环境
- 如果没有 conda `agent` 环境，则创建本地 `.venv`
- 安装/检查依赖
- 启动 Web 服务
- 自动打开浏览器访问 `http://127.0.0.1:7860`

保持运行 `./run.sh` 的终端窗口即可持续使用页面和 API。需要停止时，在该终端按 `Ctrl+C`。

`.env` 不应提交到 Git。

## 运行方式

### 推荐方式

当前推荐入口是 `src.web`。启动它以后，整个项目就跑起来了：本地前端页面、`/api/chat` 对话接口、`/api/memory` 记忆接口会一起启动。

推荐使用前端界面调试连续对话：

```bash
./run.sh
```

启动后打开：

```text
http://127.0.0.1:7860
```

页面会显示对话区、最近记忆、记忆摘要和本地记录数量。每次发送消息都会调用同一个 `WorkmateAgent` 流程，并写入 `memory/data/records.json`。

0.5.2+ 版本还会在页面左侧显示当前任务生命周期、子任务、最近 7 天摘要、未关闭承诺、长期用户画像、统一记忆项、记忆分类、高阶洞察、语义压缩和主动监督信号，并提供 `MODEL CONTEXT` 调试区。V0.8 起，左侧还可以直接开始、完成或停止一段专注会话，用来记录用户离开聊天后实际去做的那段任务；该状态会进入上下文，但不会作为强制考核。每日摘要会优先调用模型生成 JSON 记忆，失败时退回规则摘要；`MODEL CONTEXT` 会展示上一轮实际发送给模型的 messages、上下文规模、检索计划和流水线状态，方便检查 Agent 到底带入了哪些记忆。

只要这个命令所在的终端窗口保持运行，页面和 API 就会保持可用。需要停止时，在该终端按 `Ctrl+C`。

### 手动启动 Web

如果你已经准备好 conda 中名为 `agent` 的环境，也可以手动运行：

```bash
conda run -n agent python -m src.web
```

或者先激活环境：

```bash
conda activate agent
pip install -r requirements.txt
python -m src.web
```

### 命令行模式

也可以在项目根目录运行：

```bash
conda run -n agent python -m src.core
```

启动后可以连续输入消息。输入 `exit`、`quit`、`q`、`退出` 或 `结束` 可以结束对话。

## 示例对话

```text
你：我现在已经找了1条JD，并且已经放到文档中了

搭子：好，已经开始落地了。先确认两个事：高频词标出来了吗，还是只复制了原文？如果只复制了原文，下一步不要继续扩散，先把这1条里的 RAG、Agent、Python、评测这些关键词圈出来。

你：我现在完成了10条JD拉取了，现在请你根据你的记忆，总结我的进展

搭子：我会先看时间线和历史记录。你确实从“准备找JD”推进到了“完成拉取”。现在别急着扩展新目标，先把完成范围说清楚：是只有岗位信息，还是完整JD文本和高频词已经标注？下一步先整理前5个高频词及出现次数，这比继续找更多岗位更有价值。
```

更完整的真实交互案例见 [demo.md](demo.md)。

## 代码调用

如果不使用命令行，也可以在代码中单轮调用：

```python
from src.core import WorkmateAgent

agent = WorkmateAgent()
response = agent.invoke("我现在开始找第一个大模型实习JD")
print(response)
```

## 当前边界

当前版本是 JSON 文件记忆，适合早期验证连续对话、任务生命周期、统一记忆项和任务监督。V0.8 已经具备 Resource / MemoryItem / MemoryCategory 三层结构、语义压缩、高阶洞察、自我反省、记忆治理、检索计划、流水线契约、上下文压缩、主动监督信号、内部状态工具和专注会话；后续记录变多后，可以继续加入浏览器通知、周/月总结、向量检索和后台定时监督。
