import math
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


class MemoryRetriever:
    TYPE_WEIGHTS = {
        "high_level_insight": 1.35,
        "behavior_pattern": 1.25,
        "task": 1.22,
        "commitment": 1.18,
        "memory_item": 1.12,
        "memory_category": 1.08,
        "semantic_dialogue": 1.04,
        "daily_summary": 1.0,
        "record": 0.95,
        "memory_resource": 0.92,
        "user_profile": 0.9,
    }

    def __init__(
        self,
        embedding_client: Optional[Any] = None,
        vector_enabled: Optional[bool] = None,
        reranker: Optional[Any] = None,
    ):
        self.embedding_client = embedding_client
        self.vector_enabled = self._vector_enabled(vector_enabled)
        self.reranker = reranker

    def search(
        self,
        query: str,
        items: List[Dict[str, Any]],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        query_terms = self._terms(query)
        if not query_terms:
            return []
        preferred_types = self.preferred_types(query)
        query_embedding = self._embed(query)
        scored = []
        for item in items:
            if not self.matches_filters(item, filters or {}):
                continue
            keyword_score = self.keyword_score(query_terms, item.get("terms", []))
            vector_score = self.vector_score(query_embedding, item.get("embedding"))
            recency_score = self.recency_score(item.get("updated_at") or item.get("time"))
            type_weight = self.type_weight(item.get("type", ""), preferred_types)
            salience_score = self.salience_score(item)
            task_relevance_score = self.task_relevance_score(query_terms, item)
            status_penalty = self.status_penalty(item)
            raw_score = (
                keyword_score * 0.4
                + recency_score * 0.14
                + salience_score * 0.16
                + vector_score * 0.2
                + task_relevance_score * 0.1
            )
            score = max(0.0, raw_score * type_weight + status_penalty)
            if score <= 0:
                continue
            reason = self.reason(item, keyword_score, recency_score, salience_score, vector_score, task_relevance_score, type_weight)
            scored.append({
                **item,
                "source_type": item.get("type", ""),
                "source_id": item.get("id", ""),
                "score": round(score, 4),
                "reason": reason,
                "source_attribution": self.source_attribution(item),
                "score_breakdown": {
                    "keyword": round(keyword_score, 4),
                    "recency": round(recency_score, 4),
                    "salience": round(salience_score, 4),
                    "type_weight": round(type_weight, 4),
                    "vector": round(vector_score, 4),
                    "task_relevance": round(task_relevance_score, 4),
                    "status_penalty": round(status_penalty, 4),
                },
            })
        return self.rerank(query, scored, limit)

    def build_plan(
        self,
        query: str,
        results: Optional[List[Dict[str, Any]]] = None,
        needs_retrieval: bool = True,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        results = results or []
        top_score = max([float(item.get("score", 0)) for item in results] or [0])
        hit_types = sorted({item.get("source_type") or item.get("type", "") for item in results if item.get("source_type") or item.get("type")})
        return {
            "needs_retrieval": needs_retrieval,
            "mode": "hybrid",
            "vector_enabled": self.vector_enabled,
            "vector_status": "enabled" if self.vector_enabled else "disabled",
            "preferred_types": self.preferred_types(query),
            "filters": filters or {},
            "query_terms": self._terms(query)[:12],
            "hit_count": len(results),
            "hit_types": hit_types,
            "top_score": round(top_score, 4),
            "sufficiency": self.sufficiency(needs_retrieval, top_score, results),
            "top_results": [
                {
                    "source_type": item.get("source_type") or item.get("type", ""),
                    "source_id": item.get("source_id") or item.get("id", ""),
                    "score": item.get("score", 0),
                    "reason": item.get("reason", ""),
                    "score_breakdown": item.get("score_breakdown", {}),
                    "source_attribution": item.get("source_attribution", self.source_attribution(item)),
                    "text": self._compact(item.get("text", ""), 160),
                }
                for item in results[:5]
            ],
            "reason": self.retrieval_reason(needs_retrieval, results),
        }

    def keyword_score(self, query_terms: List[str], item_terms: List[str]) -> float:
        if not query_terms or not item_terms:
            return 0.0
        item_term_set = set(str(term).lower() for term in item_terms)
        matched = [term for term in query_terms if term in item_term_set]
        coverage = len(set(matched)) / max(len(set(query_terms)), 1)
        frequency = sum(str(term).lower() in item_term_set for term in query_terms) / max(len(query_terms), 1)
        return min(1.0, coverage * 0.75 + frequency * 0.25)

    def recency_score(self, value: Any) -> float:
        if not value:
            return 0.0
        try:
            updated = datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return 0.0
        age_days = max(0, (datetime.now() - updated).days)
        return round(math.exp(-age_days / 45), 4)

    def type_weight(self, item_type: str, preferred_types: List[str]) -> float:
        base = self.TYPE_WEIGHTS.get(item_type, 1.0)
        if item_type in preferred_types:
            base += 0.18
        return base

    def salience_score(self, item: Dict[str, Any]) -> float:
        salience = self._float(item.get("salience"), 0)
        confidence = self._float(item.get("confidence"), 0)
        importance = self._float(item.get("importance"), 0)
        return max(0.0, min(1.0, salience * 0.55 + confidence * 0.25 + importance * 0.2))

    def task_relevance_score(self, query_terms: List[str], item: Dict[str, Any]) -> float:
        item_type = str(item.get("type", ""))
        payload = item.get("payload", {}) if isinstance(item.get("payload", {}), dict) else {}
        task_text = " ".join([
            item.get("task_id", ""),
            item.get("task_title", ""),
            payload.get("task_id", ""),
            payload.get("task_title", ""),
            payload.get("title", ""),
        ]).lower()
        if item_type == "task":
            base = 0.45
        elif item.get("task_id") or item.get("task_title") or payload.get("task_id"):
            base = 0.25
        else:
            base = 0.0
        if not query_terms or not task_text:
            return base
        matched = sum(1 for term in set(query_terms) if term and term in task_text)
        coverage = matched / max(len(set(query_terms)), 1)
        return max(0.0, min(1.0, base + coverage * 0.55))

    def status_penalty(self, item: Dict[str, Any]) -> float:
        status = item.get("status", "")
        if status in {"archived", "resolved", "abandoned"}:
            return -0.35
        if status == "stale":
            return -0.22
        return 0.0

    def matches_filters(self, item: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        if not filters:
            return True
        type_filter = filters.get("types") or filters.get("memory_types")
        if type_filter:
            allowed = {str(value) for value in self._list(type_filter)}
            if str(item.get("type", "")) not in allowed:
                return False
        status_filter = filters.get("statuses")
        if status_filter:
            allowed = {str(value) for value in self._list(status_filter)}
            if str(item.get("status", "")) not in allowed:
                return False
        task_id = str(filters.get("task_id", "") or "")
        if task_id:
            payload = item.get("payload", {}) if isinstance(item.get("payload", {}), dict) else {}
            if str(item.get("task_id", "") or payload.get("task_id", "")) != task_id:
                return False
        min_salience = filters.get("min_salience")
        if min_salience is not None and self._float(item.get("salience"), 0) < self._float(min_salience, 0):
            return False
        updated_after = filters.get("updated_after")
        if updated_after and not self._updated_after(item.get("updated_at") or item.get("time"), updated_after):
            return False
        return True

    def source_attribution(self, item: Dict[str, Any]) -> Dict[str, Any]:
        payload = item.get("payload", {}) if isinstance(item.get("payload", {}), dict) else {}
        return {
            "source_type": item.get("source_type") or item.get("type", ""),
            "source_id": item.get("source_id") or item.get("id", ""),
            "status": item.get("status", ""),
            "updated_at": item.get("updated_at") or item.get("time", ""),
            "task_id": item.get("task_id") or payload.get("task_id", ""),
            "task_title": item.get("task_title") or payload.get("task_title", "") or payload.get("title", ""),
            "record_id": payload.get("record_id", "") or item.get("record_id", ""),
            "confidence": item.get("confidence", 0),
            "salience": item.get("salience", 0),
        }

    def vector_score(self, query_embedding: Optional[List[float]], item_embedding: Any) -> float:
        if not query_embedding or not isinstance(item_embedding, list):
            return 0.0
        pairs = [(self._float(left, 0), self._float(right, 0)) for left, right in zip(query_embedding, item_embedding)]
        if not pairs:
            return 0.0
        dot = sum(left * right for left, right in pairs)
        left_norm = math.sqrt(sum(left * left for left, _ in pairs))
        right_norm = math.sqrt(sum(right * right for _, right in pairs))
        if not left_norm or not right_norm:
            return 0.0
        return max(0.0, min(1.0, dot / (left_norm * right_norm)))

    def reason(
        self,
        item: Dict[str, Any],
        keyword_score: float,
        recency_score: float,
        salience_score: float,
        vector_score: float,
        task_relevance_score: float,
        type_weight: float,
    ) -> str:
        parts = []
        if keyword_score > 0:
            parts.append(f"关键词匹配 {keyword_score:.2f}")
        if recency_score >= 0.5:
            parts.append("近期更新")
        if salience_score >= 0.35:
            parts.append("重要性较高")
        if vector_score > 0:
            parts.append(f"向量相似 {vector_score:.2f}")
        if task_relevance_score >= 0.25:
            parts.append(f"任务相关 {task_relevance_score:.2f}")
        if type_weight > 1.15:
            parts.append(f"类型优先 {item.get('type', '')}")
        return "；".join(parts) or "综合评分召回"

    def rerank(self, query: str, scored: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        if self.reranker:
            rerank = getattr(self.reranker, "rerank", None)
            try:
                if callable(rerank):
                    reranked = rerank(query=query, results=scored, limit=limit)
                elif callable(self.reranker):
                    reranked = self.reranker(query, scored, limit)
                else:
                    reranked = None
                if isinstance(reranked, list):
                    return reranked[:limit]
            except Exception:
                pass
        scored.sort(key=lambda item: (float(item.get("score", 0)), item.get("updated_at", ""), item.get("id", "")), reverse=True)
        return scored[:limit]

    def preferred_types(self, query: str) -> List[str]:
        query = str(query or "")
        if self._has_any(query, ["承诺", "答应", "说好"]):
            return ["semantic_dialogue", "memory_item", "daily_summary", "record"]
        if self._has_any(query, ["任务", "进度", "完成", "卡住", "阻塞", "下一步"]):
            return ["semantic_dialogue", "memory_item", "memory_category", "daily_summary", "record"]
        if self._has_any(query, ["画像", "偏好", "风格"]):
            return ["semantic_dialogue", "memory_category", "record"]
        if self._has_any(query, ["来源", "原文", "记录", "哪次"]):
            return ["record", "memory_resource", "semantic_dialogue", "memory_item"]
        if self._has_any(query, ["复盘", "反省", "洞察", "模式"]):
            return ["semantic_dialogue", "memory_category", "daily_summary", "record"]
        return ["semantic_dialogue", "memory_item", "memory_category", "daily_summary", "record"]

    def sufficiency(self, needs_retrieval: bool, top_score: float, results: List[Dict[str, Any]]) -> str:
        if not needs_retrieval:
            return "no_retrieve"
        if not results:
            return "none"
        if top_score >= 0.75 or len(results) >= 3:
            return "enough"
        return "weak"

    def retrieval_reason(self, needs: bool, results: List[Dict[str, Any]]) -> str:
        if not needs:
            return "当前输入不需要长期记忆检索。"
        if not results:
            return "当前输入需要历史判断，但没有召回到相关记忆。"
        top = results[0]
        return f"已召回 {len(results)} 条记忆，最高结果来自 {top.get('source_type') or top.get('type', '')}，原因：{top.get('reason', '')}"

    def _embed(self, text: str) -> Optional[List[float]]:
        if not self.vector_enabled or not self.embedding_client:
            return None
        embed = getattr(self.embedding_client, "embed", None)
        if not callable(embed):
            return None
        try:
            vector = embed(text)
        except Exception:
            return None
        return vector if isinstance(vector, list) else None

    def _vector_enabled(self, configured: Optional[bool]) -> bool:
        if configured is not None:
            return configured
        env_val = os.getenv("WORKMATE_VECTOR_RETRIEVAL", "").lower() in {"1", "true", "yes", "on"}
        if not env_val:
            return False
        if not self.embedding_client or self.embedding_client.__class__.__name__ == "NullEmbeddingClient":
            return False
        return True

    def _terms(self, text: str) -> List[str]:
        text = str(text)
        separators = " \n\t\r，。！？、；;:：/\\|+-_*()（）[]【】{}<>\"'"
        normalized = text
        for separator in separators:
            normalized = normalized.replace(separator, " ")
        terms = [part.strip().lower() for part in normalized.split() if len(part.strip()) >= 2]
        chinese_keywords = [
            "拖延", "分心", "走神", "总结", "复盘", "实习", "大模型",
            "任务", "进度", "完成", "阻塞", "下一步", "生命周期", "高频词", "jd", "agent",
            "承诺", "专注", "提醒", "模式", "画像", "偏好", "记忆",
        ]
        lowered = text.lower()
        for keyword in chinese_keywords:
            if keyword.lower() in lowered:
                terms.append(keyword.lower())
        return terms

    def _has_any(self, text: str, keywords: List[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _list(self, value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, tuple) or isinstance(value, set):
            return list(value)
        return [value]

    def _updated_after(self, value: Any, threshold: Any) -> bool:
        if not value:
            return False
        try:
            left = datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
            right = datetime.fromisoformat(str(threshold).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return False
        return left >= right

    def _compact(self, text: str, max_length: int) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
