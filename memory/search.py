import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import memory_data_path
from .retriever import MemoryRetriever


class SearchManager:
    AUTHORITATIVE_SOURCE_TYPES = {
        "user_profile",
        "commitment",
        "task",
        "high_level_insight",
        "behavior_pattern",
    }
    AUTHORITATIVE_MEMORY_ITEM_TYPES = {
        "task",
        "subtask",
        "commitment",
        "profile",
        "pattern",
        "supervision",
    }
    EPISODIC_SOURCE_TYPES = {
        "record",
        "daily_summary",
        "memory_item",
        "memory_category",
        "memory_resource",
        "semantic_dialogue",
    }

    def __init__(
        self,
        index_path: Optional[str] = None,
        retriever: Optional[MemoryRetriever] = None,
        embedding_client: Optional[Any] = None,
    ):
        self.index_path = Path(index_path) if index_path else memory_data_path("retrieval_index.json")
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backward compatible directory path for ChromaDB
        if index_path:
            p = Path(index_path)
            if p.is_dir():
                self.db_path = p
            else:
                self.db_path = p.parent / "chroma"
        else:
            self.db_path = memory_data_path("chroma")

        self.chroma_enabled = False
        try:
            import chromadb
            self.db_path.mkdir(parents=True, exist_ok=True)
            self.chroma_client = chromadb.PersistentClient(path=str(self.db_path))
            self.collection = self.chroma_client.get_or_create_collection(
                name="workmate_memories",
                metadata={"hnsw:space": "cosine"}
            )
            self.chroma_enabled = True
        except ImportError:
            pass

        if not retriever:
            if not embedding_client:
                try:
                    from .embeddings import get_embedding_client
                    embedding_client = get_embedding_client()
                except ImportError:
                    pass
            self.retriever = MemoryRetriever(embedding_client=embedding_client)
        else:
            self.retriever = retriever

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
        tasks: Optional[List[Dict[str, Any]]] = None,
        behavior_patterns: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        # Load the existing index first to build an incremental cache
        existing_items = {}
        if self.chroma_enabled:
            try:
                existing = self.collection.get(include=["documents", "embeddings", "metadatas"])
                ids = existing.get("ids", [])
                documents = existing.get("documents", [])
                embeddings = existing.get("embeddings")
                if embeddings is None:
                    embeddings = []
                metadatas = existing.get("metadatas")
                if metadatas is None:
                    metadatas = []
                for i_id, doc, emb, meta in zip(ids, documents, embeddings, metadatas):
                    item_type = meta.get("type", "") if meta else ""
                    emb_list = None
                    if emb is not None:
                        if hasattr(emb, "tolist"):
                            emb_list = emb.tolist()
                        else:
                            emb_list = list(emb)
                    existing_items[(item_type, i_id)] = (doc, emb_list)
            except Exception as e:
                print(f"[SearchManager] Error loading cache from ChromaDB: {e}")
        else:
            try:
                old_items = self.load_index()
                for item in old_items:
                    if item.get("type") and item.get("id"):
                        existing_items[(item.get("type"), item.get("id"))] = (item.get("text"), item.get("embedding"))
            except Exception:
                pass

        # Helper function to compute or retrieve cached embeddings
        def get_embedding(item_type: str, item_id: str, text_content: str) -> Optional[List[float]]:
            if not self.retriever.vector_enabled:
                return None
            compacted = self._compact(text_content, 500)
            cached_text, cached_embed = existing_items.get((item_type, item_id), (None, None))
            if cached_embed is not None and cached_text == compacted:
                return cached_embed
            return self.retriever._embed(text_content)

        items = []
        for index, record in enumerate(records[-120:]):
            text = " ".join([
                record.get("id", ""),
                record.get("time", ""),
                record.get("user", ""),
                self._sanitize_text(record.get("assistant", "")),
                json.dumps(record.get("extracted", {}), ensure_ascii=False),
            ])
            r_id = f"record-{index}"
            emb = get_embedding("record", r_id, text)
            items.append(self._item("record", r_id, text, record, embedding=emb))

        for summary in daily_summaries or []:
            text = self._sanitize_text(json.dumps(summary, ensure_ascii=False))
            s_id = summary.get("date", "")
            emb = get_embedding("daily_summary", s_id, text)
            items.append(self._item("daily_summary", s_id, text, summary, embedding=emb))

        for memory_item in memory_items or []:
            if (
                memory_item.get("status") == "archived"
                or memory_item.get("type") in self.AUTHORITATIVE_MEMORY_ITEM_TYPES
            ):
                continue
            text = self._sanitize_text(" ".join([
                memory_item.get("type", ""),
                memory_item.get("category", ""),
                memory_item.get("status", ""),
                memory_item.get("content", ""),
                memory_item.get("task_title", ""),
                json.dumps(memory_item.get("metadata", {}), ensure_ascii=False),
            ]))
            m_id = memory_item.get("id", "")
            emb = get_embedding("memory_item", m_id, text)
            items.append(self._item("memory_item", m_id, text, memory_item, embedding=emb))

        for category in memory_categories or []:
            text = self._sanitize_text(" ".join([
                category.get("name", ""),
                category.get("description", ""),
                category.get("summary", ""),
                json.dumps(category.get("type_counts", {}), ensure_ascii=False),
            ]))
            cat_id = category.get("id", "")
            emb = get_embedding("memory_category", cat_id, text)
            items.append(self._item("memory_category", cat_id, text, category, embedding=emb))

        for resource in memory_resources or []:
            text = self._sanitize_text(" ".join([
                resource.get("record_id", ""),
                resource.get("time", ""),
                resource.get("user_preview", ""),
                resource.get("assistant_preview", ""),
                resource.get("task_title", ""),
                json.dumps(resource.get("extracted_categories", []), ensure_ascii=False),
            ]))
            res_id = resource.get("id", "")
            emb = get_embedding("memory_resource", res_id, text)
            items.append(self._item("memory_resource", res_id, text, resource, embedding=emb))

        for dialogue in semantic_dialogues or []:
            text = self._sanitize_text(" ".join([
                dialogue.get("time", ""),
                dialogue.get("task_title", ""),
                dialogue.get("user_intent", ""),
                dialogue.get("semantic_summary", ""),
                json.dumps(dialogue.get("key_points", []), ensure_ascii=False),
            ]))
            d_id = dialogue.get("id", "")
            emb = get_embedding("semantic_dialogue", d_id, text)
            items.append(self._item("semantic_dialogue", d_id, text, dialogue, embedding=emb))

        if self.chroma_enabled:
            try:
                existing = self.collection.get(include=["documents", "metadatas", "embeddings"])
                existing_ids = existing.get("ids", []) if existing else []
                existing_documents = existing.get("documents", []) if existing else []
                existing_metadatas = existing.get("metadatas", []) if existing else []
                existing_embeddings = existing.get("embeddings") if existing else []
                if existing_embeddings is None:
                    existing_embeddings = []
                existing_by_id = {
                    item_id: {
                        "document": existing_documents[index] if index < len(existing_documents) else "",
                        "metadata": existing_metadatas[index] if index < len(existing_metadatas) else {},
                        "embedding": existing_embeddings[index] if index < len(existing_embeddings) else None,
                    }
                    for index, item_id in enumerate(existing_ids)
                }

                current_ids = {item["id"] for item in items}
                ids_to_delete = [item_id for item_id in existing_ids if item_id not in current_ids]
                if ids_to_delete:
                    self.collection.delete(ids=ids_to_delete)

                ids_to_upsert = []
                documents_to_upsert = []
                metadatas_to_upsert = []
                embeddings_to_upsert = []
                for item in items:
                    metadata = self._chroma_metadata(item)
                    embedding = item.get("embedding") if item.get("embedding") is not None else [0.0]
                    existing_item = existing_by_id.get(item["id"], {})
                    if (
                        existing_item.get("document") == item["text"]
                        and existing_item.get("metadata") == metadata
                        and self._embedding_equal(existing_item.get("embedding"), embedding)
                    ):
                        continue
                    ids_to_upsert.append(item["id"])
                    documents_to_upsert.append(item["text"])
                    metadatas_to_upsert.append(metadata)
                    embeddings_to_upsert.append(embedding)

                if ids_to_upsert:
                    self.collection.upsert(
                        ids=ids_to_upsert,
                        embeddings=embeddings_to_upsert,
                        documents=documents_to_upsert,
                        metadatas=metadatas_to_upsert
                    )
            except Exception as e:
                print(f"[SearchManager] Failed to save to ChromaDB: {e}")
        else:
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
        tasks: Optional[List[Dict[str, Any]]] = None,
        behavior_patterns: Optional[List[Dict[str, Any]]] = None,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
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
            tasks,
            behavior_patterns,
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
                tasks,
                behavior_patterns,
            )
        return self.retriever.search(query, items, limit=limit, filters=filters)

    def needs_retrieval(self, query: str) -> bool:
        query = str(query or "")
        if len(query) >= 12:
            return True
        return self._has_any(query, ["之前", "上次", "最近", "历史", "记忆", "进度", "任务", "承诺", "复盘"])

    def build_retrieval_plan(
        self,
        query: str,
        results: Optional[List[Dict[str, Any]]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        results = results or []
        needs = self.needs_retrieval(query)
        plan = self.retriever.build_plan(query, results, needs_retrieval=needs, filters=filters)
        plan["source_policy"] = self.source_policy()
        return plan

    def source_policy(self) -> Dict[str, Any]:
        return {
            "mode": "episodic_only",
            "indexed_types": sorted(self.EPISODIC_SOURCE_TYPES),
            "direct_context_types": sorted(self.AUTHORITATIVE_SOURCE_TYPES),
            "principle": "RAG may recall history but cannot override current execution state.",
        }

    def format_retrieval_plan(self, plan: Dict[str, Any]) -> str:
        if not plan:
            return "暂无检索计划。"
        return "\n".join([
            "以下是记忆检索计划。它用于解释本轮为什么注入或不注入历史。",
            f"needs_retrieval: {plan.get('needs_retrieval')}",
            f"mode: {plan.get('mode', 'keyword')}",
            f"vector_status: {plan.get('vector_status', 'disabled')}",
            f"preferred_types: {', '.join(plan.get('preferred_types', [])) or 'none'}",
            f"filters: {json.dumps(plan.get('filters', {}), ensure_ascii=False)}",
            f"hit_count: {plan.get('hit_count', 0)}",
            f"sufficiency: {plan.get('sufficiency', 'unknown')}",
            f"source_policy: {json.dumps(plan.get('source_policy', self.source_policy()), ensure_ascii=False)}",
            f"reason: {plan.get('reason', '')}",
            "top_results:",
            *[
                (
                    f"- [{item.get('source_type', '')}] {item.get('source_id', '')} "
                    f"score={item.get('score', 0)} reason={item.get('reason', '')} "
                    f"citation={self._format_attribution(item.get('source_attribution', {}))}"
                )
                for item in plan.get("top_results", [])[:5]
            ],
        ])

    def format_for_context(self, results: List[Dict[str, Any]]) -> str:
        if not results:
            return "暂无与当前输入直接相关的历史检索结果。"

        lines = ["以下是与当前输入相关的历史记忆。请只在相关时引用。"]
        for index, item in enumerate(results, start=1):
            score = item.get("score", "")
            score_text = f" score={score}" if score != "" else ""
            reason = item.get("reason", "")
            reason_text = f" reason={reason}" if reason else ""
            item_type = item.get("source_type") or item.get("type", "")
            attribution = item.get("source_attribution", {})
            attribution_text = ""
            if isinstance(attribution, dict):
                source_id = attribution.get("source_id", "")
                task_title = attribution.get("task_title", "")
                attribution_text = f" source={source_id}" if source_id else ""
                if task_title:
                    attribution_text += f" task={task_title}"
            lines.append(f"{index}. [{item_type}{score_text}{reason_text}{attribution_text}] {self._compact(item['text'], 220)}")
        return "\n".join(lines)

    def _format_attribution(self, attribution: Dict[str, Any]) -> str:
        if not isinstance(attribution, dict):
            return ""
        parts = []
        if attribution.get("source_id"):
            parts.append(f"source:{attribution.get('source_id')}")
        if attribution.get("task_title"):
            parts.append(f"task:{attribution.get('task_title')}")
        if attribution.get("record_id"):
            parts.append(f"record:{attribution.get('record_id')}")
        return "|".join(parts)

    def save_index(self, items: List[Dict[str, Any]]) -> None:
        serializable = [{key: value for key, value in item.items() if key != "payload"} for item in items]
        with self.index_path.open("w", encoding="utf-8") as file:
            json.dump(serializable, file, ensure_ascii=False, indent=2)

    def load_index(self) -> List[Dict[str, Any]]:
        if self.chroma_enabled:
            try:
                existing = self.collection.get(include=["documents", "embeddings", "metadatas"])
                ids = existing.get("ids", [])
                documents = existing.get("documents", [])
                embeddings = existing.get("embeddings")
                if embeddings is None:
                    embeddings = []
                metadatas = existing.get("metadatas")
                if metadatas is None:
                    metadatas = []
                
                items = []
                for i_id, doc, emb, meta in zip(ids, documents, embeddings, metadatas):
                    emb_list = None
                    if emb is not None and len(emb) > 1:
                        if hasattr(emb, "tolist"):
                            emb_list = emb.tolist()
                        else:
                            emb_list = list(emb)
                    item = {
                        "id": i_id,
                        "text": doc,
                        "type": meta.get("type", "") if meta else "",
                        "salience": float(meta.get("salience", 0.0)) if meta else 0.0,
                        "confidence": float(meta.get("confidence", 0.0)) if meta else 0.0,
                        "importance": float(meta.get("importance", 0.0)) if meta else 0.0,
                        "status": meta.get("status", "") if meta else "",
                        "updated_at": meta.get("updated_at", "") if meta else "",
                        "task_id": meta.get("task_id", "") if meta else "",
                        "task_title": meta.get("task_title", "") if meta else "",
                        "record_id": meta.get("record_id", "") if meta else "",
                        "embedding": emb_list
                    }
                    normalized = self._normalize_index_item(item)
                    if normalized and self._is_allowed_index_item(normalized):
                        items.append(normalized)
                return items
            except Exception as e:
                print(f"[SearchManager] Failed to load index from ChromaDB: {e}")
                return []

        if not self.index_path.exists() or self.index_path.stat().st_size == 0:
            return []
        try:
            with self.index_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [
            item
            for item in (self._normalize_index_item(item) for item in data)
            if item and self._is_allowed_index_item(item)
        ]

    def _is_allowed_index_item(self, item: Dict[str, Any]) -> bool:
        item_type = item.get("type", "")
        if item_type not in self.EPISODIC_SOURCE_TYPES:
            return False
        if item_type == "memory_item":
            memory_kind = str(item.get("text", "")).split(" ", 1)[0].strip().lower()
            if memory_kind in self.AUTHORITATIVE_MEMORY_ITEM_TYPES:
                return False
        return True

    def _item(
        self,
        item_type: str,
        item_id: str,
        text: str,
        payload: Dict[str, Any],
        embedding: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        source = self._source_metadata(item_type, item_id, payload)
        item_dict = {
            "type": item_type,
            "id": item_id,
            "text": self._compact(text, 500),
            "terms": self._terms(text),
            "salience": float(payload.get("salience", 0)) if isinstance(payload, dict) else 0,
            "confidence": float(payload.get("confidence", 0)) if isinstance(payload, dict) else 0,
            "importance": float(payload.get("importance", 0)) if isinstance(payload, dict) else 0,
            "status": payload.get("status", "") if isinstance(payload, dict) else "",
            "updated_at": payload.get("updated_at", "") if isinstance(payload, dict) else "",
            **source,
            "payload": payload,
        }
        if embedding is not None:
            item_dict["embedding"] = embedding
        return item_dict

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
            "importance": float(item.get("importance", 0)),
            "status": item.get("status", ""),
            "updated_at": item.get("updated_at", ""),
            "task_id": item.get("task_id", ""),
            "task_title": item.get("task_title", ""),
            "record_id": item.get("record_id", ""),
            "embedding": item.get("embedding"),
        }

    def _source_metadata(self, item_type: str, item_id: str, payload: Dict[str, Any]) -> Dict[str, str]:
        if not isinstance(payload, dict):
            return {"task_id": "", "task_title": "", "record_id": ""}
        task_id = payload.get("task_id", "")
        task_title = payload.get("task_title", "") or payload.get("title", "")
        record_id = payload.get("record_id", "")
        if item_type == "record":
            record_id = payload.get("id", "") or item_id
        if item_type == "task":
            task_id = payload.get("id", "") or item_id
            task_title = payload.get("title", "")
        return {
            "task_id": str(task_id or ""),
            "task_title": str(task_title or ""),
            "record_id": str(record_id or ""),
        }

    def _chroma_metadata(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": item["type"],
            "salience": item.get("salience", 0.0),
            "confidence": item.get("confidence", 0.0),
            "importance": item.get("importance", 0.0),
            "status": item.get("status", ""),
            "updated_at": item.get("updated_at", ""),
            "task_id": item.get("task_id", ""),
            "task_title": item.get("task_title", ""),
            "record_id": item.get("record_id", ""),
        }

    def _embedding_equal(self, left: Any, right: Any) -> bool:
        if hasattr(left, "tolist"):
            left = left.tolist()
        if hasattr(right, "tolist"):
            right = right.tolist()
        if left is None:
            return right is None
        if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
            return False
        return all(abs(float(a) - float(b)) < 1e-9 for a, b in zip(left, right))

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
            "质疑": "必要时澄清一个关键信息",
            "催促": "轻轻提醒",
            "不要委婉": "保持温和直接",
        }
        softened = str(text or "")
        for old, new in replacements.items():
            softened = softened.replace(old, new)
        return softened
