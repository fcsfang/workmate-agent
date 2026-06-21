# Workmate Agent

> **让每一个长期目标，都持续有人记得。**

Workmate 是一个持续关注目标、行动与注意力的个人生产力 Agent。它记住事情进行到了哪里，理解你此刻正在做什么，并在关键时刻主动出现，把零散投入沉淀为持续进展。

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)
![ChromaDB](https://img.shields.io/badge/ChromaDB-FF6600?style=flat)
[![CI](https://github.com/fcsfang/workmate-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/fcsfang/workmate-agent/actions/workflows/ci.yml)

[English](readme.md) · [快速开始](#快速开始) · [隐私说明](#数据与隐私) · [技术架构](docs/ARCHITECTURE_WALKTHROUGH.md)

![Workmate Agent 产品演示](docs/assets/product-overview.gif)

## 目标不会掉线

计划一旦交给 Workmate，就不再只是一句话。

主任务、子任务、当前进度、未关闭承诺和下一步会被持续保存。刷新页面、重新启动或隔一段时间回来，事情仍然从原来的位置继续。

![持续更新的任务主线](docs/assets/task-lifecycle.png)

## 看见行动发生的地方

屏幕，才是目标真正被执行的地方。

视觉监督会带着当前目标理解屏幕内容。它不只知道用户打开了什么应用，还会判断眼前的活动是否正在推进任务，并结合近期轨迹识别一次临时切换与持续偏航。

**当前目标 × 屏幕语义 × 行为轨迹 → 静默、同行或拉回。**

用户也可以主动触发一次屏幕观察，立即获得与当前任务相关的反馈。

![视觉主动监督](docs/assets/vision-supervision.gif)

<details>
<summary>查看清晰的视觉监督消息</summary>

![视觉监督详情](docs/assets/vision-supervision.png)

</details>

## 在关键时刻主动出现

Workmate 不需要等用户再次打开聊天窗口。

只要本地服务保持运行，它就会持续关注任务停滞、专注结束、承诺临近和屏幕偏航。这些信号会形成可追踪的监督事件，直到被确认、延后、关闭或完成。

目标因此不会悄无声息地被日常事务覆盖。

## 每一次投入，都留下积累

Workmate 保存的不只是对话。

眼前的任务状态、长期目标、沟通偏好、重复行为模式和阶段反思会被分别沉淀。过去的经历只在真正相关时重新进入上下文，让每次使用都沿着已经形成的主线继续向前。

## 数据与隐私

- 任务、对话、画像、长期认知和向量索引默认保存在本机。
- 使用外部模型时，必要上下文会发送给所配置的服务商。
- 启用视觉监督后，临时截图会发送给视觉模型，并在分析完成后从本地删除。
- API Key、运行时记忆、屏幕截图和本地索引不会提交到 Git。

随时清除全部本地记忆：

```bash
# 先停止正在运行的 Workmate
./scripts/clear_memory.sh
```

## 快速开始

要求 Python 3.12+。推荐使用 Conda，也支持自动创建本地 `.venv`。

```bash
git clone https://github.com/fcsfang/workmate-agent.git
cd workmate-agent
cp .env.example .env
```

在 `.env` 中填写 OpenAI 兼容模型配置：

```env
LLM_MODEL_ID=moonshotai/kimi-k2.6:free
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://openrouter.ai/api/v1
```

运行：

```bash
./run.sh
```

- Web 页面：`http://127.0.0.1:7860`
- OpenAPI：`http://127.0.0.1:7860/docs`
- 自定义端口：`WORKMATE_PORT=7861 ./run.sh`
- 停止服务：在运行终端按 `Ctrl+C`

<details>
<summary>查看初始化界面</summary>

![Workmate Agent 初始化界面](docs/assets/init.png)

</details>

## Agent 工程能力

产品体验由一套完整的 Agent 运行链路支撑：

- 分层长期记忆与历史检索；
- Schema 驱动的内部状态工具；
- 主动监督事件生命周期；
- 多模态屏幕理解；
- 流式响应、FastAPI 与 OpenAPI；
- 自动化测试与固定评估集。

```bash
conda run -n agent pytest
conda run -n agent python evals/run_eval.py
```

[架构讲解](docs/ARCHITECTURE_WALKTHROUGH.md) · [版本记录](CHANGELOG.md)

## 项目边界

Workmate 当前是一个本地优先、单用户的个人生产力 Agent。它不替用户完成具体工作，而是让长期目标始终可见、可继续、可完成。
