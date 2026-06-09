from datetime import datetime
from typing import Any, Dict, List, Optional


class SupervisionManager:
    def build_state(
        self,
        task_view: Dict[str, Any],
        commitments: List[Dict[str, Any]],
        memory_items: List[Dict[str, Any]],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = datetime.now()
        current = task_view.get("current") or {}
        signals = []

        stale = self._staleness_signal(current, now)
        if stale:
            signals.append(stale)

        open_commitments = [item for item in commitments if item.get("status") == "open"]
        for signal in self._commitment_deadline_signals(open_commitments, now):
            signals.append(signal)
        if open_commitments:
            signals.append({
                "type": "open_commitment",
                "severity": "low",
                "message": f"还有 {len(open_commitments)} 个未关闭承诺；只在相关时顺手提醒用户这些事项还被记着。",
            })

        repeated_blockers = self._repeated_blockers(memory_items)
        if repeated_blockers:
            signals.append({
                "type": "repeated_blocker",
                "severity": "medium",
                "message": "反复出现的阻塞/风险，可在相关时给一句小建议: " + "、".join(repeated_blockers[:4]),
            })

        active_tasks = task_view.get("active") or []
        if len(active_tasks) >= 4:
            signals.append({
                "type": "too_many_open_tasks",
                "severity": "low",
                "message": "未关闭任务偏多；如果用户正在新增任务，可以轻轻建议先保留一个主线。",
            })

        prompt = self._build_prompt(signals, current, user_profile or {})
        return {
            "generated_at": now.isoformat(timespec="seconds"),
            "signals": signals,
            "proactive_message": prompt,
            "should_nudge": bool(signals),
        }

    def format_for_context(self, state: Dict[str, Any]) -> str:
        if not state.get("signals"):
            return "暂无需要主动提醒的明显信号。"
        lines = ["以下是轻量提醒信号。请优先记住和整理；只在相关时给一句小建议，不要制造压力，不要要求证据。"]
        for index, signal in enumerate(state["signals"][:5], start=1):
            lines.append(f"{index}. [{signal.get('severity', 'low')}] {signal.get('message', '')}")
        if state.get("proactive_message"):
            lines.append("建议回应语气: " + state["proactive_message"])
        return "\n".join(lines)

    def _staleness_signal(self, task: Dict[str, Any], now: datetime) -> Dict[str, str]:
        if not task.get("id") or task.get("status") in {"done", "abandoned"}:
            return {}
        updated_at = self._parse_time(task.get("updated_at", ""))
        if not updated_at:
            return {}
        hours = (now - updated_at).total_seconds() / 3600
        if hours >= 24:
            return {
                "type": "stale_task",
                "severity": "medium",
                "message": f"当前任务已约 {int(hours)} 小时没有更新；可以温和提醒用户回来同步进展，不要用追问催促。",
            }
        if hours >= 6:
            return {
                "type": "stale_task",
                "severity": "low",
                "message": "当前任务已有一段时间未更新；暂不催促，必要时轻轻提醒它还被记着。",
            }
        return {}

    def _repeated_blockers(self, memory_items: List[Dict[str, Any]]) -> List[str]:
        counts = {}
        for item in memory_items:
            if item.get("type") != "blocker":
                continue
            content = item.get("content", "")
            if not content:
                continue
            source_count = len(item.get("source_record_ids", [])) if isinstance(item.get("source_record_ids", []), list) else 0
            counts[content] = max(counts.get(content, 0), source_count, int(item.get("usage_count", 0)))
        return [content for content, count in sorted(counts.items(), key=lambda pair: pair[1], reverse=True) if count >= 2]

    def _build_prompt(self, signals: List[Dict[str, str]], task: Dict[str, Any], profile: Dict[str, Any]) -> str:
        if not signals:
            return ""
        task_title = task.get("title", "")
        preference = "；".join((profile.get("communication_preference") or [])[:3])
        if task_title:
            return f"围绕“{task_title}”保持低压力回应：先确认已记住；如有必要，只补一句小建议。{preference}"
        return f"保持低压力回应：先记住和整理；如有必要，只补一句小建议。{preference}"

    def _commitment_deadline_signals(self, open_commitments: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
        overdue = []
        due_today = []
        for item in open_commitments:
            deadline_str = item.get("deadline", "")
            if not deadline_str:
                continue
            try:
                deadline_dt = datetime.fromisoformat(deadline_str)
                if deadline_dt < now:
                    overdue.append(item.get("commitment", ""))
                elif deadline_dt.date() == now.date():
                    due_today.append(item.get("commitment", ""))
            except ValueError:
                continue

        signals = []
        if overdue:
            signals.append({
                "type": "overdue_commitment",
                "severity": "medium",
                "message": f"{len(overdue)} 个承诺已逾期；回复时可以顺手轻提，帮用户决定关闭或延期。",
            })
        if due_today:
            signals.append({
                "type": "due_today",
                "severity": "low",
                "message": f"今天有 {len(due_today)} 个承诺到期；可以在相关时轻轻提一句。",
            })
        return signals

    def _parse_time(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
