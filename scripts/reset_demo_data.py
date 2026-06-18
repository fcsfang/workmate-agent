#!/usr/bin/env python3
"""Reset local memory data into an interview-friendly demo state."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "memory" / "data"
ARCHIVE_DIR = ROOT / "memory" / "archive"
DAILY_DIR = DATA_DIR / "daily_summaries"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def iso_minutes(minutes: int) -> str:
    return (datetime.now() + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def backup_data() -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    target = ARCHIVE_DIR / f"demo-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if DATA_DIR.exists():
        shutil.copytree(
            DATA_DIR,
            target,
            ignore=shutil.ignore_patterns(".gitkeep", ".DS_Store"),
        )
    else:
        target.mkdir(parents=True, exist_ok=True)
    return target


def clear_runtime_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    for path in DATA_DIR.glob("*.json"):
        path.unlink()
    for path in DAILY_DIR.glob("*.json"):
        path.unlink()
    for folder in [DATA_DIR / "screenshots", DATA_DIR / "chroma"]:
        if folder.exists():
            shutil.rmtree(folder)
    (DATA_DIR / ".gitkeep").touch()
    (DAILY_DIR / ".gitkeep").touch()


def demo_payload() -> dict[str, Any]:
    now = now_text()
    earlier = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
    yesterday = (datetime.now() - timedelta(days=1, hours=2)).isoformat(timespec="seconds")
    task_id = "demo-task-agent"
    record_id = "demo-record-001"
    event_id = "demo-event-task-stale"

    task = {
        "id": task_id,
        "title": "准备 Workmate Agent 面试演示",
        "status": "active",
        "priority": "high",
        "created_at": yesterday,
        "updated_at": earlier,
        "started_at": yesterday,
        "completed_at": "",
        "abandoned_at": "",
        "due_at": iso_minutes(180),
        "last_user_update_at": earlier,
        "next_check_at": iso_minutes(30),
        "progress": [
            "已经完成 Agent Runtime、Hybrid Memory RAG、Tool Calling 和主动监督状态机。",
            "正在准备一键 demo、架构图和 3-5 分钟展示脚本。",
        ],
        "subtasks": [
            {"id": "demo-sub-run", "title": "确认一键启动流程", "status": "done", "updated_at": now},
            {"id": "demo-sub-data", "title": "准备可复现 demo 数据", "status": "active", "updated_at": now},
            {"id": "demo-sub-script", "title": "整理面试讲解脚本", "status": "planned", "updated_at": now},
        ],
        "blockers": [],
        "next_actions": [
            "运行 demo reset 后打开 Web 页面，展示任务、记忆、RAG、工具和监督事件。",
            "打开 /docs 展示 FastAPI OpenAPI schema。",
        ],
        "user_commitments": ["今天整理 V2.7 demo packaging"],
        "related_record_ids": [record_id],
    }

    record = {
        "id": record_id,
        "time": earlier,
        "user": "我今天想把 Workmate Agent 包装成一个适合简历展示的 Agent 项目。",
        "assistant": (
            "我会把重点放在可演示工程能力上：一键启动、OpenAPI、评估报告、"
            "Hybrid Memory RAG、工具调用和主动监督闭环。"
        ),
        "extracted": {
            "categories": ["project_goal", "demo_packaging"],
            "task": task["title"],
            "progress": "明确了简历展示导向，需要准备可复现 demo。",
            "blockers": [],
            "next_actions": task["next_actions"],
            "user_commitments": task["user_commitments"],
            "signals": ["resume_ready_agent_project"],
        },
        "task_state_snapshot": {
            "active_task": task["title"],
            "task_id": task_id,
            "status": "in_progress",
            "current_progress": "正在做 demo packaging。",
            "updated_at": earlier,
        },
    }

    supervision_event = {
        "id": event_id,
        "dedupe_key": f"task_stale:task:{task_id}",
        "type": "task_stale",
        "subject_type": "task",
        "subject_id": task_id,
        "subject_title": task["title"],
        "severity": "low",
        "title": "当前任务久未更新",
        "message": "当前任务【准备 Workmate Agent 面试演示】已有一段时间未更新，适合温和提醒它还被记着。",
        "display_message": "这条 demo packaging 主线还在这里，先把可复现数据和展示脚本收一下就很稳。",
        "status": "detected",
        "source": "demo_seed",
        "metadata": {"stale_hours": 26, "status": "active", "demo": True},
        "detected_at": now,
        "last_detected_at": now,
        "notified_at": "",
        "acknowledged_at": "",
        "snoozed_at": "",
        "snoozed_until": "",
        "resolved_at": "",
        "dismissed_at": "",
        "dismiss_reason": "",
        "muted_at": "",
        "muted_until": "",
        "linked_updates": [],
        "feedback_history": [
            {"action": "snoozed", "at": yesterday, "details": {"snoozed_until": earlier}},
            {"action": "acknowledged", "at": earlier, "details": {"acknowledged_at": earlier}},
        ],
        "transition_history": [
            {"from": "", "to": "detected", "at": now, "reason": "demo_seed", "details": {}},
        ],
        "last_transition_reason": "demo_seed",
        "created_at": now,
        "updated_at": now,
    }

    memory_item = {
        "id": "demo-memory-rag",
        "type": "task",
        "category": "project_goal",
        "content": "Workmate Agent 的简历亮点是本地优先 Agent Runtime、Hybrid Memory RAG、工具调用、主动监督闭环和可复现评估。",
        "task_id": task_id,
        "task_title": task["title"],
        "source_record_ids": [record_id],
        "confidence": 0.92,
        "salience": 0.9,
        "status": "active",
        "created_at": earlier,
        "updated_at": now,
        "metadata": {"demo": True},
    }

    return {
        "records.json": [record],
        "tasks.json": [task],
        "task_state.json": {
            "active_task": task["title"],
            "task_id": task_id,
            "status": "in_progress",
            "current_progress": "正在准备可复现 demo 数据。",
            "blockers": [],
            "subtasks": task["subtasks"],
            "next_action": task["next_actions"][0],
            "next_actions": task["next_actions"],
            "events": [
                {
                    "time": earlier,
                    "task": task["title"],
                    "progress": "明确 demo packaging 是下一阶段重点。",
                    "blockers": [],
                    "next_actions": task["next_actions"],
                }
            ],
            "updated_at": now,
            "last_user_input": record["user"],
            "last_agent_response": record["assistant"],
        },
        "task_events.json": [
            {"id": "demo-task-event-001", "task_id": task_id, "type": "created", "time": yesterday, "payload": {"title": task["title"]}},
            {"id": "demo-task-event-002", "task_id": task_id, "type": "status_changed", "time": earlier, "payload": {"status": "active"}},
        ],
        "commitments.json": [
            {
                "id": "demo-commit-readme",
                "owner": "user",
                "task": task["title"],
                "commitment": "今天补齐 demo packaging 文档和脚本",
                "deadline": iso_minutes(240),
                "status": "open",
                "created_at": earlier,
                "closed_at": "",
                "related_record_ids": [record_id],
            }
        ],
        "focus_sessions.json": [
            {
                "id": "demo-focus-001",
                "goal": "准备 Workmate Agent demo 展示",
                "task_id": task_id,
                "task_title": task["title"],
                "status": "active",
                "duration_minutes": 45,
                "started_at": (datetime.now() - timedelta(minutes=20)).isoformat(timespec="seconds"),
                "expected_end_at": iso_minutes(25),
                "ended_at": "",
                "elapsed_minutes": 20,
                "outcome": "",
                "created_at": now,
                "updated_at": now,
            }
        ],
        "supervision_events.json": [supervision_event],
        "supervision_messages.json": [
            {
                "id": "supervision-demo-message",
                "event_id": event_id,
                "time": now,
                "user": "",
                "assistant": supervision_event["display_message"],
                "is_supervision": True,
                "transient": True,
                "source": "demo_seed",
                "type": "task_stale",
                "task_state_snapshot": {},
                "extracted": {},
            }
        ],
        "supervision_preferences.json": {
            "enabled": True,
            "reminder_strength": "gentle",
            "min_severity": "low",
            "push_min_severity": "medium",
            "page_min_severity": "low",
            "browser_min_severity": "medium",
            "background_min_severity": "high",
            "voice_enabled": False,
            "voice_provider": "browser",
            "voice_min_severity": "medium",
            "voice_volume": 0.7,
            "voice_rate": 1.0,
            "voice_include_accompaniment": False,
            "event_type_min_severity": {},
            "default_snooze_minutes": 60,
            "default_mute_hours": 24,
            "quiet_hours_enabled": True,
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "07:00",
            "quiet_until": "",
            "notify_focus": True,
            "notify_commitments": True,
            "notify_tasks": True,
            "screen_monitor_enabled": True,
            "screen_monitor_interval_minutes": 5,
            "screen_force_message": False,
            "last_screen_check": "",
            "auto_monitor_work_hours_enabled": True,
            "work_hours_start": "09:00",
            "work_hours_end": "18:00",
            "custom_blacklist_keywords": [],
            "custom_whitelist_keywords": [],
        },
        "memory_items.json": [memory_item],
        "memory_categories.json": [
            {
                "id": "demo-category-project-goal",
                "name": "project_goal",
                "description": "项目目标与简历展示定位",
                "item_count": 1,
                "active_count": 1,
                "updated_at": now,
            }
        ],
        "memory_resources.json": [
            {
                "id": "demo-resource-record-001",
                "resource_type": "conversation_turn",
                "record_id": record_id,
                "time": earlier,
                "modality": "text",
                "local_ref": "memory/data/records.json",
                "user_preview": record["user"],
                "assistant_preview": record["assistant"],
                "extracted_categories": record["extracted"]["categories"],
                "task_id": task_id,
                "task_title": task["title"],
                "task_status": "active",
                "created_at": earlier,
                "updated_at": now,
            }
        ],
        "semantic_dialogues.json": [
            {
                "id": "demo-dialogue-001",
                "record_id": record_id,
                "time": earlier,
                "summary": "用户希望把 Workmate Agent 包装成简历可展示项目。",
                "key_points": ["简历展示", "可复现 demo", "Agent 工程亮点"],
                "task_id": task_id,
                "task_title": task["title"],
                "created_at": earlier,
                "updated_at": now,
            }
        ],
        "high_level_insights.json": [
            {
                "id": "demo-insight-agent-project",
                "type": "project_positioning",
                "content": "项目展示应优先证明 Agent Runtime、RAG、Tool Calling、Supervision Loop、Observability 和 Evaluation，而不是继续堆个人化体验。",
                "status": "active",
                "confidence": 0.9,
                "source_ids": ["demo-memory-rag"],
                "created_at": now,
                "updated_at": now,
            }
        ],
        "behavior_patterns.json": [
            {
                "id": "demo-pattern-packaging",
                "type": "demo_readiness",
                "level": "info",
                "message": "当前阶段适合把能力包装成可复现 demo，而不是继续扩展新功能。",
                "evidence": ["V2.7 目标是 Packaging & Demo Readiness"],
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ],
        "memory_conflicts.json": [],
        "reflections.json": [],
        "screen_observations.json": [
            {
                "id": "demo-screen-observation",
                "observed_at": now,
                "subject_id": task_id,
                "subject_title": task["title"],
                "subject_type": "task",
                "goal": task["title"],
                "app_name": "Visual Studio Code",
                "window_title": "workmate-agent",
                "observation": "用户正在查看项目代码和文档。",
                "goal_note": "与 demo packaging 主线相关。",
                "message_type": "companion",
                "should_message": True,
                "message": "这段还在主线上，继续把 demo 数据和讲解脚本收一下就好。",
            }
        ],
        "retrieval_index.json": [
            {
                "id": "demo-memory-rag",
                "source_type": "memory_item",
                "source_id": "demo-memory-rag",
                "type": "task",
                "text": memory_item["content"],
                "terms": ["workmate", "agent", "rag", "tool", "supervision", "evaluation", "demo"],
                "updated_at": now,
                "salience": 0.9,
                "confidence": 0.92,
                "task_id": task_id,
                "task_title": task["title"],
                "record_id": record_id,
            }
        ],
    }


def reset_demo_data(skip_backup: bool = False) -> Path | None:
    backup_path = None if skip_backup else backup_data()
    clear_runtime_files()
    payload = demo_payload()
    for name, value in payload.items():
        write_json(DATA_DIR / name, value)
    write_json(DAILY_DIR / f"{datetime.now().date().isoformat()}.json", {
        "date": datetime.now().date().isoformat(),
        "summary": "Demo 数据：Workmate Agent 正在准备可复现面试展示。",
        "main_tasks": ["准备 Workmate Agent 面试演示"],
        "completed": ["完成一键启动加固"],
        "in_progress": ["准备 demo 数据重置脚本"],
        "blockers": [],
        "next_actions": ["打开 Web 页面展示 Agent Loop、RAG、Tool Calling、Supervision 和 OpenAPI"],
        "patterns": ["简历展示优先于个人化微调"],
    })
    return backup_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset Workmate Agent local data into a reproducible demo state.")
    parser.add_argument("--no-backup", action="store_true", help="Skip backing up current memory/data into memory/archive.")
    args = parser.parse_args()

    backup_path = reset_demo_data(skip_backup=args.no_backup)
    print("Demo data reset complete.")
    if backup_path:
        print(f"Previous data backup: {backup_path.relative_to(ROOT)}")
    print("Next: run ./run.sh and open http://127.0.0.1:7860")


if __name__ == "__main__":
    main()
