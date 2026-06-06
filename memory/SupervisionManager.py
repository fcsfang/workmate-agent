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
        if open_commitments:
            signals.append({
                "type": "open_commitment",
                "severity": "medium",
                "message": f"还有 {len(open_commitments)} 个未关闭承诺，回复时应帮助用户回到已答应推进的事项。",
            })

        repeated_blockers = self._repeated_blockers(memory_items)
        if repeated_blockers:
            signals.append({
                "type": "repeated_blocker",
                "severity": "high",
                "message": "反复出现的阻塞/风险: " + "、".join(repeated_blockers[:4]),
            })

        active_tasks = task_view.get("active") or []
        if len(active_tasks) >= 4:
            signals.append({
                "type": "too_many_open_tasks",
                "severity": "medium",
                "message": "未关闭任务偏多，回复时应提醒用户收敛主线。",
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
            return "暂无需要主动监督的明显信号。"
        lines = ["以下是主动监督信号。请只在相关时自然提醒，不要制造压力，不要要求证据。"]
        for index, signal in enumerate(state["signals"][:5], start=1):
            lines.append(f"{index}. [{signal.get('severity', 'low')}] {signal.get('message', '')}")
        if state.get("proactive_message"):
            lines.append("建议监督语气: " + state["proactive_message"])
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
                "severity": "high",
                "message": f"当前任务已约 {int(hours)} 小时没有更新，适合询问实际进展并帮助收敛下一步。",
            }
        if hours >= 6:
            return {
                "type": "stale_task",
                "severity": "medium",
                "message": f"当前任务已有一段时间未更新，适合温和提醒用户回到主线。",
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
            return f"围绕“{task_title}”做一次短提醒：先问真实进展，再帮用户收敛当前主线。{preference}"
        return f"做一次短提醒：关注真实产出和当前主线。{preference}"

    def _parse_time(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
