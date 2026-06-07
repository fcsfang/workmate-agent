import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class UserProfileManager:
    def __init__(self, profile_path: Optional[str] = None):
        memory_dir = Path(__file__).resolve().parent
        self.profile_path = Path(profile_path) if profile_path else memory_dir / "user_profile.json"
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)

    def load_profile(self) -> Dict[str, Any]:
        if not self.profile_path.exists() or self.profile_path.stat().st_size == 0:
            return self.default_profile()

        try:
            with self.profile_path.open("r", encoding="utf-8") as file:
                profile = json.load(file)
        except json.JSONDecodeError:
            return self.default_profile()

        if not isinstance(profile, dict):
            return self.default_profile()
        return self._sanitize_profile({**self.default_profile(), **profile})

    def save_profile(self, profile: Dict[str, Any]) -> None:
        with self.profile_path.open("w", encoding="utf-8") as file:
            json.dump(profile, file, ensure_ascii=False, indent=2)

    def update(
        self,
        extracted: Dict[str, Any],
        user_input: str,
        assistant_output: str,
        recent_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        profile = self.load_profile()
        now = datetime.now().isoformat(timespec="seconds")

        if any(keyword in user_input for keyword in ["实习", "大模型", "AI", "求职", "工作机会"]):
            profile["long_term_goal"] = "获得AI/大模型相关实习或工作机会"

        blockers = extracted.get("blockers") or []
        if blockers:
            profile["failure_modes"] = self._merge_unique(
                profile.get("failure_modes", []),
                [f"容易出现：{blocker}" for blocker in blockers],
                limit=10,
            )

        if extracted.get("task"):
            profile["working_style"] = self._merge_unique(
                profile.get("working_style", []),
                ["适合围绕明确任务和下一步行动推进"],
                limit=10,
            )

        if recent_summary:
            patterns = recent_summary.get("repeated_patterns") or []
            profile["failure_modes"] = self._merge_unique(profile.get("failure_modes", []), patterns, limit=10)
            advice = recent_summary.get("supervision_advice") or []
            profile["effective_interventions"] = self._merge_unique(profile.get("effective_interventions", []), advice, limit=10)

        profile["communication_preference"] = self._merge_unique(
            profile.get("communication_preference", []),
            ["中文", "先帮用户记住和整理", "低压力回应", "只给一个小建议", "不要每次都强制要求证明"],
            limit=8,
        )
        profile["updated_at"] = now
        self.save_profile(profile)
        return profile

    def format_for_context(self) -> str:
        profile = self.load_profile()
        lines = [
            "以下是长期用户画像。请用它调整回应方式：先记住和整理，必要时轻量提醒，不要机械复述。",
            f"长期目标: {profile.get('long_term_goal') or '暂无'}",
        ]
        if profile.get("working_style"):
            lines.append("工作风格: " + "；".join(profile["working_style"][:5]))
        if profile.get("failure_modes"):
            lines.append("常见风险: " + "；".join(profile["failure_modes"][:5]))
        if profile.get("effective_interventions"):
            lines.append("有效干预: " + "；".join(profile["effective_interventions"][:5]))
        if profile.get("communication_preference"):
            lines.append("沟通偏好: " + "；".join(profile["communication_preference"][:5]))
        return "\n".join(lines)

    def default_profile(self) -> Dict[str, Any]:
        return {
            "long_term_goal": "",
            "working_style": [],
            "failure_modes": [],
            "effective_interventions": [],
            "communication_preference": [],
            "updated_at": "",
        }

    def _merge_unique(self, first: List[str], second: List[str], limit: int) -> List[str]:
        result = []
        for item in [*first, *second]:
            item = self._compact(item)
            if item and item not in result:
                result.append(item)
        return result[:limit]

    def _sanitize_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        for key in ["working_style", "failure_modes", "effective_interventions", "communication_preference"]:
            values = profile.get(key, [])
            if isinstance(values, list):
                profile[key] = self._soften_values(values)
        profile["communication_preference"] = self._merge_unique(
            profile.get("communication_preference", []),
            ["中文", "先帮用户记住和整理", "低压力回应", "只给一个小建议"],
            limit=8,
        )
        return profile

    def _looks_like_forced_proof(self, text: str) -> bool:
        return any(keyword in str(text) for keyword in ["证据", "截图", "无证据", "可验证", "验证标准", "运行结果后再认可", "不承认"])

    def _soften_values(self, values: List[str]) -> List[str]:
        result = []
        replacements = {
            "直接指出问题": "温和指出一个可能风险",
            "强调真实产出": "关注核心事项和实际进展",
            "强监督": "轻量提醒",
            "监督": "轻量提醒",
        }
        for value in values:
            if self._looks_like_forced_proof(value):
                continue
            text = str(value)
            for old, new in replacements.items():
                text = text.replace(old, new)
            text = self._compact(text)
            if text and text not in result:
                result.append(text)
        return result

    def _compact(self, text: str, max_length: int = 140) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
