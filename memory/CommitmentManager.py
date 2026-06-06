import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class CommitmentManager:
    def __init__(self, commitments_path: Optional[str] = None):
        memory_dir = Path(__file__).resolve().parent
        self.commitments_path = Path(commitments_path) if commitments_path else memory_dir / "commitments.json"
        self.commitments_path.parent.mkdir(parents=True, exist_ok=True)

    def load_commitments(self) -> List[Dict[str, Any]]:
        if not self.commitments_path.exists() or self.commitments_path.stat().st_size == 0:
            return []

        try:
            with self.commitments_path.open("r", encoding="utf-8") as file:
                commitments = json.load(file)
        except json.JSONDecodeError:
            return []

        if not isinstance(commitments, list):
            return []
        return [item for item in (self._sanitize_item(item) for item in commitments) if item]

    def save_commitments(self, commitments: List[Dict[str, Any]]) -> None:
        with self.commitments_path.open("w", encoding="utf-8") as file:
            json.dump(commitments, file, ensure_ascii=False, indent=2)

    def update(
        self,
        extracted: Dict[str, Any],
        user_input: str,
        assistant_output: str,
        task_state: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        commitments = self.load_commitments()
        now = datetime.now().isoformat(timespec="seconds")
        active_task = (task_state or {}).get("active_task", "")

        commitments = self._close_completed(commitments, user_input, now)
        new_items = self._build_new_commitments(extracted, active_task, now)
        for item in new_items:
            if not self._exists_open(commitments, item):
                commitments.append(item)

        commitments = self._trim(commitments)
        self.save_commitments(commitments)
        return commitments

    def get_open_commitments(self) -> List[Dict[str, Any]]:
        return [item for item in self.load_commitments() if item.get("status") == "open"]

    def format_for_context(self) -> str:
        open_items = self.get_open_commitments()
        if not open_items:
            return "暂无未关闭承诺。"

        lines = [
            "以下是未关闭承诺。请关注用户和 Agent 已经明确答应要做的事，不要让它们被新话题覆盖。",
        ]
        for index, item in enumerate(open_items[-8:], start=1):
            parts = [
                f"{index}. {item.get('commitment', '')}",
                f"owner={item.get('owner', 'user')}",
            ]
            if item.get("task"):
                parts.append(f"task={item['task']}")
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def _build_new_commitments(
        self,
        extracted: Dict[str, Any],
        active_task: str,
        now: str,
    ) -> List[Dict[str, Any]]:
        items = []
        for commitment in extracted.get("user_commitments") or []:
            items.append(self._new_item("user", commitment, active_task, now))
        return items

    def _new_item(self, owner: str, commitment: str, task: str, now: str) -> Dict[str, Any]:
        return {
            "id": self._make_id(now, commitment),
            "owner": owner,
            "task": task,
            "commitment": self._compact(commitment),
            "status": "open",
            "created_at": now,
            "closed_at": "",
        }

    def _close_completed(self, commitments: List[Dict[str, Any]], user_input: str, now: str) -> List[Dict[str, Any]]:
        if not any(keyword in user_input for keyword in ["完成", "做完", "已经", "提交", "统计"]):
            return commitments

        for item in commitments:
            if item.get("status") != "open":
                continue
            if self._looks_satisfied(item, user_input):
                item["status"] = "closed"
                item["closed_at"] = now
        return commitments

    def _looks_satisfied(self, item: Dict[str, Any], user_input: str) -> bool:
        text = item.get("commitment", "")
        keywords = [keyword for keyword in self._keywords(text) if len(keyword) >= 2]
        if not keywords:
            return False
        matched = sum(1 for keyword in keywords if keyword in user_input)
        return matched >= 1 and any(done in user_input for done in ["完成", "已经", "做完", "发给你", "统计"])

    def _exists_open(self, commitments: List[Dict[str, Any]], new_item: Dict[str, Any]) -> bool:
        for item in commitments:
            if item.get("status") == "open" and item.get("commitment") == new_item.get("commitment"):
                return True
        return False

    def _trim(self, commitments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        open_items = [item for item in commitments if item.get("status") == "open"]
        closed_items = [item for item in commitments if item.get("status") != "open"]
        return [*closed_items[-30:], *open_items[-30:]]

    def _sanitize_item(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        cleaned = dict(item)
        cleaned.pop("evidence_required", None)
        commitment = cleaned.get("commitment", "")
        if cleaned.get("owner") == "agent" and self._looks_like_old_evidence_request(commitment):
            return {}
        return cleaned

    def _looks_like_old_evidence_request(self, text: str) -> bool:
        return any(keyword in str(text) for keyword in ["证据", "截图", "截屏", "运行输出", "强制验证", "可验证"])

    def _keywords(self, text: str) -> List[str]:
        separators = " ，。！？、；;:：/\\|+-_*()（）[]【】"
        normalized = text
        for separator in separators:
            normalized = normalized.replace(separator, " ")
        return [part.strip() for part in normalized.split() if part.strip()]

    def _make_id(self, now: str, text: str) -> str:
        safe_time = now.replace("-", "").replace(":", "").replace("T", "-")
        return f"{safe_time}-{abs(hash(text)) % 100000:05d}"

    def _compact(self, text: str, max_length: int = 160) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
