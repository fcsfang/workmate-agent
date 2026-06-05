# Workmate Agent

Workmate Agent 是一个面向个人学习和工作执行的长期工位搭子。它不是一次性问答助手，而是通过本地记忆记录用户的任务汇报、模型回复和时间线，在连续对话中判断进度、提醒偏航、拆解下一步行动。

当前项目重点解决一个问题：让大模型 API 调用具备可持续的上下文记忆，并能在命令行里进行连续对话。

## 项目背景

目标用户是容易拖延、注意力分散，或者刚开始推进一个项目但缺少外部监督的人。用户可以把当天目标、当前进展、卡住的问题告诉 Agent；Agent 会结合历史记录判断用户是否真的在推进，而不是只根据单次消息给出泛泛建议。

典型场景：

- 求职准备：收集 JD、提炼高频技能词、推进作品集或项目
- 学习监督：汇报学习进度，识别过度输入和伪努力
- 任务执行：把模糊目标拆成下一步可执行动作
- 长期复盘：基于历史记录观察任务推进和时间投入是否匹配

## 功能

- 连续对话：命令行启动后可以多轮输入，直到用户主动退出
- 本地记忆：每轮用户输入和 Agent 回复都会保存到 `memory/records.json`
- 上下文注入：下一轮调用模型前，会读取最近几轮对话并生成长期记忆摘要
- 时间感：当前输入会附带当前时间，历史输入会附带历史记录时间
- 进度监督：Prompt 设定 Agent 关注任务进展、偏航、伪努力和下一步行动

## 项目结构

```text
workmate-agent/
├── memory/
│   ├── MemoryManager.py   # 记忆读写、摘要和上下文组装
│   ├── MemoryExtractor.py # 每轮对话后的结构化事实提取
│   ├── CommitmentManager.py # 承诺和待验证事项追踪
│   ├── SummaryManager.py  # 模型优先的每日摘要和最近7天摘要
│   ├── UserProfileManager.py # 长期用户画像
│   ├── SearchManager.py   # 轻量关键词历史检索
│   ├── TaskStateManager.py # 当前任务状态维护
│   ├── __init__.py
│   ├── records.json       # 本地对话记录，运行时生成
│   ├── task_state.json    # 当前任务状态，运行时生成
│   ├── commitments.json   # 未关闭承诺，运行时生成
│   ├── user_profile.json  # 长期画像，运行时生成
│   ├── retrieval_index.json # 检索索引，运行时生成
│   └── daily_summaries/   # 每日摘要，运行时生成
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

项目运行环境使用 conda 中名为 `agent` 的环境。

```bash
conda activate agent
pip install -r requirements.txt
```

在项目根目录创建 `.env`，配置大模型 API：

```env
LLM_MODEL_ID=your-model-id
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://your-api-base-url
```

`.env` 不应提交到 Git。

## 运行方式

### Web 调试界面

当前推荐入口是 `src.web`。启动它以后，整个项目就跑起来了：本地前端页面、`/api/chat` 对话接口、`/api/memory` 记忆接口会一起启动。

推荐使用前端界面调试连续对话：

```bash
conda run -n agent python -m src.web
```

启动后打开：

```text
http://127.0.0.1:7860
```

页面会显示对话区、最近记忆、记忆摘要和本地记录数量。每次发送消息都会调用同一个 `WorkmateAgent` 流程，并写入 `memory/records.json`。

0.3+ 版本还会在页面左侧显示当前任务状态、最近 7 天摘要、未关闭承诺和长期用户画像，并提供 `MODEL CONTEXT` 调试区。每日摘要会优先调用模型生成 JSON 记忆，失败时退回规则摘要；`MODEL CONTEXT` 会展示上一轮实际发送给模型的 messages，方便检查 Agent 到底带入了哪些记忆。

只要这个命令所在的终端窗口保持运行，页面和 API 就会保持可用。需要停止时，在该终端按 `Ctrl + C`。

### 命令行模式

也可以在项目根目录运行：

```bash
conda run -n agent python -m src.core
```

也可以先激活环境：

```bash
conda activate agent
python -m src.core
```

启动后可以连续输入消息。输入 `exit`、`quit`、`q`、`退出` 或 `结束` 可以结束对话。

## 示例对话

```text
你：我现在已经找了1条JD，并且已经放到文档中了

搭子：好，已经开始落地了。先确认两个事：高频词标出来了吗，还是只复制了原文？如果只复制了原文，下一步不要继续扩散，先把这1条里的 RAG、Agent、Python、评测这些关键词圈出来。

你：我现在完成了10条JD拉取了，现在请你根据你的记忆，总结我的进展

搭子：我会先看时间线和历史记录。你确实从“准备找JD”推进到了“完成拉取”，但我还需要确认完成质量：是只有岗位信息，还是完整JD文本和高频词已经标注？下一步给我前5个高频词及出现次数，这比继续找更多岗位更有价值。
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

当前版本是 JSON 文件记忆，适合早期验证连续对话和任务监督。后续记录变多后，可以继续加入每日摘要、周/月总结、向量检索和更细的任务状态结构。
