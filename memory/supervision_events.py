import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import memory_data_path


class SupervisionEventManager:
    ACTIVE_STATUSES = {"detected", "notified", "acknowledged"}
    PAUSED_STATUSES = {"snoozed", "muted"}
    FINAL_STATUSES = {"resolved", "dismissed"}
    VALID_STATUSES = ACTIVE_STATUSES | PAUSED_STATUSES | FINAL_STATUSES
    STATE_LABELS = {
        "detected": "已发现",
        "notified": "已提醒",
        "acknowledged": "已确认",
        "snoozed": "稍后提醒",
        "muted": "已静音",
        "resolved": "已完成",
        "dismissed": "已关闭",
    }

    def __init__(
        self,
        events_path: Optional[str] = None,
        preferences_path: Optional[str] = None,
        observations_path: Optional[str] = None,
    ):
        self.events_path = Path(events_path) if events_path else memory_data_path("supervision_events.json")
        self.preferences_path = (
            Path(preferences_path) if preferences_path else memory_data_path("supervision_preferences.json")
        )
        self.observations_path = (
            Path(observations_path)
            if observations_path
            else self.events_path.parent / "screen_observations.json"
        )
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        self.observations_path.parent.mkdir(parents=True, exist_ok=True)
        self.llm_client = None

    def set_llm_client(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def load_events(self) -> List[Dict[str, Any]]:
        if not self.events_path.exists() or self.events_path.stat().st_size == 0:
            return []
        try:
            with self.events_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [event for event in (self._normalize_event(item) for item in data) if event]

    def load_preferences(self) -> Dict[str, Any]:
        defaults = self.default_preferences()
        if not self.preferences_path.exists() or self.preferences_path.stat().st_size == 0:
            return defaults
        try:
            with self.preferences_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return defaults
        if not isinstance(data, dict):
            return defaults
        return self._normalize_preferences({**defaults, **data})

    def save_preferences(self, preferences: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_preferences({**self.default_preferences(), **preferences})
        with self.preferences_path.open("w", encoding="utf-8") as file:
            json.dump(normalized, file, ensure_ascii=False, indent=2)
        return normalized

    def update_preferences(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        preferences = self.load_preferences()
        for key, value in (updates or {}).items():
            if key not in preferences:
                continue
            if key == "event_type_min_severity" and isinstance(value, dict):
                merged = preferences.get("event_type_min_severity", {})
                if not isinstance(merged, dict):
                    merged = {}
                for event_type, channel_values in value.items():
                    if not isinstance(channel_values, dict):
                        continue
                    current = merged.get(event_type, {})
                    if not isinstance(current, dict):
                        current = {}
                    current.update(channel_values)
                    merged[event_type] = current
                preferences[key] = merged
            else:
                preferences[key] = value
        return self.save_preferences(preferences)

    def apply_natural_language_control(self, text: str, llm_client: Any = None) -> Dict[str, Any]:
        updates = self._llm_natural_language_updates(text, llm_client) or self._natural_language_updates(text)
        if not updates:
            return {"applied": False, "reason": "no_explicit_reminder_control"}
        preferences = self.update_preferences(updates["preferences"])
        return {
            "applied": True,
            "intent": updates["intent"],
            "summary": updates["summary"],
            "source": updates.get("source", "rule"),
            "preferences": preferences,
        }

    def default_preferences(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "reminder_strength": "gentle",
            "min_severity": "low",
            "push_min_severity": "medium",
            "page_min_severity": "low",
            "browser_min_severity": "medium",
            "background_min_severity": "high",
            "voice_enabled": False,
            "voice_provider": os.getenv("TTS_PROVIDER", "browser").strip().lower() or "browser",
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
        }

    def save_events(self, events: List[Dict[str, Any]]) -> None:
        with self.events_path.open("w", encoding="utf-8") as file:
            json.dump(events[-500:], file, ensure_ascii=False, indent=2)

    def load_screen_observations(self) -> List[Dict[str, Any]]:
        if not self.observations_path.exists() or self.observations_path.stat().st_size == 0:
            return []
        try:
            with self.observations_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def save_screen_observations(self, observations: List[Dict[str, Any]]) -> None:
        with self.observations_path.open("w", encoding="utf-8") as file:
            json.dump(observations[-80:], file, ensure_ascii=False, indent=2)

    def get_event(self, event_id: str) -> Dict[str, Any]:
        for event in self.load_events():
            if event.get("id") == event_id:
                return event
        raise ValueError(f"supervision event not found: {event_id}")

    def detect_events(
        self,
        focus_state: Dict[str, Any],
        commitments: List[Dict[str, Any]],
        task_view: Dict[str, Any],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        events = self.load_events()
        now = datetime.now()
        self._reactivate_paused_events(events, now)
        candidates = []
        focus_candidate = self._focus_expired_candidate(focus_state, now)
        if focus_candidate:
            candidates.append(focus_candidate)
        candidates.extend(self._commitment_deadline_candidates(commitments, now))
        stale_candidate = self._stale_task_candidate(task_view, now)
        if stale_candidate:
            candidates.append(stale_candidate)
        screen_candidate = self._screen_deviation_candidate(focus_state, task_view, now)
        if screen_candidate:
            candidates.append(screen_candidate)

        copy_policy = self._copy_policy(user_profile or {})
        candidates = [self._apply_copy_policy(candidate, copy_policy) for candidate in candidates]

        for candidate in candidates:
            events = self._upsert_candidate(events, candidate, now)

        self._auto_resolve_missing_events(events, candidates, now)
        self.save_events(events)
        return self.build_state(events=events, user_profile=user_profile)["active"]

    def build_state(
        self,
        events: Optional[List[Dict[str, Any]]] = None,
        limit: int = 12,
        support_state: Optional[Dict[str, Any]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        events = events if events is not None else self.load_events()
        self._reactivate_paused_events(events, datetime.now())
        preferences = self.load_preferences()
        feedback_stats = self._feedback_stats(events)
        copy_policy = self._copy_policy(user_profile or {})
        active = [
            event for event in events
            if event.get("status") in self.ACTIVE_STATUSES
        ]
        snoozed = [event for event in events if self._is_snoozed_now(event)]
        muted = [event for event in events if self._is_muted_now(event)]
        recent = sorted(events, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit]
        screen_observations = self._recent_screen_observations(limit=limit)
        active_sorted = sorted(active, key=lambda item: (self._severity_rank(item), item.get("updated_at", "")), reverse=True)
        return {
            "active": active_sorted[:limit],
            "snoozed": sorted(snoozed, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit],
            "muted": sorted(muted, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit],
            "recent": recent,
            "screen_observations": screen_observations,
            "preferences": preferences,
            "feedback_stats": feedback_stats,
            "strategy": self._build_strategy(
                preferences,
                feedback_stats,
                support_state=support_state,
                copy_policy=copy_policy,
            ),
            "counts": {
                "active": len(active),
                "snoozed": len(snoozed),
                "muted": len(muted),
                "resolved": len([event for event in events if event.get("status") == "resolved"]),
                "dismissed": len([event for event in events if event.get("status") == "dismissed"]),
                "total": len(events),
            },
            "state_machine": self._state_machine_summary(events),
        }

    def mark_notified(self, event_id: str) -> Dict[str, Any]:
        return self._transition(event_id, "notified", {"notified_at": datetime.now().isoformat(timespec="seconds")})

    def acknowledge(self, event_id: str) -> Dict[str, Any]:
        return self._transition(event_id, "acknowledged", {"acknowledged_at": datetime.now().isoformat(timespec="seconds")})

    def snooze(self, event_id: str, minutes: int = 60) -> Dict[str, Any]:
        minutes = self._bounded_int(minutes, 5, 1440)
        now = datetime.now()
        return self._transition(
            event_id,
            "snoozed",
            {
                "snoozed_at": now.isoformat(timespec="seconds"),
                "snoozed_until": (now + timedelta(minutes=minutes)).isoformat(timespec="seconds"),
            },
        )

    def resolve(self, event_id: str, linked_updates: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        fields = {"resolved_at": datetime.now().isoformat(timespec="seconds")}
        if linked_updates is not None:
            fields["linked_updates"] = linked_updates
        return self._transition(event_id, "resolved", fields)

    def dismiss(self, event_id: str, reason: str = "user_dismissed") -> Dict[str, Any]:
        return self._transition(
            event_id,
            "dismissed",
            {
                "dismissed_at": datetime.now().isoformat(timespec="seconds"),
                "dismiss_reason": str(reason or "user_dismissed").strip() or "user_dismissed",
            },
        )

    def mute(self, event_id: str, hours: int = 24) -> Dict[str, Any]:
        hours = self._bounded_int(hours, 1, 168)
        now = datetime.now()
        return self._transition(
            event_id,
            "muted",
            {
                "muted_at": now.isoformat(timespec="seconds"),
                "muted_until": (now + timedelta(hours=hours)).isoformat(timespec="seconds"),
            },
        )

    def should_notify(
        self,
        event: Dict[str, Any],
        now: Optional[datetime] = None,
        channel: str = "background",
    ) -> bool:
        now = now or datetime.now()
        preferences = self.load_preferences()
        if not preferences.get("enabled", True):
            return False
        if event.get("status") != "detected":
            return False
        if self._is_quiet_until(now, preferences):
            return False
        min_severity = self._channel_min_severity(preferences, channel, event.get("type", ""))
        if self._severity_rank(event) < self._severity_rank({"severity": min_severity}):
            return False
        if preferences.get("quiet_hours_enabled") and self._in_quiet_hours(now, preferences):
            return False
        event_type = event.get("type", "")
        if event_type == "focus_expired" and not preferences.get("notify_focus", True):
            return False
        if event_type in {"commitment_due_today", "commitment_overdue"} and not preferences.get("notify_commitments", True):
            return False
        if event_type == "task_stale" and not preferences.get("notify_tasks", True):
            return False
        return True

    def format_for_context(self, state: Optional[Dict[str, Any]] = None) -> str:
        state = state or self.build_state()
        active = state.get("active") or []
        if not active:
            return "暂无未处理的监督事件。"
        lines = [
            "以下是可追踪的监督事件。请把它们当作低压力提醒，不要反复催促，不要要求证明。",
        ]
        strategy = state.get("strategy") or {}
        tone_policy = strategy.get("tone_policy") or {}
        if tone_policy.get("mode") == "soften":
            lines.append(f"当前提醒语气策略：{tone_policy.get('reply_guidance', '放轻提醒语气。')}")
        copy_policy = strategy.get("copy_policy") or {}
        if copy_policy.get("summary"):
            lines.append(f"当前提醒文案策略：{copy_policy.get('summary')}")
        for index, event in enumerate(active[:5], start=1):
            lines.append(
                f"{index}. [{event.get('severity', 'low')}] {event.get('title', '')}: "
                f"{event.get('display_message') or event.get('message', '')} status={event.get('status', '')}"
            )
        return "\n".join(lines)

    def _focus_expired_candidate(self, focus_state: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        current = (focus_state or {}).get("current") or {}
        if current.get("status") != "expired" or not current.get("id"):
            return {}
        return {
            "type": "focus_expired",
            "subject_type": "focus_session",
            "subject_id": current.get("id", ""),
            "subject_title": current.get("goal", ""),
            "severity": "medium",
            "title": "专注会话已超时",
            "message": (
                f"专注会话【{current.get('goal', '')}】已超过计划 "
                f"{current.get('duration_minutes', 0)} 分钟，适合温和收束进展。"
            ),
            "metadata": {
                "duration_minutes": current.get("duration_minutes", 0),
                "elapsed_minutes": current.get("elapsed_minutes", 0),
                "expected_end_at": current.get("expected_end_at", ""),
            },
        }

    def _screen_deviation_candidate(
        self,
        focus_state: Dict[str, Any],
        task_view: Dict[str, Any],
        now: datetime,
    ) -> Dict[str, Any]:
        prefs = self.load_preferences()
        if not prefs.get("screen_monitor_enabled", True):
            print("[DEBUG] screen_monitor_enabled is False")
            return {}

        # 1. 触发判定判定 (Trigger check): Focus Session Or Work Hours
        current_focus = (focus_state or {}).get("current") or {}
        focus_active = current_focus and current_focus.get("status") == "active"
        
        auto_hours_active = False
        if not focus_active and prefs.get("auto_monitor_work_hours_enabled", True):
            # 检查是否在工作时间段
            start_str = prefs.get("work_hours_start", "09:00")
            end_str = prefs.get("work_hours_end", "18:00")
            current_time_str = now.strftime("%H:%M")
            if start_str <= current_time_str <= end_str:
                auto_hours_active = True
                
        print(f"[DEBUG] focus_active={focus_active}, auto_hours_active={auto_hours_active}, prefs={prefs}")
        if not focus_active and not auto_hours_active:
            return {}

        # 2. 监测目标同步 (Goal Sync): Determine active goal
        goal = ""
        subject_id = ""
        subject_title = ""
        subject_type = ""
        
        if focus_active:
            goal = current_focus.get("goal", "")
            subject_id = current_focus.get("id", "")
            subject_title = current_focus.get("goal", "")
            subject_type = "focus"
        else:
            # 读取当前任务
            current_task = (task_view or {}).get("current") or {}
            if current_task and current_task.get("status") == "active":
                goal = current_task.get("title", "")
                subject_id = current_task.get("id", "")
                subject_title = current_task.get("title", "")
                subject_type = "task"
            else:
                goal = "推进工作与学习"
                subject_id = "auto-work-hours"
                subject_title = "工作时间段自动监视"
                subject_type = "system"

        # 3. 冷却时间判定 (Cooldown/Interval check)
        last_check_str = prefs.get("last_screen_check", "")
        interval_min = self._bounded_int(prefs.get("screen_monitor_interval_minutes", 5), 1, 120)
        
        # 自适应监测频率判定 (Adaptive Interval calculation)
        adaptive_interval_min = float(interval_min)
        recent_obs = self._recent_screen_observations(subject_id=subject_id, limit=1)
        if recent_obs:
            obs_time = self._parse_time(recent_obs[0].get("observed_at", ""))
            if obs_time and (now - obs_time).total_seconds() <= 30 * 60:
                msg_type = str(recent_obs[0].get("message_type", "")).strip().lower()
                if msg_type == "pullback":
                    adaptive_interval_min = interval_min * 0.4
                    print(f"[DEBUG] Adaptive frequency: last observation was pullback. Scaling cooldown interval to {adaptive_interval_min}m (base={interval_min}m)")
                elif msg_type in {"companion", "silent"}:
                    adaptive_interval_min = interval_min * 1.5
                    print(f"[DEBUG] Adaptive frequency: last observation was {msg_type}. Scaling cooldown interval to {adaptive_interval_min}m (base={interval_min}m)")
        
        if last_check_str:
            last_check = self._parse_time(last_check_str)
            print(f"[DEBUG] last_check_str={last_check_str}, last_check={last_check}, now={now}")
            if last_check:
                diff_seconds = (now - last_check).total_seconds()
                if 0 <= diff_seconds < adaptive_interval_min * 60:
                    print(f"[DEBUG] Within adaptive cooldown ({adaptive_interval_min}m), skipping screen monitor check")
                    return {}

        self.update_preferences({"last_screen_check": now.isoformat(timespec="seconds")})

        # 4. 本地规则与多模态模型判断选择
        # 如果配置了 llm_client，我们优先使用 Vision 大模型进行深度屏幕内容分析（可获得高度动态与陪伴式的个性化文案）
        # 如果没有配置大模型，或者大模型调用失败，则退回到本地规则匹配 (Rule-based check)
        
        app_name, window_title = self._get_active_window_macos()
        
        # 如果当前活跃窗口是本 Agent 的前端网页（Workmate Agent）或终端，则直接静默跳过，避免生成提醒干扰用户交互
        if app_name:
            app_lower = app_name.lower()
            title_lower = window_title.lower()
            if "workmate" in app_lower or "workmate" in title_lower :
                print(f"[DEBUG] Active window is Workmate Agent ({app_name} - {window_title}), skipping screen monitor.")
                return {}
                
        rule_result = self._rule_based_check(app_name, window_title, goal) if app_name else None

        # 尝试调用多模态 Vision 模型
        vision_success = False
        analysis = {}
        
        if self.llm_client:
            import os
            import base64
            import subprocess
            
            screenshots_dir = self.events_path.parent / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshots_dir / f"screen-{now.strftime('%Y%m%d-%H%M%S')}.jpg"
            
            try:
                cmd = ["/usr/sbin/screencapture", "-x", "-t", "jpeg", str(screenshot_path)]
                if os.path.exists("/usr/sbin/screencapture"):
                    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if res.returncode == 0:
                        image_base64 = ""
                        if screenshot_path.exists():
                            with open(screenshot_path, "rb") as img_file:
                                img_data = img_file.read()
                                image_base64 = base64.b64encode(img_data).decode("utf-8")
                        
                        if image_base64:
                            current_task = (task_view or {}).get("current") or {}
                            task_title = current_task.get("title", "") or "个人自律"
                            
                            recent_observations = self._recent_screen_observations(subject_id=subject_id, limit=6)
                            recent_context = self._format_screen_observation_context(recent_observations)
                            # 增强 Prompt，将本地窗口信息和最近观察轨迹作为上下文提供给大模型参考
                            local_rule_context = ""
                            if app_name:
                                local_rule_context = f"\n（本地检测到前台 App 为：{app_name}，窗口标题为：{window_title}）"
                                
                            prompt = (
                                "# 角色\n"
                                "你是一个坐在用户旁边的“工位搭子”（同桌），温柔、有趣、懂技术，不是冷冰冰的安全审计员。你现在看到了用户当前的屏幕截图。\n\n"
                                "# 目标与主线\n"
                                "- 专注目标：'{goal}'\n"
                                "- 主线任务：'{task_title}'\n"
                                "{local_context}\n\n"
                                "# 最近屏幕观察历史 (用来判断连续趋势，避免把当前截图当成孤立瞬间)\n"
                                "{recent_context}\n\n"
                                "# 任务说明\n"
                                "你使用的是强视觉模型，请发挥你的多模态分析能力，看懂用户屏幕截图：\n"
                                "1. 分析用户在做什么，以及这和当前目标与主线的关系。不要只按 App 名机械判断；如果页面内容本身与目标相关（如查报错、看文档），要把这种关系识别出来。\n"
                                "2. 根据截图与历史，判断是短暂切换/查资料，还是已经进入偏航拖延状态。\n"
                                "3. 决定是否对用户说话。如果不该打扰，让 should_message 为 false，message 留空；如果值得陪伴、提醒或轻轻拉回，直接在 message 中写下最自然的陪伴文案。文案不限制长度，不要写成固定模板，请贴合具体情境，可以温柔、明确、简短或稍微展开。\n\n"
                                "# 输出格式\n"
                                "请务必以 JSON 格式输出，对象必须恰好包含以下字段：\n"
                                "{\n"
                                "  \"observation\": \"屏幕活动描述，用自然语言简要描述你看到屏幕上正在发生什么\",\n"
                                "  \"goal_note\": \"活动与当前主线的关系，用自然语言说明\",\n"
                                "  \"message_type\": \"companion|pullback|silent\",\n"
                                "  \"should_message\": true 或 false,\n"
                                "  \"message\": \"你对用户说的话，直接写在这里；如果不该打扰，留空\"\n"
                                "}"
                            ).replace("{goal}", goal).replace("{task_title}", task_title).replace("{local_context}", local_rule_context).replace("{recent_context}", recent_context)
                            
                            raw_response = self.llm_client.invoke_vision(prompt, image_base64, json_mode=True)
                            analysis = self._parse_json_response(raw_response)
                            if "observation" in analysis:
                                vision_success = True
                                
                if screenshot_path.exists():
                    screenshot_path.unlink()
            except Exception as e:
                print(f"[DEBUG] Vision check failed, falling back to rule check. Error: {e}")

        # 根据检测结果生成事件
        if vision_success:
            message_type = self._screen_message_type(analysis)
            should_message = bool(analysis.get("should_message", False))
            activity_summary = str(analysis.get("observation", "") or "")
            observation = self._record_screen_observation(
                analysis=analysis,
                now=now,
                subject_id=subject_id,
                subject_title=subject_title,
                subject_type=subject_type,
                goal=goal,
                app_name=app_name,
                window_title=window_title,
            )
            policy = self._screen_observation_policy(observation)
            if policy.get("action") == "record_only":
                print(f"[DEBUG] Screen observation recorded without reminder: {policy}")
                return {}
            
            if message_type == "pullback":
                display_message = self._vision_direct_reminder(
                    analysis=analysis,
                    event_type="screen_deviation",
                    goal=goal,
                    subject_title=subject_title,
                    app_name=app_name,
                    window_title=window_title,
                )
                return {
                    "type": "screen_deviation",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "subject_title": subject_title,
                    "severity": policy.get("severity", "high"),
                    "title": "工位偏航提醒 🔔",
                    "message": f"视觉观察：{activity_summary}。{analysis.get('goal_note', '')}",
                    "display_message": display_message,
                    "metadata": {
                        "activity_summary": activity_summary,
                        "goal_note": analysis.get("goal_note", ""),
                        "message_type": message_type,
                        "should_message": should_message,
                        "vision_direct_message": self._clean_screen_reminder(analysis.get("message", "")),
                        "focus_goal": goal,
                        "triggered_by": "vision_llm",
                        "reminder_generated_by": "vision_direct" if analysis.get("message") else "fallback",
                        "screen_policy": policy,
                        "observation_id": observation.get("id", ""),
                    },
                }
            else:
                display_message = self._vision_direct_reminder(
                    analysis=analysis,
                    event_type="screen_accompaniment",
                    goal=goal,
                    subject_title=subject_title,
                    app_name=app_name,
                    window_title=window_title,
                )
                return {
                    "type": "screen_accompaniment",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "subject_title": subject_title,
                    "severity": "low",
                    "title": "工位陪伴提醒 🌟",
                    "message": f"视觉观察：{activity_summary}。{analysis.get('goal_note', '')}",
                    "display_message": display_message,
                    "metadata": {
                        "activity_summary": activity_summary,
                        "goal_note": analysis.get("goal_note", ""),
                        "message_type": message_type,
                        "should_message": should_message,
                        "vision_direct_message": self._clean_screen_reminder(analysis.get("message", "")),
                        "focus_goal": goal,
                        "triggered_by": "vision_llm",
                        "reminder_generated_by": "vision_direct" if analysis.get("message") else "fallback",
                        "screen_policy": policy,
                        "observation_id": observation.get("id", ""),
                    },
                }
        else:
            # 大模型未配置或调用失败，退回到本地规则结果
            if rule_result is False:
                activity_summary = f"处于工作应用：{app_name}，窗口标题：{window_title}"
                display_msg = f"这段还在【{goal}】上，先把当前这个点收完。"
                app_lower = app_name.lower()
                if "code" in app_lower or "cursor" in app_lower or "pycharm" in app_lower:
                    display_msg = f"代码这条线还在推进，先把眼前这个小问题收住。"
                elif "terminal" in app_lower or "iterm" in app_lower:
                    display_msg = f"终端这边看起来是在处理任务相关的事，先把这一步跑完。"
                elif "github" in window_title.lower() or "stackoverflow" in window_title.lower():
                    display_msg = f"资料这段可以，先抓住一个有用点带回当前任务。"
                    
                return {
                    "type": "screen_accompaniment",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "subject_title": subject_title,
                    "severity": "low",
                    "title": "工位陪伴提醒 🌟",
                    "message": f"监测到屏幕活动正常：{activity_summary}",
                    "display_message": display_msg,
                    "metadata": {
                        "activity_summary": activity_summary,
                        "focus_goal": goal,
                        "triggered_by": "local_rules",
                    },
                }
            elif rule_result is True:
                activity_summary = f"处于活跃应用：{app_name}，窗口标题：{window_title}"
                deviation_reason = "本地黑名单规则匹配成功，确定处于娱乐偏航状态"
                display_msg = f"先回来一下，当前主线是【{goal}】；把这个窗口放一边，接上任务里最小的一步。"
                return {
                    "type": "screen_deviation",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "subject_title": subject_title,
                    "severity": "high",
                    "title": "工位偏航提醒 🔔",
                    "message": f"监测到屏幕活动偏离目标：{activity_summary}。原因：{deviation_reason}",
                    "display_message": display_msg,
                    "metadata": {
                        "activity_summary": activity_summary,
                        "deviation_reason": deviation_reason,
                        "focus_goal": goal,
                        "triggered_by": "local_rules",
                    },
                }

    def _record_screen_observation(
        self,
        analysis: Dict[str, Any],
        now: datetime,
        subject_id: str,
        subject_title: str,
        subject_type: str,
        goal: str,
        app_name: str,
        window_title: str,
    ) -> Dict[str, Any]:
        now_text = now.isoformat(timespec="seconds")
        observation = {
            "id": self._make_id(now_text, f"screen-observation:{subject_id}:{app_name}:{window_title}"),
            "observed_at": now_text,
            "subject_id": subject_id,
            "subject_title": subject_title,
            "subject_type": subject_type,
            "focus_goal": goal,
            "app_name": app_name or "",
            "window_title": window_title or "",
            "observation": str(analysis.get("observation", "") or ""),
            "activity_summary": str(analysis.get("observation", "") or ""),
            "goal_note": str(analysis.get("goal_note", "") or ""),
            "message_type": self._screen_message_type(analysis),
            "should_message": bool(analysis.get("should_message", False)),
            "message": self._clean_screen_reminder(analysis.get("message", "")),
        }
        observations = self.load_screen_observations()
        observations.append(observation)
        self.save_screen_observations(observations)
        return observation

    def _recent_screen_observations(self, subject_id: str = "", limit: int = 6) -> List[Dict[str, Any]]:
        observations = self.load_screen_observations()
        if subject_id:
            scoped = [item for item in observations if item.get("subject_id") == subject_id]
            if scoped:
                observations = scoped
        return sorted(observations, key=lambda item: item.get("observed_at", ""), reverse=True)[:limit]

    def _format_screen_observation_context(self, observations: List[Dict[str, Any]]) -> str:
        if not observations:
            return "暂无历史观察。"
        lines = []
        for item in sorted(observations, key=lambda value: value.get("observed_at", "")):
            lines.append(
                f"- {item.get('observed_at', '')}: "
                f"type={item.get('message_type', '')}; "
                f"observation={item.get('observation') or item.get('activity_summary', '')}; "
                f"goal_note={item.get('goal_note', '')}"
            )
        return "\n".join(lines)

    def _screen_observation_policy(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        prefs = self.load_preferences()
        message_type = str(observation.get("message_type", "") or "silent").lower()
        should_message = bool(observation.get("should_message", False))
        has_message = bool(str(observation.get("message", "") or "").strip())
        subject_id = observation.get("subject_id", "")
        recent = self._recent_screen_observations(subject_id=subject_id, limit=4)
        consecutive_pullback = 0
        for item in recent:
            if str(item.get("message_type", "") or "").lower() == "pullback":
                consecutive_pullback += 1
            else:
                break

        if prefs.get("screen_force_message", False) and has_message:
            return {
                "action": "emit_event",
                "reason": "force_message_enabled",
                "severity": "high" if message_type == "pullback" else "low",
                "consecutive_pullback": consecutive_pullback,
            }

        if should_message and has_message:
            return {
                "action": "emit_event",
                "reason": "vision_companion_message",
                "severity": "high" if message_type == "pullback" else "low",
                "consecutive_pullback": consecutive_pullback,
            }

        return {
            "action": "record_only",
            "reason": "vision_chose_silence",
            "severity": "low",
            "consecutive_pullback": consecutive_pullback,
        }

    def _screen_message_type(self, analysis: Dict[str, Any]) -> str:
        value = str(analysis.get("message_type", "") or "silent").strip().lower()
        if value not in {"companion", "pullback", "silent"}:
            return "silent"
        return value

    def _vision_direct_reminder(
        self,
        analysis: Dict[str, Any],
        event_type: str,
        goal: str,
        subject_title: str,
        app_name: str,
        window_title: str,
    ) -> str:
        direct_message = self._clean_screen_reminder(analysis.get("message", ""))
        if direct_message:
            return direct_message
        return self._screen_fallback_message({
            "type": event_type,
            "subject_title": subject_title,
            "metadata": {
                "focus_goal": goal,
                "app_name": app_name,
                "window_title": window_title,
            },
        })

    def _clean_screen_reminder(self, text: Any) -> str:
        if not isinstance(text, str):
            return ""
        text = text.strip()
        if text.startswith("```") and text.endswith("```"):
            text = text.strip("`").strip()
        for prefix in ["提醒：", "提醒:", "工位搭子：", "工位搭子:", "Workmate：", "Workmate:"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        return self._compact_sentence(text, limit=320)

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        import re
        text = text.strip()
        # Strip markdown block if exists
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if number < 0:
            return 0.0
        if number > 1:
            return 1.0
        return number

    def _get_active_window_macos(self) -> tuple[str, str]:
        """通过 AppleScript 获取当前最前台 App 的名称与活跃窗口标题。仅支持 macOS。"""
        import os
        import subprocess
        
        # 兼容性检查：如果不是 macOS 或者 AppleScript 不存在，则直接返回空
        if not os.path.exists("/usr/sbin/screencapture"):
            return "", ""
            
        script = (
            'tell application "System Events"\n'
            '    set frontmostProcess to first application process whose frontmost is true\n'
            '    set appName to name of frontmostProcess\n'
            '    set windowTitle to ""\n'
            '    tell frontmostProcess\n'
            '        try\n'
            '            if exists window 1 then\n'
            '                set windowTitle to name of window 1\n'
            '            end if\n'
            '        end try\n'
            '    end tell\n'
            'end tell\n'
            'return appName & "|" & windowTitle'
        )
        
        try:
            cmd = ["osascript", "-e", script]
            # 执行命令并设置 2 秒超时，防止卡死
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2.0)
            if res.returncode != 0:
                return "", ""
            output = res.stdout.strip()
            if "|" in output:
                parts = output.split("|", 1)
                return parts[0].strip(), parts[1].strip()
            return output, ""
        except Exception:
            return "", ""

    def _rule_based_check(self, app_name: str, window_title: str, goal: str) -> Optional[bool]:
        """本地规则过滤器。
        返回 False 表示确认正在工作（无偏航），返回 True 表示确认娱乐偏航，返回 None 表示进入灰色地带。
        """
        if not app_name:
            return None
            
        app_lower = app_name.lower()
        title_lower = window_title.lower()
        
        # 0. 自定义黑白名单过滤 (最高优先级)
        prefs = self.load_preferences()
        custom_blacklist = prefs.get("custom_blacklist_keywords", [])
        custom_whitelist = prefs.get("custom_whitelist_keywords", [])
        
        if any(kw.lower() in title_lower or kw.lower() in app_lower for kw in custom_blacklist if kw):
            return True
            
        if any(kw.lower() in title_lower or kw.lower() in app_lower for kw in custom_whitelist if kw):
            return False
        
        # 1. 软件黑名单直接判定偏航
        blacklist_apps = {"steam", "epic games launcher", "league of legends", "genshin impact"}
        if app_lower in blacklist_apps:
            return True
            
        # 2. 网页黑名单直接判定偏航
        blacklist_keywords = {
            "bilibili", "youtube", "weibo", "taobao", "zhihu", 
            "reddit", "netflix", "douyin", "xiaohongshu", "kuaishou", 
            "tieba", "jd.com", "tmall", "steam"
        }
        if any(kw in title_lower or kw in app_lower for kw in blacklist_keywords):
            return True
            
        # 3. 软件白名单直接判定无偏航 (IDE, Terminal)
        whitelist_apps = {
            "xcode", "visual studio code", "cursor", "terminal", 
            "iterm", "iterm2", "pycharm", "intellij idea", "clion", 
            "webstorm", "sublime text", "android studio", "docker"
        }
        if app_lower in whitelist_apps:
            return False
            
        # 4. 网页白名单/工作关键词直接判定无偏航
        whitelist_keywords = {
            "github", "stackoverflow", "leetcode", "localhost", 
            "documentation", "google search", "api reference", 
            "developer", "mdn", "chatgpt", "deepseek", "kimi",
            "antigravity", "workmate"
        }
        if any(kw in title_lower for kw in whitelist_keywords):
            return False
            
        # 5. 进入灰色地带，需要截图 Vision LLM 判定
        return None


    def _commitment_deadline_candidates(self, commitments: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
        candidates = []
        for item in commitments:
            if item.get("status") != "open" or not item.get("id") or not item.get("deadline"):
                continue
            deadline = self._parse_time(item.get("deadline", ""))
            if not deadline:
                continue
            if deadline < now:
                event_type = "commitment_overdue"
                severity = "medium"
                title = "承诺已逾期"
                message = f"承诺【{item.get('commitment', '')}】已超过截止时间，适合提醒用户关闭、延期或放下。"
            elif deadline.date() == now.date():
                event_type = "commitment_due_today"
                severity = "low"
                title = "承诺今日到期"
                message = f"承诺【{item.get('commitment', '')}】今天到期，适合在相关时轻轻提醒。"
            else:
                continue
            candidates.append({
                "type": event_type,
                "subject_type": "commitment",
                "subject_id": item.get("id", ""),
                "subject_title": item.get("commitment", ""),
                "severity": severity,
                "title": title,
                "message": message,
                "metadata": {
                    "deadline": item.get("deadline", ""),
                    "task": item.get("task", ""),
                },
            })
        return candidates

    def _stale_task_candidate(self, task_view: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        current = (task_view or {}).get("current") or {}
        if not current.get("id") or current.get("status") in {"done", "abandoned"}:
            return {}
        updated_at = self._parse_time(current.get("updated_at", ""))
        if not updated_at:
            return {}
        hours = (now - updated_at).total_seconds() / 3600
        if hours < 24:
            return {}
        return {
            "type": "task_stale",
            "subject_type": "task",
            "subject_id": current.get("id", ""),
            "subject_title": current.get("title", ""),
            "severity": "low",
            "title": "当前任务久未更新",
            "message": f"当前任务【{current.get('title', '')}】约 {int(hours)} 小时未更新，适合温和提醒它还被记着。",
            "metadata": {
                "updated_at": current.get("updated_at", ""),
                "stale_hours": int(hours),
                "status": current.get("status", ""),
            },
        }

    def _upsert_candidate(
        self,
        events: List[Dict[str, Any]],
        candidate: Dict[str, Any],
        now: datetime,
    ) -> List[Dict[str, Any]]:
        now_text = now.isoformat(timespec="seconds")
        dedupe_key = self._dedupe_key(candidate)
        existing = next(
            (
                event for event in events
                if event.get("dedupe_key") == dedupe_key
                and event.get("status") in (self.ACTIVE_STATUSES | self.PAUSED_STATUSES)
            ),
            None,
        )
        if existing:
            existing.update({
                "severity": candidate.get("severity", existing.get("severity", "low")),
                "title": candidate.get("title", existing.get("title", "")),
                "message": candidate.get("message", existing.get("message", "")),
                "display_message": candidate.get("display_message", existing.get("display_message", "")),
                "metadata": {**existing.get("metadata", {}), **candidate.get("metadata", {})},
                "last_detected_at": now_text,
                "updated_at": now_text,
            })
            return events

        events.append({
            "id": self._make_id(now_text, dedupe_key),
            "dedupe_key": dedupe_key,
            "type": candidate.get("type", "general"),
            "subject_type": candidate.get("subject_type", ""),
            "subject_id": candidate.get("subject_id", ""),
            "subject_title": candidate.get("subject_title", ""),
            "severity": candidate.get("severity", "low"),
            "title": candidate.get("title", ""),
            "message": candidate.get("message", ""),
            "display_message": candidate.get("display_message", ""),
            "status": "detected",
            "source": "scheduler",
            "metadata": candidate.get("metadata", {}),
            "detected_at": now_text,
            "last_detected_at": now_text,
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
            "feedback_history": [],
            "transition_history": [
                self._transition_record(
                    from_status="",
                    to_status="detected",
                    at=now_text,
                    reason="candidate_detected",
                    fields={},
                )
            ],
            "created_at": now_text,
            "updated_at": now_text,
        })
        return events

    def _auto_resolve_missing_events(
        self,
        events: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        now: datetime,
    ) -> None:
        active_keys = {self._dedupe_key(candidate) for candidate in candidates}
        now_text = now.isoformat(timespec="seconds")
        for event in events:
            if event.get("status") not in (self.ACTIVE_STATUSES | self.PAUSED_STATUSES):
                continue
            if event.get("dedupe_key") not in active_keys and event.get("type") in {
                "focus_expired",
                "commitment_due_today",
                "commitment_overdue",
                "task_stale",
                "screen_deviation",
                "screen_accompaniment",
            }:
                previous_status = str(event.get("status", "detected") or "detected")
                event["status"] = "resolved"
                event["resolved_at"] = now_text
                event["updated_at"] = now_text
                self._append_transition(
                    event,
                    from_status=previous_status,
                    to_status="resolved",
                    now_text=now_text,
                    reason="candidate_disappeared",
                    fields={"resolved_at": now_text},
                )

    def _transition(self, event_id: str, status: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"invalid supervision event status: {status}")
        events = self.load_events()
        now_text = datetime.now().isoformat(timespec="seconds")
        for event in events:
            if event.get("id") == event_id:
                previous_status = str(event.get("status", "detected") or "detected")
                event["status"] = status
                event["updated_at"] = now_text
                event.update(fields)
                self._append_transition(
                    event,
                    from_status=previous_status,
                    to_status=status,
                    now_text=now_text,
                    reason=self._transition_reason(previous_status, status, fields),
                    fields=fields,
                )
                self._append_feedback(event, status, now_text, fields)
                self.save_events(events)
                return event
        raise ValueError(f"supervision event not found: {event_id}")

    def _normalize_event(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        status = str(item.get("status", "detected")).strip().lower()
        if status not in self.VALID_STATUSES:
            status = "detected"
        return {
            "id": item.get("id", ""),
            "dedupe_key": item.get("dedupe_key", ""),
            "type": item.get("type", "general"),
            "subject_type": item.get("subject_type", ""),
            "subject_id": item.get("subject_id", ""),
            "subject_title": item.get("subject_title", ""),
            "severity": item.get("severity", "low"),
            "title": item.get("title", ""),
            "message": item.get("message", ""),
            "display_message": item.get("display_message", ""),
            "status": status,
            "source": item.get("source", ""),
            "metadata": item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {},
            "linked_updates": item.get("linked_updates", [])
            if isinstance(item.get("linked_updates", []), list) else [],
            "detected_at": item.get("detected_at", ""),
            "last_detected_at": item.get("last_detected_at", ""),
            "notified_at": item.get("notified_at", ""),
            "acknowledged_at": item.get("acknowledged_at", ""),
            "snoozed_at": item.get("snoozed_at", ""),
            "snoozed_until": item.get("snoozed_until", ""),
            "resolved_at": item.get("resolved_at", ""),
            "dismissed_at": item.get("dismissed_at", ""),
            "dismiss_reason": item.get("dismiss_reason", ""),
            "muted_at": item.get("muted_at", ""),
            "muted_until": item.get("muted_until", ""),
            "feedback_history": item.get("feedback_history", [])
            if isinstance(item.get("feedback_history", []), list) else [],
            "transition_history": item.get("transition_history", [])
            if isinstance(item.get("transition_history", []), list) else [],
            "last_transition_reason": item.get("last_transition_reason", ""),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
        }

    def _append_feedback(self, event: Dict[str, Any], action: str, now_text: str, fields: Dict[str, Any]) -> None:
        history = event.get("feedback_history", [])
        if not isinstance(history, list):
            history = []
        history.append({
            "action": action,
            "at": now_text,
            "details": {
                key: value
                for key, value in fields.items()
                if key.endswith("_until") or key.endswith("_at")
            },
        })
        event["feedback_history"] = history[-20:]

    def _append_transition(
        self,
        event: Dict[str, Any],
        from_status: str,
        to_status: str,
        now_text: str,
        reason: str,
        fields: Dict[str, Any],
    ) -> None:
        history = event.get("transition_history", [])
        if not isinstance(history, list):
            history = []
        history.append(self._transition_record(from_status, to_status, now_text, reason, fields))
        event["transition_history"] = history[-30:]
        event["last_transition_reason"] = reason

    def _transition_record(
        self,
        from_status: str,
        to_status: str,
        at: str,
        reason: str,
        fields: Dict[str, Any],
    ) -> Dict[str, Any]:
        details = {
            key: value
            for key, value in (fields or {}).items()
            if key.endswith("_until") or key.endswith("_at") or key in {"dismiss_reason"}
        }
        return {
            "from": from_status,
            "to": to_status,
            "at": at,
            "reason": reason,
            "details": details,
        }

    def _transition_reason(self, previous_status: str, status: str, fields: Dict[str, Any]) -> str:
        if status == "notified":
            return "notification_sent"
        if status == "acknowledged":
            return "user_acknowledged"
        if status == "snoozed":
            return "user_snoozed"
        if status == "muted":
            return "user_muted"
        if status == "resolved":
            return "user_resolved" if previous_status != "detected" else "user_marked_done"
        if status == "dismissed":
            return str(fields.get("dismiss_reason") or "user_dismissed")
        return "status_updated"

    def _state_machine_summary(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        status_counts: Dict[str, int] = {status: 0 for status in sorted(self.VALID_STATUSES)}
        recent_transitions = []
        transition_sequence = 0
        for event in events:
            status = str(event.get("status", "detected") or "detected")
            if status in status_counts:
                status_counts[status] += 1
            history = event.get("transition_history", []) or []
            if isinstance(history, list):
                for item in history[-3:]:
                    if not isinstance(item, dict):
                        continue
                    transition_sequence += 1
                    recent_transitions.append({
                        "event_id": event.get("id", ""),
                        "type": event.get("type", ""),
                        "subject_title": event.get("subject_title", ""),
                        "from": item.get("from", ""),
                        "to": item.get("to", ""),
                        "at": item.get("at", ""),
                        "reason": item.get("reason", ""),
                        "_sequence": transition_sequence,
                    })
        recent_transitions = sorted(
            recent_transitions,
            key=lambda item: (item.get("at", ""), item.get("_sequence", 0)),
            reverse=True,
        )[:10]
        for item in recent_transitions:
            item.pop("_sequence", None)
        return {
            "states": status_counts,
            "active_statuses": sorted(self.ACTIVE_STATUSES),
            "paused_statuses": sorted(self.PAUSED_STATUSES),
            "final_statuses": sorted(self.FINAL_STATUSES),
            "labels": self.STATE_LABELS,
            "recent_transitions": recent_transitions,
        }

    def _feedback_stats(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_action: Dict[str, int] = {}
        by_type: Dict[str, Dict[str, int]] = {}
        last_feedback = ""
        total = 0
        for event in events:
            event_type = event.get("type", "general")
            for item in event.get("feedback_history", []) or []:
                if not isinstance(item, dict):
                    continue
                action = str(item.get("action", "")).strip() or "unknown"
                by_action[action] = by_action.get(action, 0) + 1
                by_type.setdefault(event_type, {})
                by_type[event_type][action] = by_type[event_type].get(action, 0) + 1
                total += 1
                if str(item.get("at", "")) > last_feedback:
                    last_feedback = str(item.get("at", ""))
        return {
            "total": total,
            "by_action": by_action,
            "by_type": by_type,
            "last_feedback_at": last_feedback,
        }

    def _build_strategy(
        self,
        preferences: Dict[str, Any],
        feedback_stats: Dict[str, Any],
        support_state: Optional[Dict[str, Any]] = None,
        copy_policy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        by_action = feedback_stats.get("by_action", {}) if isinstance(feedback_stats, dict) else {}
        by_type = feedback_stats.get("by_type", {}) if isinstance(feedback_stats, dict) else {}
        quiet_until = self._parse_time(preferences.get("quiet_until", ""))
        tone_policy = self._tone_policy(preferences, support_state=support_state)
        delayed = int(by_action.get("snoozed", 0) or 0) + int(by_action.get("muted", 0) or 0)
        accepted = int(by_action.get("acknowledged", 0) or 0) + int(by_action.get("resolved", 0) or 0)
        recommendations = []
        explanations = []
        updates: Dict[str, Any] = {}

        if delayed >= 3 and delayed > accepted:
            if preferences.get("browser_min_severity") != "high":
                recommendations.append({
                    "field": "browser_min_severity",
                    "current": preferences.get("browser_min_severity", preferences.get("push_min_severity", "medium")),
                    "recommended": "high",
                    "reason": "用户对提醒更多选择稍后或静音，浏览器通知适合只推送高优先级事件。",
                    "impact": "低/中等级事件仍保留在页面内，但不弹出浏览器通知。",
                })
                explanations.append(self._strategy_explanation(
                    decision="raise_browser_threshold",
                    reason="用户对提醒更多选择稍后或静音。",
                    evidence={
                        "snoozed_or_muted": delayed,
                        "acknowledged_or_resolved": accepted,
                        "last_feedback_at": feedback_stats.get("last_feedback_at", ""),
                    },
                    affected_fields=["browser_min_severity", "push_min_severity"],
                    recommendation="浏览器通知只推送高优先级事件。",
                    confidence="medium",
                ))
                updates["browser_min_severity"] = "high"
                updates["push_min_severity"] = "high"
            if preferences.get("background_min_severity") != "high":
                recommendations.append({
                    "field": "background_min_severity",
                    "current": preferences.get("background_min_severity", "high"),
                    "recommended": "high",
                    "reason": "后台推送比页面提醒更打扰，适合保持最高门槛。",
                    "impact": "macOS/Bark/飞书等后台通知只处理高优先级事件。",
                })
                explanations.append(self._strategy_explanation(
                    decision="keep_background_strict",
                    reason="后台推送打扰度高，且近期反馈没有支持提高后台主动性。",
                    evidence={
                        "snoozed_or_muted": delayed,
                        "acknowledged_or_resolved": accepted,
                    },
                    affected_fields=["background_min_severity"],
                    recommendation="后台通知保持高门槛。",
                    confidence="high",
                ))
                updates["background_min_severity"] = "high"
            if int(preferences.get("default_snooze_minutes", 60) or 60) < 120:
                recommendations.append({
                    "field": "default_snooze_minutes",
                    "current": preferences.get("default_snooze_minutes", 60),
                    "recommended": 120,
                    "reason": "稍后提醒次数偏多，默认稍后间隔可以放长一点。",
                    "impact": "减少短时间内重复回来的提醒。",
                })
                explanations.append(self._strategy_explanation(
                    decision="extend_snooze_interval",
                    reason="用户多次选择稍后或静音，短周期重复提醒可能偏打扰。",
                    evidence={
                        "snoozed_or_muted": delayed,
                        "current_default_snooze_minutes": preferences.get("default_snooze_minutes", 60),
                    },
                    affected_fields=["default_snooze_minutes"],
                    recommendation="默认稍后间隔延长到 120 分钟。",
                    confidence="medium",
                ))
                updates["default_snooze_minutes"] = 120
            mode = "reduce_push"
            summary = "提醒反馈显示用户可能需要更安静一点。"
        elif accepted >= 3 and accepted >= delayed * 2 and preferences.get("browser_min_severity") == "high":
            recommendations.append({
                "field": "browser_min_severity",
                "current": preferences.get("browser_min_severity", "high"),
                "recommended": "medium",
                "reason": "用户近期更常确认或关闭提醒，可以允许中等级事件主动推送。",
                "impact": "浏览器通知会稍微积极一点，但后台推送仍保持更高门槛。",
            })
            explanations.append(self._strategy_explanation(
                decision="lower_browser_threshold",
                reason="用户近期更常确认或完成提醒，说明浏览器层中等级提醒可能是有帮助的。",
                evidence={
                    "acknowledged_or_resolved": accepted,
                    "snoozed_or_muted": delayed,
                    "current_browser_min_severity": preferences.get("browser_min_severity", "high"),
                },
                affected_fields=["browser_min_severity", "push_min_severity"],
                recommendation="允许中等级事件触发浏览器通知。",
                confidence="medium",
            ))
            updates["browser_min_severity"] = "medium"
            updates["push_min_severity"] = "medium"
            mode = "allow_more_push"
            summary = "用户近期能较好处理提醒，可以略微提高主动性。"
        else:
            explanations.append(self._strategy_explanation(
                decision="keep_current_strategy",
                reason="反馈数量或倾向还不足以支持调整提醒策略。",
                evidence={
                    "snoozed_or_muted": delayed,
                    "acknowledged_or_resolved": accepted,
                    "total_feedback": feedback_stats.get("total", 0),
                },
                affected_fields=[],
                recommendation="保持当前策略，继续观察。",
                confidence="high" if feedback_stats.get("total", 0) else "low",
                auto_applicable=False,
            ))
            mode = "steady"
            summary = "当前提醒策略保持稳定即可。"

        type_friction = []
        type_preference_updates: Dict[str, Dict[str, str]] = {}
        type_preference_signals = []
        for event_type, actions in by_type.items():
            if not isinstance(actions, dict):
                continue
            type_delayed = int(actions.get("snoozed", 0) or 0) + int(actions.get("muted", 0) or 0)
            type_accepted = int(actions.get("acknowledged", 0) or 0) + int(actions.get("resolved", 0) or 0)
            if type_delayed >= 2 and type_delayed > type_accepted:
                suggested_channels = {"browser": "high", "background": "high"}
                type_friction.append({
                    "type": event_type,
                    "delayed": type_delayed,
                    "accepted": type_accepted,
                    "suggestion": self._type_friction_suggestion(event_type),
                    "recommended_channels": suggested_channels,
                })
                type_preference_updates[event_type] = suggested_channels
                type_preference_signals.append({
                    "type": event_type,
                    "mode": "reduce_push_for_type",
                    "summary": "这一类提醒更常被稍后或静音，适合只保留页面提醒或提高弹窗门槛。",
                    "evidence": {
                        "snoozed_or_muted": type_delayed,
                        "acknowledged_or_resolved": type_accepted,
                    },
                })
                explanations.append(self._strategy_explanation(
                    decision="raise_type_threshold",
                    reason=f"{event_type} 类型提醒更常被稍后或静音。",
                    evidence={
                        "event_type": event_type,
                        "snoozed_or_muted": type_delayed,
                        "acknowledged_or_resolved": type_accepted,
                    },
                    affected_fields=[f"event_type_min_severity.{event_type}.browser", f"event_type_min_severity.{event_type}.background"],
                    recommendation="提高这一类事件的弹窗和后台推送门槛。",
                    confidence="medium",
                ))
            elif type_accepted >= 3 and type_accepted >= type_delayed * 2:
                suggested_channels = {"browser": "medium"}
                type_preference_updates[event_type] = suggested_channels
                type_preference_signals.append({
                    "type": event_type,
                    "mode": "allow_browser_for_type",
                    "summary": "这一类提醒更常被确认或关闭，可以允许中等级浏览器提醒。",
                    "evidence": {
                        "acknowledged_or_resolved": type_accepted,
                        "snoozed_or_muted": type_delayed,
                    },
                })
                explanations.append(self._strategy_explanation(
                    decision="lower_type_browser_threshold",
                    reason=f"{event_type} 类型提醒更常被确认或完成。",
                    evidence={
                        "event_type": event_type,
                        "acknowledged_or_resolved": type_accepted,
                        "snoozed_or_muted": type_delayed,
                    },
                    affected_fields=[f"event_type_min_severity.{event_type}.browser"],
                    recommendation="允许这一类事件触发中等级浏览器提醒。",
                    confidence="medium",
                ))

        if type_preference_updates:
            updates["event_type_min_severity"] = self._merge_event_type_updates(
                updates.get("event_type_min_severity", {}),
                type_preference_updates,
            )

        manual_control = {}
        if quiet_until and quiet_until > datetime.now():
            manual_control = {
                "active": True,
                "quiet_until": quiet_until.isoformat(timespec="seconds"),
                "summary": f"提醒已安静到 {quiet_until.strftime('%m-%d %H:%M')}。",
            }

        return {
            "mode": mode,
            "summary": summary,
            "recommendations": recommendations,
            "explanations": explanations[:8],
            "preference_updates": updates,
            "type_friction": type_friction[:5],
            "type_preference_signals": type_preference_signals[:5],
            "manual_control": manual_control,
            "tone_policy": tone_policy,
            "copy_policy": copy_policy or self._copy_policy({}),
        }

    def _copy_policy(self, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        preferences = user_profile.get("communication_preference") or []
        interventions = user_profile.get("effective_interventions") or []
        if isinstance(preferences, str):
            preferences = [preferences]
        if isinstance(interventions, str):
            interventions = [interventions]
        profile_text = "；".join(str(item) for item in [*preferences, *interventions])
        low_pressure = any(keyword in profile_text for keyword in ["低压力", "无压力", "不要催促", "不施压", "别催"])
        concise = any(keyword in profile_text for keyword in ["只给一个小建议", "简短", "一句", "低认知负荷"])
        organize_first = any(keyword in profile_text for keyword in ["记住", "整理", "先帮用户"])
        no_proof = any(keyword in profile_text for keyword in ["不要每次都强制要求证明", "不要要求证明", "不要求证明", "证据"])
        return {
            "source": "user_profile",
            "low_pressure": low_pressure,
            "concise": concise,
            "organize_first": organize_first,
            "no_proof": no_proof,
            "summary": self._copy_policy_summary(low_pressure, concise, organize_first, no_proof),
        }

    def _strategy_explanation(
        self,
        decision: str,
        reason: str,
        evidence: Dict[str, Any],
        affected_fields: List[str],
        recommendation: str,
        confidence: str = "medium",
        auto_applicable: bool = True,
    ) -> Dict[str, Any]:
        return {
            "decision": decision,
            "reason": reason,
            "evidence": evidence if isinstance(evidence, dict) else {},
            "affected_fields": affected_fields if isinstance(affected_fields, list) else [],
            "recommendation": recommendation,
            "confidence": confidence if confidence in {"low", "medium", "high"} else "medium",
            "auto_applicable": bool(auto_applicable),
        }

    def _copy_policy_summary(
        self,
        low_pressure: bool,
        concise: bool,
        organize_first: bool,
        no_proof: bool,
    ) -> str:
        parts = []
        if organize_first:
            parts.append("先确认已记住")
        if low_pressure:
            parts.append("低压力提醒")
        if concise:
            parts.append("只给一个小提示")
        if no_proof:
            parts.append("不要求证明")
        return "；".join(parts) if parts else "保持默认温和提醒"

    def _apply_copy_policy(self, candidate: Dict[str, Any], copy_policy: Dict[str, Any]) -> Dict[str, Any]:
        if not candidate:
            return candidate
        candidate = {**candidate}
        subject = candidate.get("subject_title", "")
        event_type = candidate.get("type", "")
        if event_type == "focus_expired":
            display = f"我先帮你记着：这段专注【{subject}】已经到点了，回来时简单收一下进展就好。"
        elif event_type == "commitment_overdue":
            display = f"我先帮你把承诺【{subject}】标出来：它已经过了截止时间，之后可以选择关闭、延期或放下。"
        elif event_type == "commitment_due_today":
            display = f"我先帮你记着：承诺【{subject}】今天到期，相关时轻轻处理一下就好。"
        elif event_type == "task_stale":
            display = f"我先帮你保留主线：当前任务【{subject}】有一阵子没更新了，回来时接上一个小动作就行。"
        elif event_type in {"screen_deviation", "screen_accompaniment"}:
            display = candidate.get("display_message") or self._screen_fallback_message(candidate)
        else:
            display = candidate.get("message", "")

        if copy_policy.get("concise") and event_type not in {"screen_deviation", "screen_accompaniment"}:
            display = self._compact_sentence(display, limit=90)
        if copy_policy.get("no_proof"):
            display = display.replace("收一下进展", "说一句进展")
        candidate["display_message"] = display
        metadata = candidate.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        candidate["metadata"] = {
            **metadata,
            "copy_policy": copy_policy.get("summary", ""),
        }
        return candidate

    def _screen_fallback_message(self, candidate: Dict[str, Any]) -> str:
        event_type = candidate.get("type", "")
        metadata = candidate.get("metadata", {}) if isinstance(candidate.get("metadata", {}), dict) else {}
        goal = metadata.get("focus_goal") or candidate.get("subject_title") or "当前主线"
        if event_type == "screen_deviation":
            return f"先回来一下，当前主线是【{goal}】。"
        return f"这段还在【{goal}】上。"

    def _compact_sentence(self, text: str, limit: int = 90) -> str:
        text = str(text or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip("，。；、 ") + "。"

    def _tone_policy(
        self,
        preferences: Dict[str, Any],
        support_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        states = {
            str(item).strip().lower()
            for item in ((support_state or {}).get("states") or [])
            if str(item).strip()
        }
        pressure_states = {"anxious", "tired", "avoidant", "stuck", "scattered", "overplanning"}
        matched_states = sorted(states & pressure_states)
        now = datetime.now()
        rest_time = now.hour >= 22 or now.hour < 7

        if matched_states or rest_time:
            reasons = []
            if matched_states:
                reasons.append("检测到用户可能处在压力、疲惫、分散或卡住状态")
            if rest_time:
                reasons.append("当前处于休息时段")
            updates: Dict[str, Any] = {}
            if preferences.get("reminder_strength") != "soft":
                updates["reminder_strength"] = "soft"
            if preferences.get("browser_min_severity") != "high":
                updates["browser_min_severity"] = "high"
                updates["push_min_severity"] = "high"
            if preferences.get("background_min_severity") != "high":
                updates["background_min_severity"] = "high"
            return {
                "mode": "soften",
                "summary": "；".join(reasons) + "，适合自动降低监督语气。",
                "states": matched_states,
                "rest_time": rest_time,
                "reply_guidance": "只做状态确认和一个很小的提示，不追问、不催促、不展开长建议。",
                "preference_updates": updates,
            }

        return {
            "mode": "normal",
            "summary": "当前没有明显压力或休息时段信号，保持温和提醒即可。",
            "states": [],
            "rest_time": False,
            "reply_guidance": "保持低压力、短回复，只在相关时补一句轻量建议。",
            "preference_updates": {},
        }

    def _type_friction_suggestion(self, event_type: str) -> str:
        if event_type == "focus_expired":
            return "专注超时提醒可以更多留在页面内，减少主动推送。"
        if event_type in {"commitment_due_today", "commitment_overdue"}:
            return "承诺提醒可以优先推送逾期项，今日到期项保持页面提醒。"
        if event_type == "task_stale":
            return "任务停滞提醒适合放轻，只在用户打开页面时露出。"
        return "这一类提醒可以降低主动推送频率。"

    def _merge_event_type_updates(
        self,
        first: Any,
        second: Dict[str, Dict[str, str]],
    ) -> Dict[str, Dict[str, str]]:
        merged = self._normalize_event_type_min_severity(first)
        for event_type, channels in self._normalize_event_type_min_severity(second).items():
            current = merged.get(event_type, {})
            current.update(channels)
            merged[event_type] = current
        return merged

    def _is_muted_now(self, event: Dict[str, Any]) -> bool:
        if event.get("status") != "muted":
            return False
        muted_until = self._parse_time(event.get("muted_until", ""))
        return bool(muted_until and muted_until > datetime.now())

    def _is_snoozed_now(self, event: Dict[str, Any]) -> bool:
        if event.get("status") != "snoozed":
            return False
        snoozed_until = self._parse_time(event.get("snoozed_until", ""))
        return bool(snoozed_until and snoozed_until > datetime.now())

    def _reactivate_paused_events(self, events: List[Dict[str, Any]], now: datetime) -> None:
        now_text = now.isoformat(timespec="seconds")
        for event in events:
            if event.get("status") == "snoozed":
                snoozed_until = self._parse_time(event.get("snoozed_until", ""))
                if snoozed_until and snoozed_until <= now:
                    event["status"] = "detected"
                    event["updated_at"] = now_text
            if event.get("status") == "muted":
                muted_until = self._parse_time(event.get("muted_until", ""))
                if muted_until and muted_until <= now:
                    event["status"] = "detected"
                    event["updated_at"] = now_text

    def _severity_rank(self, event: Dict[str, Any]) -> int:
        return {"high": 3, "medium": 2, "low": 1}.get(event.get("severity", "low"), 1)

    def _channel_min_severity(self, preferences: Dict[str, Any], channel: str, event_type: str = "") -> str:
        channel = str(channel or "background").strip().lower()
        event_overrides = preferences.get("event_type_min_severity", {})
        if isinstance(event_overrides, dict):
            channel_overrides = event_overrides.get(str(event_type or ""))
            if isinstance(channel_overrides, dict):
                override = str(channel_overrides.get(channel, "")).strip().lower()
                if override in {"low", "medium", "high"}:
                    return override
        if channel == "page":
            return preferences.get("page_min_severity") or preferences.get("min_severity", "low")
        if channel == "browser":
            return preferences.get("browser_min_severity") or preferences.get("push_min_severity", "medium")
        return preferences.get("background_min_severity") or preferences.get("push_min_severity", "medium")

    def _in_quiet_hours(self, now: datetime, preferences: Dict[str, Any]) -> bool:
        start = self._parse_clock(preferences.get("quiet_hours_start", "23:00"))
        end = self._parse_clock(preferences.get("quiet_hours_end", "07:00"))
        if start is None or end is None:
            return False
        current = now.hour * 60 + now.minute
        if start <= end:
            return start <= current < end
        return current >= start or current < end

    def _is_quiet_until(self, now: datetime, preferences: Dict[str, Any]) -> bool:
        quiet_until = self._parse_time(preferences.get("quiet_until", ""))
        return bool(quiet_until and quiet_until > now)

    def _llm_natural_language_updates(self, text: str, llm_client: Any = None) -> Dict[str, Any]:
        if not llm_client or not self._looks_like_reminder_control(text):
            return {}
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Workmate Agent 的提醒控制意图分类器。"
                    "只判断用户是否在调整提醒/通知/监督边界。"
                    "只输出合法 JSON，不要 Markdown，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "从用户输入中分类提醒控制意图。\n"
                    "允许 intent: none, restore_reminders, pause_reminders, quiet_today, "
                    "reduce_reminders, increase_reminders, commitments_only, focus_only, tasks_only, all_reminders。\n"
                    "如果用户只是在普通聊天、汇报计划、表达情绪，不要误判，intent=none。\n"
                    "可以输出 preferences 覆盖这些字段：enabled, page_min_severity, browser_min_severity, "
                    "background_min_severity, event_type_min_severity, default_snooze_minutes, "
                    "notify_focus, notify_commitments, notify_tasks。\n"
                    "severity 只允许 low/medium/high。confidence 取 0 到 1。\n"
                    "用户输入："
                    f"{text}\n"
                    "输出 JSON 示例："
                    "{\"intent\":\"reduce_reminders\",\"confidence\":0.82,"
                    "\"summary\":\"已降低主动提醒强度。\","
                    "\"preferences\":{\"browser_min_severity\":\"high\",\"background_min_severity\":\"high\"}}"
                ),
            },
        ]
        try:
            raw = llm_client.invoke_raw(messages) if hasattr(llm_client, "invoke_raw") else llm_client.invoke(messages=messages)
            parsed = self._parse_json_object(raw)
            return self._normalize_llm_control(parsed)
        except Exception:
            return {}

    def _looks_like_reminder_control(self, text: str) -> bool:
        compact = "".join(str(text or "").split()).lower()
        if not compact:
            return False
        keywords = [
            "提醒", "通知", "推送", "弹窗", "打扰", "催", "安静", "静音", "暂停",
            "恢复", "关闭", "打开", "少一点", "多一点", "只提醒", "别吵", "别弹",
            "专注提醒", "任务提醒", "承诺提醒", "手机", "浏览器", "后台",
        ]
        return any(keyword in compact for keyword in keywords)

    def _normalize_llm_control(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(parsed, dict):
            return {}
        intent = str(parsed.get("intent", "none")).strip().lower()
        allowed_intents = {
            "restore_reminders",
            "pause_reminders",
            "quiet_today",
            "reduce_reminders",
            "increase_reminders",
            "commitments_only",
            "focus_only",
            "tasks_only",
            "all_reminders",
        }
        if intent not in allowed_intents:
            return {}
        try:
            confidence = float(parsed.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        if confidence < 0.65:
            return {}

        base = self._control_update_from_intent(intent)
        preferences = {
            **base.get("preferences", {}),
            **self._safe_llm_control_preferences(parsed.get("preferences", {})),
        }
        return {
            "intent": intent,
            "summary": self._compact(parsed.get("summary") or base.get("summary", ""), 120),
            "preferences": preferences,
            "source": "llm",
        }

    def _control_update_from_intent(self, intent: str) -> Dict[str, Any]:
        today_until = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0).isoformat(timespec="seconds")
        mapping = {
            "restore_reminders": {
                "summary": "已恢复正常提醒。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "push_min_severity": "medium",
                    "browser_min_severity": "medium",
                    "background_min_severity": "high",
                    "notify_focus": True,
                    "notify_commitments": True,
                    "notify_tasks": True,
                },
            },
            "pause_reminders": {
                "summary": "已暂停主动提醒。",
                "preferences": {"enabled": False, "quiet_until": ""},
            },
            "quiet_today": {
                "summary": "今天会先保持安静，提醒仍会记录在页面内。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": today_until,
                    "push_min_severity": "high",
                    "browser_min_severity": "high",
                    "background_min_severity": "high",
                },
            },
            "reduce_reminders": {
                "summary": "已降低主动提醒强度。",
                "preferences": {
                    "enabled": True,
                    "push_min_severity": "high",
                    "browser_min_severity": "high",
                    "background_min_severity": "high",
                    "default_snooze_minutes": 120,
                },
            },
            "increase_reminders": {
                "summary": "已略微提高主动提醒强度。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "push_min_severity": "medium",
                    "browser_min_severity": "medium",
                    "background_min_severity": "medium",
                },
            },
            "commitments_only": {
                "summary": "已切换为只主动提醒承诺。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "notify_focus": False,
                    "notify_commitments": True,
                    "notify_tasks": False,
                },
            },
            "focus_only": {
                "summary": "已切换为只主动提醒专注。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "notify_focus": True,
                    "notify_commitments": False,
                    "notify_tasks": False,
                },
            },
            "tasks_only": {
                "summary": "已切换为只主动提醒任务停滞。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "notify_focus": False,
                    "notify_commitments": False,
                    "notify_tasks": True,
                },
            },
            "all_reminders": {
                "summary": "已开启全部提醒类型。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "notify_focus": True,
                    "notify_commitments": True,
                    "notify_tasks": True,
                },
            },
        }
        return mapping.get(intent, {})

    def _safe_llm_control_preferences(self, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        safe: Dict[str, Any] = {}
        severity_fields = {"page_min_severity", "browser_min_severity", "background_min_severity", "push_min_severity"}
        for field in severity_fields:
            severity = str(value.get(field, "")).strip().lower()
            if severity in {"low", "medium", "high"}:
                safe[field] = severity
        for field in ["enabled", "notify_focus", "notify_commitments", "notify_tasks"]:
            if isinstance(value.get(field), bool):
                safe[field] = value[field]
        if "event_type_min_severity" in value:
            event_type_min_severity = self._normalize_event_type_min_severity(value.get("event_type_min_severity"))
            if event_type_min_severity:
                safe["event_type_min_severity"] = event_type_min_severity
        if "default_snooze_minutes" in value:
            safe["default_snooze_minutes"] = self._bounded_int(value.get("default_snooze_minutes"), 5, 1440)
        return safe

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("reminder control output is not a JSON object")
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("reminder control JSON is not object")
        return parsed

    def _compact(self, text: Any, limit: int = 160) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    def _natural_language_updates(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        if not text:
            return {}
        compact = "".join(text.split()).lower()
        today_until = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0).isoformat(timespec="seconds")

        if any(phrase in compact for phrase in ["恢复提醒", "打开提醒", "正常提醒", "继续提醒", "提醒恢复"]):
            return {
                "intent": "restore_reminders",
                "summary": "已恢复正常提醒。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "push_min_severity": "medium",
                    "browser_min_severity": "medium",
                    "background_min_severity": "high",
                    "notify_focus": True,
                    "notify_commitments": True,
                    "notify_tasks": True,
                },
            }

        if any(phrase in compact for phrase in ["只提醒承诺", "只要承诺提醒", "只推送承诺"]):
            return {
                "intent": "commitments_only",
                "summary": "已切换为只主动提醒承诺。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "notify_focus": False,
                    "notify_commitments": True,
                    "notify_tasks": False,
                },
            }

        if any(phrase in compact for phrase in ["只提醒专注", "只要专注提醒", "只推送专注"]):
            return {
                "intent": "focus_only",
                "summary": "已切换为只主动提醒专注。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "notify_focus": True,
                    "notify_commitments": False,
                    "notify_tasks": False,
                },
            }

        if any(phrase in compact for phrase in ["只提醒任务", "只要任务提醒", "只推送任务"]):
            return {
                "intent": "tasks_only",
                "summary": "已切换为只主动提醒任务停滞。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "notify_focus": False,
                    "notify_commitments": False,
                    "notify_tasks": True,
                },
            }

        if any(phrase in compact for phrase in ["提醒全部", "全部提醒", "所有提醒"]):
            return {
                "intent": "all_reminders",
                "summary": "已开启全部提醒类型。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "notify_focus": True,
                    "notify_commitments": True,
                    "notify_tasks": True,
                },
            }

        if any(phrase in compact for phrase in ["今天安静一点", "今天别提醒", "今天不要提醒", "今天先安静", "今天安静"]):
            return {
                "intent": "quiet_today",
                "summary": "今天会先保持安静，提醒仍会记录在页面内。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": today_until,
                    "push_min_severity": "high",
                    "browser_min_severity": "high",
                    "background_min_severity": "high",
                },
            }

        if any(phrase in compact for phrase in ["暂停提醒", "关闭提醒", "不要提醒我", "先别提醒"]):
            return {
                "intent": "pause_reminders",
                "summary": "已暂停主动提醒。",
                "preferences": {
                    "enabled": False,
                    "quiet_until": "",
                },
            }

        if any(phrase in compact for phrase in ["少提醒", "别太频繁", "提醒少一点", "安静一点"]):
            return {
                "intent": "reduce_reminders",
                "summary": "已降低主动提醒强度。",
                "preferences": {
                    "enabled": True,
                    "push_min_severity": "high",
                    "browser_min_severity": "high",
                    "background_min_severity": "high",
                    "default_snooze_minutes": 120,
                },
            }

        if any(phrase in compact for phrase in ["多提醒", "积极提醒", "提醒积极一点"]):
            return {
                "intent": "increase_reminders",
                "summary": "已略微提高主动提醒强度。",
                "preferences": {
                    "enabled": True,
                    "quiet_until": "",
                    "push_min_severity": "medium",
                    "browser_min_severity": "medium",
                    "background_min_severity": "medium",
                },
            }

        return {}

    def _parse_clock(self, text: str) -> Optional[int]:
        parts = str(text or "").split(":")
        if len(parts) != 2:
            return None
        try:
            hour = max(0, min(23, int(parts[0])))
            minute = max(0, min(59, int(parts[1])))
        except ValueError:
            return None
        return hour * 60 + minute

    def _normalize_preferences(self, preferences: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self.default_preferences()
        severity = str(preferences.get("min_severity", defaults["min_severity"])).lower()
        if severity not in {"low", "medium", "high"}:
            severity = defaults["min_severity"]
        push_min_severity = str(preferences.get("push_min_severity", defaults["push_min_severity"])).lower()
        if push_min_severity not in {"low", "medium", "high"}:
            push_min_severity = defaults["push_min_severity"]
        page_min_severity = str(preferences.get("page_min_severity", defaults["page_min_severity"])).lower()
        if page_min_severity not in {"low", "medium", "high"}:
            page_min_severity = defaults["page_min_severity"]
        browser_min_severity = str(preferences.get("browser_min_severity", push_min_severity)).lower()
        if browser_min_severity not in {"low", "medium", "high"}:
            browser_min_severity = push_min_severity
        background_min_severity = str(preferences.get("background_min_severity", defaults["background_min_severity"])).lower()
        if background_min_severity not in {"low", "medium", "high"}:
            background_min_severity = defaults["background_min_severity"]
        voice_min_severity = str(preferences.get("voice_min_severity", defaults["voice_min_severity"])).lower()
        if voice_min_severity not in {"low", "medium", "high"}:
            voice_min_severity = defaults["voice_min_severity"]
        voice_provider = str(preferences.get("voice_provider", defaults["voice_provider"])).strip().lower()
        if voice_provider not in {"browser", "xfyun"}:
            voice_provider = defaults["voice_provider"]
        event_type_min_severity = self._normalize_event_type_min_severity(
            preferences.get("event_type_min_severity", defaults["event_type_min_severity"])
        )
        strength = str(preferences.get("reminder_strength", defaults["reminder_strength"])).lower()
        if strength not in {"soft", "gentle", "normal"}:
            strength = defaults["reminder_strength"]

        custom_blacklist = preferences.get("custom_blacklist_keywords", defaults.get("custom_blacklist_keywords", []))
        if not isinstance(custom_blacklist, list):
            custom_blacklist = []
        custom_blacklist = [str(x).strip() for x in custom_blacklist if x]

        custom_whitelist = preferences.get("custom_whitelist_keywords", defaults.get("custom_whitelist_keywords", []))
        if not isinstance(custom_whitelist, list):
            custom_whitelist = []
        custom_whitelist = [str(x).strip() for x in custom_whitelist if x]

        return {
            "enabled": bool(preferences.get("enabled", defaults["enabled"])),
            "reminder_strength": strength,
            "min_severity": severity,
            "push_min_severity": browser_min_severity,
            "page_min_severity": page_min_severity,
            "browser_min_severity": browser_min_severity,
            "background_min_severity": background_min_severity,
            "voice_enabled": bool(preferences.get("voice_enabled", defaults["voice_enabled"])),
            "voice_provider": voice_provider,
            "voice_min_severity": voice_min_severity,
            "voice_volume": self._bounded_float(preferences.get("voice_volume", defaults["voice_volume"]), 0.0, 1.0),
            "voice_rate": self._bounded_float(preferences.get("voice_rate", defaults["voice_rate"]), 0.6, 1.4),
            "voice_include_accompaniment": bool(preferences.get("voice_include_accompaniment", defaults["voice_include_accompaniment"])),
            "event_type_min_severity": event_type_min_severity,
            "default_snooze_minutes": self._bounded_int(preferences.get("default_snooze_minutes", 60), 5, 1440),
            "default_mute_hours": self._bounded_int(preferences.get("default_mute_hours", 24), 1, 168),
            "quiet_hours_enabled": bool(preferences.get("quiet_hours_enabled", defaults["quiet_hours_enabled"])),
            "quiet_hours_start": preferences.get("quiet_hours_start", defaults["quiet_hours_start"])
            if self._parse_clock(preferences.get("quiet_hours_start", "")) is not None else defaults["quiet_hours_start"],
            "quiet_hours_end": preferences.get("quiet_hours_end", defaults["quiet_hours_end"])
            if self._parse_clock(preferences.get("quiet_hours_end", "")) is not None else defaults["quiet_hours_end"],
            "quiet_until": preferences.get("quiet_until", defaults["quiet_until"])
            if self._parse_time(preferences.get("quiet_until", "")) is not None or not preferences.get("quiet_until")
            else defaults["quiet_until"],
            "notify_focus": bool(preferences.get("notify_focus", defaults["notify_focus"])),
            "notify_commitments": bool(preferences.get("notify_commitments", defaults["notify_commitments"])),
            "notify_tasks": bool(preferences.get("notify_tasks", defaults.get("notify_tasks", True))),
            "screen_monitor_enabled": bool(preferences.get("screen_monitor_enabled", defaults["screen_monitor_enabled"])),
            "screen_monitor_interval_minutes": self._bounded_int(preferences.get("screen_monitor_interval_minutes", defaults["screen_monitor_interval_minutes"]), 1, 60),
            "screen_force_message": bool(preferences.get("screen_force_message", defaults["screen_force_message"])),
            "last_screen_check": str(preferences.get("last_screen_check", defaults["last_screen_check"])),
            "auto_monitor_work_hours_enabled": bool(preferences.get("auto_monitor_work_hours_enabled", defaults["auto_monitor_work_hours_enabled"])),
            "work_hours_start": str(preferences.get("work_hours_start", defaults["work_hours_start"])),
            "work_hours_end": str(preferences.get("work_hours_end", defaults["work_hours_end"])),
            "custom_blacklist_keywords": custom_blacklist,
            "custom_whitelist_keywords": custom_whitelist,
        }

    def _normalize_event_type_min_severity(self, value: Any) -> Dict[str, Dict[str, str]]:
        if not isinstance(value, dict):
            return {}
        allowed_types = {"focus_expired", "commitment_due_today", "commitment_overdue", "task_stale", "screen_deviation"}
        allowed_channels = {"page", "browser", "background", "voice"}
        result: Dict[str, Dict[str, str]] = {}
        for event_type, channels in value.items():
            event_type = str(event_type or "").strip()
            if event_type not in allowed_types or not isinstance(channels, dict):
                continue
            normalized_channels = {}
            for channel, severity in channels.items():
                channel = str(channel or "").strip().lower()
                severity = str(severity or "").strip().lower()
                if channel in allowed_channels and severity in {"low", "medium", "high"}:
                    normalized_channels[channel] = severity
            if normalized_channels:
                result[event_type] = normalized_channels
        return result

    def _dedupe_key(self, event: Dict[str, Any]) -> str:
        return "|".join([
            str(event.get("type", "")),
            str(event.get("subject_type", "")),
            str(event.get("subject_id", "")),
        ])

    def _make_id(self, now: str, dedupe_key: str) -> str:
        safe_time = now.replace("-", "").replace(":", "").replace("T", "-")
        digest = hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:10]
        return f"sup-{safe_time}-{digest}"

    def _parse_time(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _bounded_int(self, value: Any, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = minimum
        return max(minimum, min(maximum, number))

    def _bounded_float(self, value: Any, minimum: float, maximum: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = minimum
        return max(minimum, min(maximum, number))
