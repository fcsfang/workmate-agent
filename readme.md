# Workmate Agent

> **Keep every long-term goal in sight.**

Workmate is a personal productivity agent that stays aware of your goals, actions, and attention. It remembers where things stand, understands what you are doing now, and steps in at the right moment—turning scattered effort into sustained progress.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)
![ChromaDB](https://img.shields.io/badge/ChromaDB-FF6600?style=flat)
[![CI](https://github.com/fcsfang/workmate-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/fcsfang/workmate-agent/actions/workflows/ci.yml)

[中文](README_zh.md) · [Quick Start](#quick-start) · [Privacy](#data-and-privacy) · [Architecture](docs/ARCHITECTURE_WALKTHROUGH.md)

![Workmate Agent product demo](docs/assets/product-overview.gif)

## Your Goal Stays Active

Once a plan enters Workmate, it becomes more than a sentence.

The main task, subtasks, current progress, open commitments, and next action remain available. Refresh the page, restart the app, or return days later—the work continues from where you left it.

![A continuously updated task thread](docs/assets/task-lifecycle.png)

## See Where Action Happens

The screen is where a goal becomes real work.

Vision supervision reads screen content with the current goal in mind. It goes beyond knowing which app is open: it evaluates whether the activity is moving the task forward, then uses recent observations to distinguish a brief context switch from sustained drift.

**Current goal × screen meaning × activity trajectory → stay silent, accompany, or redirect.**

You can also trigger an immediate screen observation and receive feedback grounded in the task you are working on.

![Goal-aware vision supervision](docs/assets/vision-supervision.gif)

<details>
<summary>View the vision supervision message in detail</summary>

![Vision supervision detail](docs/assets/vision-supervision.png)

</details>

## Step In at the Right Moment

Workmate does not need to wait for you to reopen the chat.

While the local service is running, it watches for stalled tasks, finished focus sessions, approaching commitments, and screen drift. Each signal becomes a traceable supervision event until it is acknowledged, snoozed, dismissed, or resolved.

Your goal is less likely to disappear beneath the next urgent distraction.

## Every Effort Becomes Useful Context

Workmate preserves more than conversations.

Immediate task state, long-term goals, communication preferences, recurring behavior patterns, and periodic reflections are stored at different layers. Past experience returns only when it is relevant, so each session can continue along an existing thread instead of starting from a blank page.

## Data and Privacy

- Tasks, conversations, profiles, long-term knowledge, and vector indices stay on your machine by default.
- When an external model is configured, the required context is sent to that provider.
- With vision supervision enabled, a temporary screenshot is sent to the vision model and deleted locally after analysis.
- API keys, runtime memory, screenshots, and local indices are excluded from Git.

Clear all local memory at any time:

```bash
# Stop the running Workmate service first
./scripts/clear_memory.sh
```

## Quick Start

Requires Python 3.12+. Conda is recommended; the launcher can also create a local `.venv` automatically.

```bash
git clone https://github.com/fcsfang/workmate-agent.git
cd workmate-agent
cp .env.example .env
```

Configure an OpenAI-compatible model in `.env`:

```env
LLM_MODEL_ID=moonshotai/kimi-k2.6:free
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://openrouter.ai/api/v1
```

Run:

```bash
./run.sh
```

- Web UI: `http://127.0.0.1:7860`
- OpenAPI: `http://127.0.0.1:7860/docs`
- Custom port: `WORKMATE_PORT=7861 ./run.sh`
- Stop: press `Ctrl+C` in the running terminal

<details>
<summary>View the initial workspace</summary>

![Workmate Agent initial workspace](docs/assets/init.png)

</details>

## Agent Engineering

The product experience is backed by a complete agent runtime:

- Layered long-term memory and episodic retrieval
- Schema-driven internal state tools
- Proactive supervision event lifecycle
- Multimodal screen understanding
- Streaming responses, FastAPI, and OpenAPI
- Automated tests and a fixed evaluation suite

```bash
conda run -n agent pytest
conda run -n agent python evals/run_eval.py
```

[Architecture Walkthrough](docs/ARCHITECTURE_WALKTHROUGH.md) · [Changelog](CHANGELOG.md)

## Project Scope

Workmate is currently a local-first, single-user productivity agent. It does not complete the work for you; it keeps long-term goals visible, resumable, and moving toward completion.
