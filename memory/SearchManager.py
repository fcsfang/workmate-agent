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
        semantic_dialogues: Optional[List[Dict[str, Any]]] = None,
        insights: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        #把所有类型的记忆（对话记录、日摘、用户画像、承诺、知识点…）全部转换成统一格式：
        #python
        #{
        #    "type": "memory_item",       # 这条记忆是什么类型
        #    "id":   "item-xxx",
        #    "text": "简历 优化 AI实习 ...",  # 把内容拍平成一个大字符串
        #    "terms": ["简历", "优化", "ai实习"],  # 分词后的词列表
        #    "payload": { ...原始数据... }
        #}
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
            if memory_item.get("status") == "archived":
                continue
            text = self._sanitize_text(" ".join([
                memory_item.get("type", ""),
                memory_item.get("category", ""),
                memory_item.get("status", ""),
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

        for dialogue in semantic_dialogues or []:
            text = self._sanitize_text(" ".join([
                dialogue.get("time", ""),
                dialogue.get("task_title", ""),
                dialogue.get("user_intent", ""),
                dialogue.get("semantic_summary", ""),
                json.dumps(dialogue.get("key_points", []), ensure_ascii=False),
            ]))
            items.append(self._item("semantic_dialogue", dialogue.get("id", ""), text, dialogue))

        for insight in insights or []:
            if insight.get("status") not in {"active", ""}:
                continue
            text = self._sanitize_text(" ".join([
                insight.get("type", ""),
                insight.get("content", ""),
                insight.get("why_it_matters", ""),
                insight.get("suggested_intervention", ""),
            ]))
            items.append(self._item("high_level_insight", insight.get("id", ""), text, insight))

        self.save_index(items)
        return items

    def search(
        self,
        query: str,
        records: Optional[List[Dict[str, Any]]] = None,
        daily_summaries: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        commitments: Optional[List[Dict[str, Any]]] = None,
        memory_items: Optional[List[Dict[str, Any]]] = None,
        memory_categories: Optional[List[Dict[str, Any]]] = None,
        memory_resources: Optional[List[Dict[str, Any]]] = None,
        semantic_dialogues: Optional[List[Dict[str, Any]]] = None,
        insights: Optional[List[Dict[str, Any]]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if not self.needs_retrieval(query):
            return []

        items = self.load_index()
        if not items and self._has_source_data(
            records,
            daily_summaries,
            user_profile,
            commitments,
            memory_items,
            memory_categories,
            memory_resources,
            semantic_dialogues,
            insights,
        ):
            items = self.build_index(
                records or [],
                daily_summaries,
                user_profile,
                commitments,
                memory_items,
                memory_categories,
                memory_resources,
                semantic_dialogues,
                insights,
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
            if item["type"] == "memory_item":
                score += float(item.get("salience", 0))
                if item.get("status") == "stale":
                    score -= 0.8
            if item["type"] == "memory_category":
                score += float(item.get("salience", 0))
            if item["type"] == "high_level_insight":
                score += 1 + float(item.get("confidence", 0))
            if item["type"] == "semantic_dialogue":
                score += 0.5
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

    def load_index(self) -> List[Dict[str, Any]]:
        if not self.index_path.exists() or self.index_path.stat().st_size == 0:
            return []
        try:
            with self.index_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in (self._normalize_index_item(item) for item in data) if item]

    def _item(self, item_type: str, item_id: str, text: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": item_type,
            "id": item_id,
            "text": self._compact(text, 500),
            "terms": self._terms(text),
            "salience": float(payload.get("salience", 0)) if isinstance(payload, dict) else 0,
            "confidence": float(payload.get("confidence", 0)) if isinstance(payload, dict) else 0,
            "status": payload.get("status", "") if isinstance(payload, dict) else "",
            "updated_at": payload.get("updated_at", "") if isinstance(payload, dict) else "",
            "payload": payload,
        }

    def _normalize_index_item(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict) or not item.get("type"):
            return {}
        text = self._compact(item.get("text", ""), 500)
        if not text:
            return {}
        terms = item.get("terms")
        if not isinstance(terms, list):
            terms = self._terms(text)
        return {
            "type": item.get("type", ""),
            "id": item.get("id", ""),
            "text": text,
            "terms": [str(term) for term in terms],
            "salience": float(item.get("salience", 0)),
            "confidence": float(item.get("confidence", 0)),
            "status": item.get("status", ""),
            "updated_at": item.get("updated_at", ""),
        }

    def _has_source_data(self, *values: Any) -> bool:
        for value in values:
            if isinstance(value, list) and value:
                return True
            if isinstance(value, dict) and any(value.values()):
                return True
        return False

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
            return ["high_level_insight", "commitment", "semantic_dialogue", "memory_item", "memory_category"]
        if self._has_any(query, ["任务", "进度", "完成", "卡住", "阻塞", "下一步"]):
            return ["high_level_insight", "semantic_dialogue", "memory_category", "memory_item", "daily_summary"]
        if self._has_any(query, ["画像", "偏好", "风格"]):
            return ["high_level_insight", "user_profile", "memory_category", "memory_item"]
        if self._has_any(query, ["来源", "原文", "记录", "哪次"]):
            return ["semantic_dialogue", "memory_resource", "record", "memory_item"]
        if self._has_any(query, ["复盘", "反省", "洞察", "模式"]):
            return ["high_level_insight", "semantic_dialogue", "memory_category"]
        return ["high_level_insight", "semantic_dialogue", "memory_category", "memory_item"]

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
            line = self._soften_pressure_text(line)
            lines.append(line)
        return "\n".join(lines)

    def _soften_pressure_text(self, text: str) -> str:
        replacements = {
            "强制用户": "可以轻量提醒用户",
            "直接指出问题": "温和指出一个可能风险",
            "直接指出": "温和指出",
            "强调真实产出": "关注核心事项和实际进展",
            "监督用户": "轻量提醒用户",
            "监督方式": "轻量提醒方式",
            "质疑": "提出一个问题",
            "催促": "轻轻提醒",
            "不要委婉": "保持温和直接",
        }
        softened = str(text or "")
        for old, new in replacements.items():
            softened = softened.replace(old, new)
        return softened
