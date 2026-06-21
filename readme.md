# Workmate Agent

> **A local-first, single-user productivity agent built to accompany and supervise long-term goals.**

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)
![ChromaDB](https://img.shields.io/badge/ChromaDB-FF6600?style=flat)
![OpenAI-Compatible](https://img.shields.io/badge/LLM-OpenAI_Compatible-green)
![Local-First](https://img.shields.io/badge/Architecture-Local_First-8A2BE2)

> 🇨🇳 [中文版说明书 (Chinese README)](README_zh.md)

![Workmate Agent product demo](docs/assets/product-overview.gif)

## What It Is
Workmate Agent is a local-first productivity companion. Unlike traditional chatbots that reset their context every session, Workmate maintains a persistent state across your tasks, commitments, and focus sessions. It is designed to gently remind you when you stray off-track, help you focus, and actively push long-term goals to closure.

**Project Boundaries:** This is a strictly local-first, single-user productivity agent. It is not a general-purpose AI assistant or a multi-tenant cloud service.

## Why It's Different
Traditional chatbots cram all historical conversation into the context window, leading to context pollution and confusion over what is currently true. Workmate solves this by segregating **authoritative state** (what you are doing *right now*) from **episodic memory** (what we talked about *in the past*), allowing it to behave like a true companion that tracks progress over days and weeks without hallucinating its state.

---

## Architecture

See the [Architecture Walkthrough](docs/ARCHITECTURE_WALKTHROUGH.md) for the agent loop, memory layers, internal tools, and proactive supervision flow.

---

## Key Engineering Contributions

### 1. Explicit Agent Runtime
**Challenge:** Standard LLM wrappers send user input directly to the model, making the reasoning opaque and impossible to debug.
**Solution:** Built a fully observable execution chain. Every turn passes through structured Context Planning -> Tool Planning -> Tool Execution -> Response -> Memory Writeback. The `turn_trace` records latency, tool side-effects, and memory updates without exposing messy reasoning loops to the user.

### 2. Hierarchical Memory & Episodic RAG
**Challenge:** Semantic search (RAG) on chat history often retrieves outdated information that overwrites current context.
**Solution:** Segregated memory into Working Memory (context window), Authoritative State (tasks/focus sessions stored in JSON), Long-term Cognition (hierarchical markdown), and Episodic Memory (ChromaDB RAG). RAG incorporates time decay, saliency, and task relevance, ensuring the agent always knows your *current* focus while having access to historical context.

### 3. Schema-Driven Tool Calling
**Challenge:** Giving an agent unconstrained tool access can lead to unpredictable external side-effects.
**Solution:** Tools exclusively operate on Workmate's internal state (tasks, memory, supervision preferences). Every tool strictly declares schemas, read/write permissions, and expected side effects, complete with audit records and graceful degradation paths upon failure.

### 4. Proactive Supervision State Machine
**Challenge:** Agents are typically reactive; they only work when you prompt them.
**Solution:** Engineered a background scheduler that monitors task stagnation, expiring commitments, and screen divergence. These are translated into supervision events managed by a rigid state machine (`detected -> notified -> acknowledged/snoozed -> resolved`). Screen-vision reminders are transient—they do not pollute the core RAG database.

---

## Capabilities Evidence

| Capability | Core Implementation | Observable Evidence |
| --- | --- | --- |
| **Agent Runtime** | [`agent/runtime.py`](agent/runtime.py) | `turn_trace`, `OBSERVABILITY SUMMARY` |
| **Hierarchical Memory** | [`memory/knowledge.py`](memory/knowledge.py), [`memory/context_engine.py`](memory/context_engine.py) | `memory/data/knowledge/*.md`, Model Context Panel |
| **Episodic RAG** | [`memory/search.py`](memory/search.py), [`memory/retriever.py`](memory/retriever.py) | Retrieval plan, Score breakdown, Citations |
| **Tool Calling** | [`tools/registry.py`](tools/registry.py), [`tools/executor.py`](tools/executor.py) | Tool schema, Tool trace, Audit records |
| **Supervision Loop** | [`memory/supervision_events.py`](memory/supervision_events.py) | Event state machine, Scheduler ticks |
| **Vision Companion** | [`src/LLMClient.py`](src/LLMClient.py) | Transient screen reminders |
| **API Contract** | [`src/web.py`](src/web.py) | `/docs`, `/openapi.json` |
| **Evaluation** | [`evals/run_eval.py`](evals/run_eval.py), [`evals/cases.json`](evals/cases.json) | Markdown / JSON evaluation reports |

---

## Quick Start

### Prerequisites
- **Python:** 3.12+
- **Environment:** `conda` (Highly Recommended)

### Installation
Clone the repository and set up your environment variables:
```bash
git clone https://github.com/fcsfang/workmate-agent.git
cd workmate-agent
cp .env.example .env
```

Configure your OpenAI-compatible LLM provider in `.env`:
```env
LLM_MODEL_ID=moonshotai/kimi-k2.6:free
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://openrouter.ai/api/v1
```

### Run the Agent
The startup script automatically provisions the environment (prioritizing the `agent` conda environment), installs dependencies, launches the FastAPI server, and opens your browser.

```bash
./run.sh
```

- **Web UI:** `http://127.0.0.1:7860`
- **OpenAPI Docs:** `http://127.0.0.1:7860/docs`
- **Custom Port:** `WORKMATE_PORT=7861 ./run.sh`
- **Stop Service:** Press `Ctrl+C` in the terminal.

*(Note: Vision tracking, system notifications, and TTS are optional features. Configure them via `.env`. API keys, local indices, and screenshots are excluded from version control for privacy).*

---

## Reset Local Memory

Stop the running service first, then clear conversations, tasks, profiles, observations, and local indices:

```bash
./scripts/clear_memory.sh
```

---

## Testing & Evaluation
The project includes a robust evaluation suite and CI pipeline.

```bash
# Run unit and integration tests
conda run -n agent pytest

# Run reproducible evaluation suite
conda run -n agent python evals/run_eval.py

# Basic syntax checks
conda run -n agent python -m py_compile agent/*.py memory/*.py src/*.py tools/*.py tests/*.py
```
Evaluation reports are generated in `evals/reports/`, covering intent classification, RAG recall, task management, and OpenAPI smoke tests. GitHub Actions automatically run these checks on push and pull requests.

---

## Project Structure
```text
workmate-agent/
├── agent/                  # Core Agent Runtime and turn tracing
├── memory/                 # Hierarchical state, RAG, and supervision logic
│   └── data/               # Local runtime data (Git-ignored)
├── tools/                  # Tool registry and internal state operators
├── src/                    # LLM client, CLI, and FastAPI app
├── web/                    # Local debugging UI
├── evals/                  # Fixed evaluation sets and local reporting
├── tests/                  # Pytest suite
├── scripts/                # Local maintenance scripts
└── docs/                   # Architecture documentation and product assets
```

## Documentation Links
- [Architecture Walkthrough](docs/ARCHITECTURE_WALKTHROUGH.md): Detailed agent loops, RAG design, state machine flow.
- [CHANGELOG](CHANGELOG.md): Version milestones and design changes.
