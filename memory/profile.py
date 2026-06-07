import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import memory_data_path


class UserProfileManager:
    def __init__(self, profile_path: Optional[str] = None, llm_client: Optional[Any] = None):
        self.profile_path = Path(profile_path) if profile_path else memory_data_path("user_profile.json")
        self.llm_client = llm_client
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)

    def set_llm_client(self, llm_client: Any) -> None:
        self.llm_client = llm_client

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

        updates = self._extract_profile_updates_with_llm(profile, extracted, user_input, assistant_output, recent_summary)
        if updates:
            self._apply_profile_updates(profile, updates)
        else:
            self._apply_rule_updates(profile, extracted, user_input, recent_summary)

        profile["communication_preference"] = self._merge_unique(
            profile.get("communication_preference", []),
            ["中文", "先帮用户记住和整理", "低压力回应", "只给一个小建议", "不要每次都强制要求证明"],
            limit=8,
        )
        profile["updated_at"] = now
        self.save_profile(profile)
        return profile

    def _extract_profile_updates_with_llm(
        self,
        profile: Dict[str, Any],
        extracted: Dict[str, Any],
        user_input: str,
        assistant_output: str,
        recent_summary: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not self.llm_client:
            return {}
        schema = {
            "long_term_goal": "稳定长期目标；没有新信息则为空字符串",
            "working_style": ["稳定工作风格或偏好"],
            "failure_modes": ["反复出现的风险或困难模式"],
            "effective_interventions": ["对用户有效的低压力帮助方式"],
            "communication_preference": ["用户明确表达的沟通偏好"],
            "reason": "一句话说明",
        }
        payload = {
            "current_profile": profile,
            "extracted": extracted,
            "recent_summary": recent_summary or {},
            "user_input": user_input,
            "assistant_output": assistant_output,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Workmate Agent 的用户画像更新器。"
                    "只提取稳定、可复用的用户画像增量，不要把单次普通表达写成长期偏好。"
                    "只输出合法 JSON，不要 Markdown，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "要求：\n"
                    "1. 只在用户明确表达或多次模式支持时更新画像。\n"
                    "2. 不要写入强制证据、催促、压力式监督偏好。\n"
                    "3. communication_preference 只能来自用户明确表达。\n"
                    "4. 所有数组最多 6 项，每项简短。\n\n"
                    f"schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                    f"payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
                ),
            },
        ]
        try:
            raw = self.llm_client.invoke_raw(messages) if hasattr(self.llm_client, "invoke_raw") else self.llm_client.invoke(messages=messages)
            parsed = self._parse_json_object(raw)
            return {
                "long_term_goal": self._compact(parsed.get("long_term_goal", ""), 160),
                "working_style": self._list_field(parsed.get("working_style", []), 8),
                "failure_modes": self._list_field(parsed.get("failure_modes", []), 8),
                "effective_interventions": self._list_field(parsed.get("effective_interventions", []), 8),
                "communication_preference": self._list_field(parsed.get("communication_preference", []), 6),
            }
        except Exception:
            return {}

    def _apply_profile_updates(self, profile: Dict[str, Any], updates: Dict[str, Any]) -> None:
        if updates.get("long_term_goal"):
            profile["long_term_goal"] = updates["long_term_goal"]
        for key, limit in [
            ("working_style", 10),
            ("failure_modes", 10),
            ("effective_interventions", 10),
            ("communication_preference", 8),
        ]:
            profile[key] = self._merge_unique(profile.get(key, []), updates.get(key, []), limit=limit)

    def _apply_rule_updates(
        self,
        profile: Dict[str, Any],
        extracted: Dict[str, Any],
        user_input: str,
        recent_summary: Optional[Dict[str, Any]],
    ) -> None:
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

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("profile output is not a JSON object")
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("profile output JSON is not object")
        return parsed

    def _list_field(self, value: Any, limit: int) -> List[str]:
        if isinstance(value, str):
            value = [value] if value else []
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            item = self._compact(item)
            if item and not self._looks_like_forced_proof(item) and item not in result:
                result.append(item)
        return result[:limit]

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
