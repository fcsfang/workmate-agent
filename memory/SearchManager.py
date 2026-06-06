import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class SearchManager:
    def __init__(self, index_path: Optional[str] = None):
        memory_dir = Path(__file__).resolve().parent
        self.index_path = Path(index_path) if index_path else memory_dir / "retrieval_index.json"
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

    def build_index(
        self,
        records: List[Dict[str, Any]],
        daily_summaries: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        commitments: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        items = []
        for index, record in enumerate(records[-120:]):
            text = " ".join([
                record.get("time", ""),
                record.get("user", ""),
                self._sanitize_text(record.get("assistant", "")),
                json.dumps(record.get("extracted", {}), ensure_ascii=False),
            ])
            items.append(self._item("record", f"record-{index}", text, record))

        for summary in daily_summaries or []:
            text = self._sanitize_text(json.dumps(summary, ensure_ascii=False))
            items.append(self._item("daily_summary", summary.get("date", ""), text, summary))

        if user_profile:
            items.append(self._item("user_profile", "user_profile", self._sanitize_text(json.dumps(user_profile, ensure_ascii=False)), user_profile))

        for commitment in commitments or []:
            text = self._sanitize_text(json.dumps(commitment, ensure_ascii=False))
            items.append(self._item("commitment", commitment.get("id", ""), text, commitment))

        self.save_index(items)
        return items

    def search(
        self,
        query: str,
        records: List[Dict[str, Any]],
        daily_summaries: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        commitments: Optional[List[Dict[str, Any]]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        items = self.build_index(records, daily_summaries, user_profile, commitments)
        query_terms = self._terms(query)
        if not query_terms:
            return []

        scored = []
        for item in items:
            score = sum(item["terms"].count(term) for term in query_terms)
            if score:
                scored.append({**item, "score": score})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]

    def format_for_context(self, results: List[Dict[str, Any]]) -> str:
        if not results:
            return "暂无与当前输入直接相关的历史检索结果。"

        lines = ["以下是与当前输入相关的历史记忆。请只在相关时引用。"]
        for index, item in enumerate(results, start=1):
            lines.append(f"{index}. [{item['type']}] {self._compact(item['text'], 220)}")
        return "\n".join(lines)

    def save_index(self, items: List[Dict[str, Any]]) -> None:
        serializable = [{key: value for key, value in item.items() if key != "payload"} for item in items]
        with self.index_path.open("w", encoding="utf-8") as file:
            json.dump(serializable, file, ensure_ascii=False, indent=2)

    def _item(self, item_type: str, item_id: str, text: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": item_type,
            "id": item_id,
            "text": self._compact(text, 500),
            "terms": self._terms(text),
            "payload": payload,
        }

    def _terms(self, text: str) -> List[str]:
        text = str(text)
        separators = " \n\t\r，。！？、；;:：/\\|+-_*()（）[]【】{}<>\"'"
        normalized = text
        for separator in separators:
            normalized = normalized.replace(separator, " ")
        terms = [part.strip().lower() for part in normalized.split() if len(part.strip()) >= 2]

        chinese_keywords = [
            "拖延", "分心", "走神", "总结", "复盘", "实习", "大模型",
            "任务", "进度", "完成", "阻塞", "下一步", "生命周期", "高频词", "JD", "Agent",
        ]
        for keyword in chinese_keywords:
            if keyword.lower() in text.lower():
                terms.append(keyword.lower())
        return terms

    def _compact(self, text: str, max_length: int = 300) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."

    def _sanitize_text(self, text: str) -> str:
        lines = []
        for line in str(text or "").splitlines():
            if any(keyword in line for keyword in ["证据", "截图", "截屏", "强制验证", "不承认无证据"]):
                continue
            lines.append(line)
        return "\n".join(lines)
