import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from .core import WorkmateAgent
except ImportError:
    from core import WorkmateAgent

from memory import MemoryManager, Notifier
from observability import get_provider_trace_summary
from tts import synthesize_speech

WEB_ROOT = PROJECT_ROOT / "web"


def model_to_dict(model: BaseModel, exclude_none: bool = False) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=exclude_none)
    return model.dict(exclude_none=exclude_none)


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class FocusRequest(BaseModel):
    action: str
    goal: str = ""
    duration_minutes: int = 45
    outcome: str = ""


class TaskStatusRequest(BaseModel):
    id: str
    status: str


class SupervisionEventRequest(BaseModel):
    id: str
    action: str
    hours: int = 24
    minutes: int = 0


class SupervisionPreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: Optional[bool] = None
    work_hours_enabled: Optional[bool] = None
    work_hours_start: Optional[str] = None
    work_hours_end: Optional[str] = None
    cooldown_minutes: Optional[int] = None
    default_snooze_minutes: Optional[int] = None
    reminder_strength: Optional[str] = None
    page_min_severity: Optional[str] = None
    browser_min_severity: Optional[str] = None
    background_min_severity: Optional[str] = None
    push_min_severity: Optional[str] = None
    voice_enabled: Optional[bool] = None
    voice_provider: Optional[str] = None
    voice_min_severity: Optional[str] = None
    voice_volume: Optional[float] = None
    voice_rate: Optional[float] = None
    voice_include_accompaniment: Optional[bool] = None
    screen_force_message: Optional[bool] = None
    custom_blacklist_keywords: Optional[list[str]] = None
    custom_whitelist_keywords: Optional[list[str]] = None
    event_type_min_severity: Optional[Dict[str, str]] = None


class SubTask(BaseModel):
    id: Optional[str] = ""
    title: str
    status: Optional[str] = "active"


class Task(BaseModel):
    id: Optional[str] = ""
    title: Optional[str] = ""
    status: Optional[str] = "inbox"
    priority: Optional[str] = "normal"
    created_at: Optional[str] = ""
    updated_at: Optional[str] = ""
    started_at: Optional[str] = ""
    completed_at: Optional[str] = ""
    abandoned_at: Optional[str] = ""
    due_at: Optional[str] = ""
    last_user_update_at: Optional[str] = ""
    next_check_at: Optional[str] = ""
    progress: List[Any] = []
    subtasks: List[SubTask] = []
    blockers: List[Any] = []
    next_actions: List[Any] = []
    user_commitments: List[Any] = []
    related_record_ids: List[str] = []


class TaskView(BaseModel):
    current: Optional[Task] = None
    active: List[Task] = []
    inbox: List[Task] = []
    completed: List[Task] = []
    abandoned: List[Task] = []


class TaskState(BaseModel):
    active_task: Optional[str] = ""
    task_id: Optional[str] = ""
    status: Optional[str] = ""
    current_progress: Optional[str] = ""
    updated_at: Optional[str] = ""


class Commitment(BaseModel):
    id: Optional[str] = ""
    owner: Optional[str] = "user"
    task: Optional[str] = ""
    commitment: Optional[str] = ""
    status: Optional[str] = "open"
    created_at: Optional[str] = ""
    closed_at: Optional[str] = ""
    related_record_ids: List[str] = []


class SupervisionEvent(BaseModel):
    id: Optional[str] = ""
    dedupe_key: Optional[str] = ""
    type: Optional[str] = ""
    subject_type: Optional[str] = ""
    subject_id: Optional[str] = ""
    subject_title: Optional[str] = ""
    severity: Optional[str] = "low"
    title: Optional[str] = ""
    message: Optional[str] = ""
    display_message: Optional[str] = ""
    status: Optional[str] = "detected"
    source: Optional[str] = ""
    created_at: Optional[str] = ""
    updated_at: Optional[str] = ""
    snoozed_until: Optional[str] = ""
    muted_until: Optional[str] = ""
    dismissed_at: Optional[str] = ""
    dismiss_reason: Optional[str] = ""
    last_transition_reason: Optional[str] = ""
    feedback_history: List[Dict[str, Any]] = []
    transition_history: List[Dict[str, Any]] = []
    metadata: Optional[Dict[str, Any]] = None


class SupervisionEventsState(BaseModel):
    active: List[SupervisionEvent] = []
    snoozed: List[SupervisionEvent] = []
    muted: List[SupervisionEvent] = []
    recent: List[SupervisionEvent] = []
    screen_observations: List[Dict[str, Any]] = []
    preferences: Dict[str, Any] = {}
    feedback_stats: Dict[str, Any] = {}
    strategy: Dict[str, Any] = {}
    counts: Dict[str, int] = {}
    state_machine: Dict[str, Any] = {}


class MemoryItem(BaseModel):
    id: Optional[str] = ""
    type: Optional[str] = "memory"
    category: Optional[str] = ""
    content: Optional[str] = ""
    task_id: Optional[str] = ""
    task_title: Optional[str] = ""
    source_record_ids: List[str] = []
    confidence: Optional[float] = 0.0
    salience: Optional[float] = 0.0
    status: Optional[str] = "active"
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = ""
    updated_at: Optional[str] = ""
    last_accessed_at: Optional[str] = ""


class MemoryCategory(BaseModel):
    id: Optional[str] = ""
    name: Optional[str] = ""
    description: Optional[str] = ""


class BehaviorPatterns(BaseModel):
    active: List[Dict[str, Any]] = []
    recent: List[Dict[str, Any]] = []


class FocusSession(BaseModel):
    id: Optional[str] = ""
    goal: Optional[str] = ""
    task_id: Optional[str] = ""
    task_title: Optional[str] = ""
    status: Optional[str] = ""
    duration_minutes: Optional[int] = 45
    started_at: Optional[str] = ""
    expected_end_at: Optional[str] = ""
    ended_at: Optional[str] = ""
    elapsed_minutes: Optional[int] = 0
    outcome: Optional[str] = ""
    created_at: Optional[str] = ""
    updated_at: Optional[str] = ""


class ToolCallTrace(BaseModel):
    call_id: Optional[str] = ""
    tool: Optional[str] = ""
    status: Optional[str] = ""
    read_only: Optional[bool] = True
    duration_ms: Optional[float] = 0.0
    reason: Optional[str] = ""
    arguments: Dict[str, Any] = {}
    observation: Dict[str, Any] = {}
    input_schema: Dict[str, Any] = {}
    output_schema: Dict[str, Any] = {}
    side_effects: List[str] = []
    decision_source: Optional[str] = ""
    planner_call_index: Optional[int] = 0
    audit_record: Dict[str, Any] = {}
    recoverable: Optional[bool] = False
    recovery_hint: Optional[str] = ""
    error: Optional[str] = None
    started_at: Optional[str] = ""
    completed_at: Optional[str] = ""


class ObservabilitySummary(BaseModel):
    turn_id: Optional[str] = ""
    status: Optional[str] = ""
    duration_ms: Optional[int] = 0
    started_at: Optional[str] = ""
    completed_at: Optional[str] = ""
    stage_count: Optional[int] = 0
    slowest_stage: Dict[str, Any] = {}
    stage_timeline: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    model_calls: Dict[str, Any] = {}
    provider_trace: Dict[str, Any] = {}
    provider_detail: Dict[str, Any] = {}
    usage: Dict[str, Any] = {}
    rag: Dict[str, Any] = {}
    rag_explainability: Dict[str, Any] = {}
    tools: Dict[str, Any] = {}
    tool_trace: Dict[str, Any] = {}
    memory: Dict[str, Any] = {}
    supervision: Dict[str, Any] = {}
    context: Dict[str, Any] = {}


class TurnTrace(BaseModel):
    turn_id: Optional[str] = ""
    status: Optional[str] = ""
    duration_ms: Optional[int] = 0
    stages: List[Dict[str, Any]] = []
    tool_calls: List[ToolCallTrace] = []
    tool_plan: Dict[str, Any] = {}
    retrieval_plan: Dict[str, Any] = {}
    provider_trace: Dict[str, Any] = {}
    observability: Optional[ObservabilitySummary] = None


class MemoryStateResponse(BaseModel):
    count: int
    recent: List[Dict[str, Any]] = []
    summary: str = ""
    structured_summary: str = ""
    recent_summary: Dict[str, Any] = {}
    recent_summary_context: str = ""
    task_state: Optional[TaskState] = None
    task_view: Optional[TaskView] = None
    open_commitments: List[Commitment] = []
    user_profile: Dict[str, Any] = {}
    long_term_knowledge_files: List[Dict[str, Any]] = []
    memory_items: List[MemoryItem] = []
    memory_categories: List[MemoryCategory] = []
    memory_resources: List[Dict[str, Any]] = []
    semantic_dialogues: List[Dict[str, Any]] = []
    high_level_insights: List[Dict[str, Any]] = []
    behavior_patterns: Optional[BehaviorPatterns] = None
    dashboard: Dict[str, Any] = {}
    memory_conflicts: List[Dict[str, Any]] = []
    reflections: List[Dict[str, Any]] = []
    supervision: Dict[str, Any] = {}
    supervision_events: Optional[SupervisionEventsState] = None
    focus_session: Optional[FocusSession] = None
    support_knowledge: Dict[str, Any] = {}
    tool_calls: List[Dict[str, Any]] = []
    tool_schemas: List[Dict[str, Any]] = []
    turn_trace: Optional[TurnTrace] = None
    observability: Optional[ObservabilitySummary] = None
    provider_trace_recent: Dict[str, Any] = {}
    last_reminder_control: Dict[str, Any] = {}
    memory_pipeline: Dict[str, Any] = {}
    last_pipeline_result: Dict[str, Any] = {}
    context_stats: Dict[str, Any] = {}
    retrieval_plan: Dict[str, Any] = {}


class ContextStateResponse(BaseModel):
    messages: List[Dict[str, Any]] = []
    message_count: int = 0
    context_stats: Dict[str, Any] = {}
    retrieval_plan: Dict[str, Any] = {}
    open_commitments: List[Commitment] = []
    task_view: Optional[TaskView] = None
    user_profile: Dict[str, Any] = {}
    long_term_knowledge_files: List[Dict[str, Any]] = []
    memory_items: List[MemoryItem] = []
    memory_categories: List[MemoryCategory] = []
    memory_resources: List[Dict[str, Any]] = []
    semantic_dialogues: List[Dict[str, Any]] = []
    high_level_insights: List[Dict[str, Any]] = []
    behavior_patterns: Optional[BehaviorPatterns] = None
    dashboard: Dict[str, Any] = {}
    memory_conflicts: List[Dict[str, Any]] = []
    reflections: List[Dict[str, Any]] = []
    supervision: Dict[str, Any] = {}
    supervision_events: Optional[SupervisionEventsState] = None
    focus_session: Optional[FocusSession] = None
    support_knowledge: Dict[str, Any] = {}
    tool_calls: List[Dict[str, Any]] = []
    tool_schemas: List[Dict[str, Any]] = []
    turn_trace: Optional[TurnTrace] = None
    observability: Optional[ObservabilitySummary] = None
    provider_trace_recent: Dict[str, Any] = {}
    last_pipeline_result: Dict[str, Any] = {}


class DashboardToday(BaseModel):
    date: str
    focus_completed: int
    focus_minutes: int
    tasks_completed: int
    commitments_closed: int
    open_commitments: int
    due_or_overdue_commitments: int
    active_supervision_events: int


class DashboardMainline(BaseModel):
    id: str = ""
    title: str = "暂无当前任务"
    status: str = ""
    has_focus: bool = False


class DashboardLoad(BaseModel):
    open_tasks: int
    blocked_tasks: int
    task_dispersion: str
    active_patterns: int


class DashboardWeek(BaseModel):
    start: str
    focus_completed: int
    focus_minutes: int
    tasks_completed: int
    commitments_opened: int
    commitments_closed: int
    commitment_fulfillment_rate: float
    active_days: int


class DashboardSuggestion(BaseModel):
    type: str = "general"
    level: str = "info"
    text: str = "暂无建议"
    ref_task_id: str = ""
    ref_event_id: str = ""


class DashboardStateResponse(BaseModel):
    today: DashboardToday
    mainline: DashboardMainline
    load: DashboardLoad
    week: DashboardWeek
    suggestion: DashboardSuggestion
    quick_actions: List[Dict[str, Any]] = []


class SupervisionEventUpdateResponse(BaseModel):
    event: Optional[Dict[str, Any]] = None
    supervision_events: SupervisionEventsState
    memory: MemoryStateResponse
    context: ContextStateResponse


class SupervisionPreferencesUpdateResponse(BaseModel):
    preferences: Dict[str, Any]
    supervision_events: SupervisionEventsState


class SchedulerTickResponse(BaseModel):
    checked_events: int
    notified_events: int
    notified_event_ids: List[str] = []
    supervision_events: SupervisionEventsState


class NotifyStatusResponse(BaseModel):
    enabled_channels: List[str]
    local_configured: bool
    bark_configured: bool
    lark_configured: bool


class NotifyTestResponse(BaseModel):
    success: bool
    error: Optional[str] = None


class FocusResponse(BaseModel):
    session: Optional[Dict[str, Any]] = None
    focus_session: Dict[str, Any]
    memory: MemoryStateResponse
    context: ContextStateResponse


class TaskUpdateStatusResponse(BaseModel):
    task_view: Optional[Dict[str, Any]] = None
    task_details: Optional[Dict[str, Any]] = None
    memory: MemoryStateResponse
    context: ContextStateResponse


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    provider: str = "xfyun"


class PrivacyDataFile(BaseModel):
    path: str
    size_bytes: int
    modified_at: str
    category: str
    exportable: bool
    sensitive: bool
    exclusion_reason: str = ""


class PrivacyInventoryResponse(BaseModel):
    data_root: str
    file_count: int
    total_bytes: int
    exportable_file_count: int
    exportable_bytes: int
    sensitive_file_count: int
    files: List[PrivacyDataFile] = []
    export_policy: Dict[str, List[str]] = {}


class PrivacyExportResponse(BaseModel):
    filename: str
    created_at: str
    file_count: int
    total_bytes: int
    download_url: str
    excluded: List[str] = []


class ChatStreamDeltaEvent(BaseModel):
    type: str = "delta"
    content: str


class ChatStreamDoneEvent(BaseModel):
    type: str = "done"
    memory: MemoryStateResponse
    context: ContextStateResponse
    tool_calls: List[Dict[str, Any]] = []
    tool_schemas: List[Dict[str, Any]] = []
    turn_trace: Optional[TurnTrace] = None
    observability: Optional[ObservabilitySummary] = None



class WorkmateWebApp:
    def __init__(self, memory_manager=None, notifier=None, start_background=None):
        import threading

        self.memory_manager = memory_manager or MemoryManager()
        self.agent = None
        self.notifier = notifier or Notifier()

        if start_background is None:
            start_background = os.getenv("WORKMATE_DISABLE_SCHEDULER", "").lower() not in {"1", "true", "yes"}
        if start_background:
            threading.Thread(target=self.start_scheduler, daemon=True).start()

    def get_agent(self):
        if self.agent is None:
            self.agent = WorkmateAgent(memory_manager=self.memory_manager)
        return self.agent

    def chat(self, prompt):
        response = self.get_agent().invoke(prompt)
        return {
            "response": response,
            "memory": self.memory_state(prompt),
            "context": self.context_state(prompt),
            "tool_calls": self.tool_state(),
            "tool_schemas": self.tool_schema_state(),
            "turn_trace": self.turn_trace_state(),
            "observability": self.observability_state(),
        }

    def chat_stream(self, prompt):
        for chunk in self.get_agent().invoke_stream(prompt):
            yield {"type": "delta", "content": chunk}
        yield {
            "type": "done",
            "memory": self.memory_state(prompt),
            "context": self.context_state(prompt),
            "tool_calls": self.tool_state(),
            "tool_schemas": self.tool_schema_state(),
            "turn_trace": self.turn_trace_state(),
            "observability": self.observability_state(),
        }

    def memory_state(self, current_prompt=""):
        records = self.memory_manager.load_records()
        recent_records = self.memory_manager.recent_records_with_transient_supervision(limit=30)
        behavior_patterns = self.memory_manager.get_behavior_patterns()
        dashboard = self.memory_manager.get_dashboard_state()
        context_debug = self.memory_manager.build_context_debug()
        return {
            "count": len(records),
            "recent": recent_records,
            "summary": self.memory_manager.get_memory_summary(),
            "structured_summary": self.memory_manager.get_structured_memory_summary(),
            "recent_summary": self.memory_manager.get_recent_summary(days=7),
            "recent_summary_context": self.memory_manager.get_recent_summary_context(days=7),
            "task_state": self.memory_manager.get_task_state(),
            "task_view": self.memory_manager.get_task_view(),
            "open_commitments": self.memory_manager.get_open_commitments(),
            "user_profile": self.memory_manager.get_user_profile(),
            "long_term_knowledge_files": self.memory_manager.get_long_term_knowledge_files(),
            "memory_items": self.memory_manager.get_memory_items(limit=30),
            "memory_categories": self.memory_manager.get_memory_categories(limit=12),
            "memory_resources": self.memory_manager.get_memory_resources(limit=12),
            "semantic_dialogues": self.memory_manager.get_semantic_dialogues(limit=12),
            "high_level_insights": self.memory_manager.get_high_level_insights(limit=12),
            "behavior_patterns": behavior_patterns,
            "dashboard": dashboard,
            "memory_conflicts": self.memory_manager.get_memory_conflicts(),
            "reflections": self.memory_manager.get_reflections(),
            "supervision": self.memory_manager.get_supervision_state(),
            "supervision_events": self.memory_manager.get_supervision_event_state(current_prompt),
            "focus_session": self.memory_manager.get_focus_session_state(),
            "support_knowledge": self.memory_manager.get_support_knowledge_state(current_prompt),
            "tool_calls": self.tool_state(),
            "tool_schemas": self.tool_schema_state(),
            "turn_trace": self.turn_trace_state(),
            "observability": self.observability_state(),
            "provider_trace_recent": self.provider_trace_state(),
            "last_reminder_control": self.memory_manager.last_reminder_control,
            "memory_pipeline": context_debug.get("memory_pipeline", {}),
            "last_pipeline_result": context_debug.get("last_pipeline_result", {}),
            "context_stats": context_debug.get("context_stats", {}),
            "retrieval_plan": context_debug.get("retrieval_plan", {}),
        }

    def context_state(self, current_prompt=""):
        if self.agent and self.agent.get_last_context():
            messages = self.agent.get_last_context()
        else:
            messages = self.memory_manager.build_context_debug().get("messages", [])
        context_debug = self.memory_manager.build_context_debug(current_prompt) if current_prompt else {}
        return {
            "messages": messages,
            "message_count": len(messages),
            "context_stats": self.memory_manager.context_compressor.estimate_context(messages),
            "retrieval_plan": context_debug.get("retrieval_plan", {}),
            "open_commitments": self.memory_manager.get_open_commitments(),
            "task_view": self.memory_manager.get_task_view(),
            "user_profile": self.memory_manager.get_user_profile(),
            "long_term_knowledge_files": self.memory_manager.get_long_term_knowledge_files(),
            "memory_items": self.memory_manager.get_memory_items(limit=20),
            "memory_categories": self.memory_manager.get_memory_categories(limit=10),
            "memory_resources": self.memory_manager.get_memory_resources(limit=10),
            "semantic_dialogues": self.memory_manager.get_semantic_dialogues(limit=10),
            "high_level_insights": self.memory_manager.get_high_level_insights(limit=10),
            "behavior_patterns": self.memory_manager.get_behavior_patterns(),
            "dashboard": self.memory_manager.get_dashboard_state(),
            "memory_conflicts": self.memory_manager.get_memory_conflicts(),
            "reflections": self.memory_manager.get_reflections(),
            "supervision": self.memory_manager.get_supervision_state(),
            "supervision_events": self.memory_manager.get_supervision_event_state(),
            "focus_session": self.memory_manager.get_focus_session_state(),
            "support_knowledge": self.memory_manager.get_support_knowledge_state(""),
            "tool_calls": self.tool_state(),
            "tool_schemas": self.tool_schema_state(),
            "turn_trace": self.turn_trace_state(),
            "observability": self.observability_state(),
            "provider_trace_recent": self.provider_trace_state(),
            "last_reminder_control": self.memory_manager.last_reminder_control,
            "last_pipeline_result": self.memory_manager.last_pipeline_result,
        }

    def focus(self, payload):
        action = str(payload.get("action", "")).strip().lower()
        if action == "start":
            goal = str(payload.get("goal", "")).strip()
            duration_minutes = int(payload.get("duration_minutes", 45) or 45)
            session = self.memory_manager.start_focus_session(goal, duration_minutes=duration_minutes)
        elif action == "complete":
            outcome = str(payload.get("outcome", "")).strip()
            session = self.memory_manager.complete_focus_session(outcome=outcome)
        elif action == "abandon":
            outcome = str(payload.get("outcome", "")).strip()
            session = self.memory_manager.abandon_focus_session(outcome=outcome)
        else:
            raise ValueError("Unknown focus action")

        return {
            "session": session,
            "focus_session": self.memory_manager.get_focus_session_state(),
            "memory": self.memory_state(),
            "context": self.context_state(),
        }

    def tool_state(self):
        if not self.agent:
            return []
        return self.agent.get_last_tool_calls()

    def tool_schema_state(self):
        return self.get_agent().get_tool_schemas()

    def turn_trace_state(self):
        if not self.agent:
            return {}
        return self.agent.get_last_turn_trace()

    def observability_state(self):
        trace = self.turn_trace_state()
        if not isinstance(trace, dict):
            return {}
        return trace.get("observability", {})

    def provider_trace_state(self):
        return get_provider_trace_summary(limit=20)

    def dashboard_state(self):
        return self.memory_manager.get_dashboard_state()

    def privacy_inventory(self):
        return self.memory_manager.get_privacy_inventory()

    def export_local_data(self):
        return self.memory_manager.export_local_data()

    def resolve_local_export(self, filename):
        return self.memory_manager.resolve_local_export(filename)

    def update_task_status(self, payload):
        task_id = payload.get("id")
        status = payload.get("status")
        if not task_id or not status:
            raise ValueError("id and status are required")
        res = self.memory_manager.update_task_status(task_id, status)
        return {
            "task_view": res.get("task_view"),
            "task_details": res.get("updated_task"),
            "memory": self.memory_state(),
            "context": self.context_state(),
        }

    def supervision_events(self):
        return self.memory_manager.get_supervision_event_state()

    def update_supervision_event(self, payload):
        event_id = str(payload.get("id", "")).strip()
        action = str(payload.get("action", "")).strip()
        hours = int(payload.get("hours", 24) or 24)
        minutes = int(payload.get("minutes", 0) or 0)
        if not event_id or not action:
            raise ValueError("id and action are required")
        event = self.memory_manager.update_supervision_event(event_id, action, hours=hours, minutes=minutes)
        return {
            "event": event,
            "supervision_events": self.memory_manager.get_supervision_event_state(),
            "memory": self.memory_state(),
            "context": self.context_state(),
        }

    def supervision_preferences(self):
        return self.memory_manager.get_supervision_preferences()

    def update_supervision_preferences(self, payload):
        preferences = self.memory_manager.update_supervision_preferences(payload)
        return {
            "preferences": preferences,
            "supervision_events": self.memory_manager.get_supervision_event_state(),
        }

    def start_scheduler(self):
        import time

        time.sleep(5)
        while True:
            try:
                self.run_background_checks()
            except Exception as e:
                print(f"[Background Scheduler Error] {e}", file=sys.stderr)
            time.sleep(60)

    def run_background_checks(self):
        return self.scheduler_tick()

    def scheduler_tick(self):
        events = self.memory_manager.refresh_supervision_events()
        notified_event_ids = []
        for event in events:
            if not self.memory_manager.supervision_event_manager.should_notify(event, channel="background"):
                continue
            title = event.get("title") or "Workmate Agent 提醒"
            body = event.get("display_message") or event.get("message") or "有一个事项需要你稍后回来处理。"
            self.notifier.send_notification(title, body)
            self.memory_manager.update_supervision_event(event.get("id", ""), "mark_notified")
            notified_event_ids.append(event.get("id", ""))
        return {
            "checked_events": len(events),
            "notified_events": len(notified_event_ids),
            "notified_event_ids": notified_event_ids,
            "supervision_events": self.memory_manager.get_supervision_event_state(),
        }


APP = WorkmateWebApp()
app = FastAPI(
    title="Workmate Agent API",
    description="Local API for chat, memory, focus sessions, supervision events, and runtime observability.",
    version="2.9.0",
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse({"error": detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/api/memory", summary="Get current memory state", response_model=MemoryStateResponse)
async def get_memory():
    return APP.memory_state()


@app.get("/api/context", summary="Get latest model context and debug state", response_model=ContextStateResponse)
async def get_context():
    return APP.context_state()


@app.get("/api/dashboard", summary="Get today dashboard state", response_model=DashboardStateResponse)
async def get_dashboard():
    return APP.dashboard_state()


@app.get("/api/privacy/inventory", summary="Inspect local agent data", response_model=PrivacyInventoryResponse)
async def get_privacy_inventory():
    return APP.privacy_inventory()


@app.post("/api/privacy/export", summary="Create a portable local data export", response_model=PrivacyExportResponse)
async def post_privacy_export():
    return APP.export_local_data()


@app.get("/api/privacy/exports/{filename}", summary="Download a generated local data export")
async def get_privacy_export(filename: str):
    export_path = APP.resolve_local_export(filename)
    return FileResponse(export_path, media_type="application/zip", filename=export_path.name)


@app.post("/api/scheduler/tick", summary="Run one supervision scheduler tick", response_model=SchedulerTickResponse)
async def post_scheduler_tick():
    return APP.scheduler_tick()


@app.get("/api/supervision/events", summary="Get active supervision events", response_model=SupervisionEventsState)
async def get_supervision_events():
    return APP.supervision_events()


@app.post("/api/supervision/events", summary="Update a supervision event", response_model=SupervisionEventUpdateResponse)
async def post_supervision_events(payload: SupervisionEventRequest):
    return APP.update_supervision_event(model_to_dict(payload))


@app.get("/api/supervision/preferences", summary="Get supervision preferences", response_model=Dict[str, Any])
async def get_supervision_preferences():
    return APP.supervision_preferences()


@app.post("/api/supervision/preferences", summary="Update supervision preferences", response_model=SupervisionPreferencesUpdateResponse)
async def post_supervision_preferences(payload: SupervisionPreferencesRequest):
    return APP.update_supervision_preferences(model_to_dict(payload, exclude_none=True))


@app.get("/api/notify/status", summary="Get notification channel status", response_model=NotifyStatusResponse)
async def get_notify_status():
    channels = [c.strip() for c in os.getenv("PUSH_CHANNELS", "").split(",") if c.strip()]
    return {
        "enabled_channels": channels,
        "local_configured": True,
        "bark_configured": bool(os.getenv("BARK_KEY")),
        "lark_configured": bool(os.getenv("LARK_WEBHOOK_URL")),
    }


@app.post("/api/notify/test", summary="Send a test notification", response_model=NotifyTestResponse)
async def post_notify_test():
    try:
        APP.notifier.send_notification(
            "自检测试通知 🔔",
            "这是一条来自 Workmate Agent 的自检测试通知，听到/看到声音表示配置正确！",
        )
        return {"success": True}
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.post("/api/tts/speech", summary="Synthesize short reminder speech")
async def post_tts_speech(payload: TTSRequest):
    try:
        audio, media_type = synthesize_speech(payload.text, provider=payload.provider)
        return Response(content=audio, media_type=media_type)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/focus", summary="Start, complete, or abandon a focus session", response_model=FocusResponse)
async def post_focus(payload: FocusRequest):
    return APP.focus(model_to_dict(payload))


@app.post("/api/task/update-status", summary="Update task status", response_model=TaskUpdateStatusResponse)
async def post_task_update_status(payload: TaskStatusRequest):
    return APP.update_task_status(model_to_dict(payload))


def stream_chat_events(prompt: str) -> Generator[str, None, None]:
    try:
        for event in APP.chat_stream(prompt):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    except Exception as exc:
        error_event = {"type": "error", "error": str(exc)}
        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"


@app.post("/api/chat", summary="Send a chat prompt and stream the response")
async def post_chat(payload: ChatRequest):
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    return StreamingResponse(
        stream_chat_events(prompt),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/{file_path:path}", include_in_schema=False)
async def static_file(file_path: str):
    safe_path = file_path.lstrip("/")
    resolved_path = (WEB_ROOT / safe_path).resolve()
    web_root = WEB_ROOT.resolve()
    if web_root not in resolved_path.parents and resolved_path != web_root:
        raise HTTPException(status_code=403, detail="Forbidden")
    if resolved_path.is_file():
        return FileResponse(resolved_path)
    raise HTTPException(status_code=404, detail="Not found")


def run_web(host="127.0.0.1", port=7860):
    import uvicorn

    print(f"Workmate Web 已启动：http://{host}:{port}")
    print(f"OpenAPI 文档：http://{host}:{port}/docs")
    print("按 Ctrl+C 结束服务。")
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    run_web()
