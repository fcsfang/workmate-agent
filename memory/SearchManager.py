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
        memory_items: Optional[List[Dict[str, Any]]] = None,
        memory_categories: Optional[List[Dict[str, Any]]] = None,
        memory_resources: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        items = []
        for index, record in enumerate(records[-120:]):
            text = " ".join([
                record.get("id", ""),
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

        for memory_item in memory_items or []:
            text = self._sanitize_text(" ".join([
                memory_item.get("type", ""),
                memory_item.get("category", ""),
                memory_item.get("content", ""),
                memory_item.get("task_title", ""),
                json.dumps(memory_item.get("metadata", {}), ensure_ascii=False),
            ]))
            items.append(self._item("memory_item", memory_item.get("id", ""), text, memory_item))

        for category in memory_categories or []:
            text = self._sanitize_text(" ".join([
                category.get("name", ""),
                category.get("description", ""),
                category.get("summary", ""),
                json.dumps(category.get("type_counts", {}), ensure_ascii=False),
            ]))
            items.append(self._item("memory_category", category.get("id", ""), text, category))

        for resource in memory_resources or []:
            text = self._sanitize_text(" ".join([
                resource.get("record_id", ""),
                resource.get("time", ""),
                resource.get("user_preview", ""),
                resource.get("assistant_preview", ""),
                resource.get("task_title", ""),
                json.dumps(resource.get("extracted_categories", []), ensure_ascii=False),
            ]))
            items.append(self._item("memory_resource", resource.get("id", ""), text, resource))

        self.save_index(items)
        return items

    def search(
        self,
        query: str,
        records: List[Dict[str, Any]],
        daily_summaries: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        commitments: Optional[List[Dict[str, Any]]] = None,
        memory_items: Optional[List[Dict[str, Any]]] = None,
        memory_categories: Optional[List[Dict[str, Any]]] = None,
        memory_resources: Optional[List[Dict[str, Any]]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if not self.needs_retrieval(query):
            return []

        items = self.build_index(
            records,
            daily_summaries,
            user_profile,
            commitments,
            memory_items,
            memory_categories,
            memory_resources,
        )
        query_terms = self._terms(query)
        if not query_terms:
            return []

        preferred_types = self._preferred_types(query)
        scored = []
        for item in items:
            score = sum(item["terms"].count(term) for term in query_terms)
            if item["type"] in preferred_types:
                score += 1
            payload = item.get("payload", {})
            if item["type"] == "memory_item" and isinstance(payload, dict):
                score += float(payload.get("salience", 0))
            if item["type"] == "memory_category" and isinstance(payload, dict):
                score += float(payload.get("salience", 0))
            if score:
                scored.append({**item, "score": score})
        scored.sort(key=lambda item: (item["score"], item.get("id", "")), reverse=True)
        return scored[:limit]

    def needs_retrieval(self, query: str) -> bool:
        query = str(query or "")
        if len(query) >= 12:
            return True
        return self._has_any(query, ["之前", "上次", "最近", "历史", "记忆", "进度", "任务", "承诺", "复盘"])

    def build_retrieval_plan(self, query: str, results: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        results = results or []
        needs = self.needs_retrieval(query)
        preferred = self._preferred_types(query)
        top_score = max([float(item.get("score", 0)) for item in results] or [0])
        hit_types = sorted({item.get("type", "") for item in results if item.get("type")})
        sufficiency = "enough" if results and top_score >= 2 else "more"
        if not needs:
            sufficiency = "no_retrieve"
        return {
            "needs_retrieval": needs,
            "preferred_types": preferred,
            "query_terms": self._terms(query)[:12],
            "hit_count": len(results),
            "hit_types": hit_types,
            "top_score": top_score,
            "sufficiency": sufficiency,
            "reason": self._retrieval_reason(query, needs, results),
        }

    def format_retrieval_plan(self, plan: Dict[str, Any]) -> str:
        if not plan:
            return "暂无检索计划。"
        return "\n".join([
            "以下是记忆检索计划。它用于解释本轮为什么注入或不注入历史。",
            f"needs_retrieval: {plan.get('needs_retrieval')}",
            f"preferred_types: {', '.join(plan.get('preferred_types', [])) or 'none'}",
            f"hit_count: {plan.get('hit_count', 0)}",
            f"sufficiency: {plan.get('sufficiency', 'unknown')}",
            f"reason: {plan.get('reason', '')}",
        ])

    def format_for_context(self, results: List[Dict[str, Any]]) -> str:
        if not results:
            return "暂无与当前输入直接相关的历史检索结果。"

        lines = ["以下是与当前输入相关的历史记忆。请只在相关时引用。"]
        for index, item in enumerate(results, start=1):
            score = item.get("score", "")
            score_text = f" score={score}" if score != "" else ""
            lines.append(f"{index}. [{item['type']}{score_text}] {self._compact(item['text'], 220)}")
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

    def _preferred_types(self, query: str) -> List[str]:
        query = str(query or "")
        if self._has_any(query, ["承诺", "答应", "说好"]):
            return ["commitment", "memory_item", "memory_category"]
        if self._has_any(query, ["任务", "进度", "完成", "卡住", "阻塞", "下一步"]):
            return ["memory_category", "memory_item", "record", "daily_summary"]
        if self._has_any(query, ["画像", "偏好", "风格"]):
            return ["user_profile", "memory_category", "memory_item"]
        if self._has_any(query, ["来源", "原文", "记录", "哪次"]):
            return ["memory_resource", "record", "memory_item"]
        return ["memory_category", "memory_item"]

    def _retrieval_reason(self, query: str, needs: bool, results: List[Dict[str, Any]]) -> str:
        if not needs:
            return "当前输入较短或不涉及历史、任务、承诺、复盘等记忆触发词。"
        if not results:
            return "当前输入需要历史判断，但没有召回到直接相关结果。"
        top = results[0]
        return f"已召回 {len(results)} 条结果，最高相关类型为 {top.get('type', '')}。"

    def _has_any(self, text: str, keywords: List[str]) -> bool:
        return any(keyword in text for keyword in keywords)

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
