"""Human-readable long-term knowledge projected from structured memory."""

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class LongTermKnowledgeManager:
    """Maintain the stable cognition layer used during context assembly.

    Structured JSON remains the compatibility write model. These Markdown files
    are the compact, auditable representation the model reads as long-term
    knowledge; volatile execution state is deliberately excluded.
    """

    FILES = {
        "user": "USER.md",
        "goals": "GOALS.md",
        "preferences": "PREFERENCES.md",
        "patterns": "PATTERNS.md",
        "insights": "INSIGHTS.md",
    }

    def __init__(self, knowledge_dir: Optional[str] = None):
        self.knowledge_dir = Path(knowledge_dir) if knowledge_dir else Path(__file__).parent / "data" / "knowledge"

    def sync(
        self,
        user_profile: Optional[Dict[str, Any]] = None,
        insights: Optional[List[Dict[str, Any]]] = None,
        behavior_patterns: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, str]:
        profile = user_profile or {}
        active_insights = [item for item in (insights or []) if item.get("status", "active") == "active"]
        active_patterns = [item for item in (behavior_patterns or []) if item.get("status", "active") == "active"]
        documents = {
            "user": self._document(
                "User",
                "Stable observations about how the user works.",
                [
                    ("Working Style", profile.get("working_style", [])),
                    ("Recurring Difficulties", profile.get("failure_modes", [])),
                    ("Effective Support", profile.get("effective_interventions", [])),
                ],
            ),
            "goals": self._document(
                "Goals",
                "Stable long-term goals. Current tasks are stored in the execution-state layer.",
                [("Long-term Goal", [profile.get("long_term_goal", "")])],
            ),
            "preferences": self._document(
                "Preferences",
                "Explicit communication and supervision preferences.",
                [("Communication", profile.get("communication_preference", []))],
            ),
            "patterns": self._document(
                "Patterns",
                "Repeated behavior patterns supported by multiple observations.",
                [("Active Patterns", [self._pattern_line(item) for item in active_patterns[:12]])],
            ),
            "insights": self._document(
                "Insights",
                "Higher-order reflections. Treat these as guidance, not current task truth.",
                [("Active Insights", [self._insight_line(item) for item in active_insights[:12]])],
            ),
        }
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        for key, content in documents.items():
            self._atomic_write(self.knowledge_dir / self.FILES[key], content)
        return {key: str(self.knowledge_dir / filename) for key, filename in self.FILES.items()}

    def format_for_context(self, intent: str = "chat", max_chars: int = 6000) -> str:
        keys = ["user", "goals", "preferences"]
        if intent in {"task", "review", "supervision", "weekly_report"}:
            keys.extend(["patterns", "insights"])

        sections = []
        for key in keys:
            path = self.knowledge_dir / self.FILES[key]
            if path.is_file():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    sections.append(content)
        if not sections:
            return "暂无长期认知文件。"
        return self._truncate(
            "以下是分层长期认知文件。它们用于调整理解和回应方式，不能覆盖当前任务、承诺或专注状态。\n\n"
            + "\n\n".join(sections),
            max_chars,
        )

    def list_documents(self) -> List[Dict[str, Any]]:
        documents = []
        for key, filename in self.FILES.items():
            path = self.knowledge_dir / filename
            documents.append({
                "key": key,
                "filename": filename,
                "path": str(path),
                "exists": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else 0,
            })
        return documents

    def has_documents(self) -> bool:
        return any((self.knowledge_dir / filename).is_file() for filename in self.FILES.values())

    def _document(self, title: str, description: str, sections: Iterable[Any]) -> str:
        lines = [f"# {title}", "", description, ""]
        for heading, values in sections:
            lines.extend([f"## {heading}", ""])
            normalized = self._values(values)
            lines.extend([f"- {value}" for value in normalized] or ["- None recorded"])
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _pattern_line(self, item: Dict[str, Any]) -> str:
        text = item.get("summary") or item.get("title") or item.get("content") or ""
        intervention = item.get("suggested_intervention", "")
        return self._compact(f"{text}" + (f" Suggested support: {intervention}" if intervention else ""), 360)

    def _insight_line(self, item: Dict[str, Any]) -> str:
        text = item.get("content") or item.get("summary") or ""
        reason = item.get("why_it_matters", "")
        return self._compact(f"{text}" + (f" Why it matters: {reason}" if reason else ""), 360)

    def _values(self, values: Any) -> List[str]:
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            return []
        result = []
        for value in values:
            text = self._compact(value, 360)
            if text and text not in result:
                result.append(text)
        return result

    def _atomic_write(self, path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _compact(value: Any, max_chars: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "..."

    @staticmethod
    def _truncate(value: Any, max_chars: int) -> str:
        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "..."
