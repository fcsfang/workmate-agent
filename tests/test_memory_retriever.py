import json
import unittest
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory

from memory import MemoryRetriever, SearchManager


class FakeChromaCollection:
    def __init__(self):
        self.store = {}
        self.deleted = []
        self.upserted = []

    def get(self, include=None):
        ids = list(self.store.keys())
        return {
            "ids": ids,
            "documents": [self.store[item_id]["document"] for item_id in ids],
            "metadatas": [self.store[item_id]["metadata"] for item_id in ids],
            "embeddings": [self.store[item_id]["embedding"] for item_id in ids],
        }

    def delete(self, ids):
        self.deleted.extend(ids)
        for item_id in ids:
            self.store.pop(item_id, None)

    def upsert(self, ids, embeddings, documents, metadatas):
        self.upserted.extend(ids)
        for index, item_id in enumerate(ids):
            self.store[item_id] = {
                "document": documents[index],
                "metadata": metadatas[index],
                "embedding": embeddings[index],
            }


class MemoryRetrieverTest(unittest.TestCase):
    def test_hybrid_scoring_prefers_relevant_task_memory(self):
        now = datetime.now().isoformat(timespec="seconds")
        old = (datetime.now() - timedelta(days=120)).isoformat(timespec="seconds")
        items = [
            {
                "type": "record",
                "id": "record-1",
                "text": "昨天闲聊了天气",
                "terms": ["天气", "闲聊"],
                "updated_at": now,
            },
            {
                "type": "task",
                "id": "task-1",
                "text": "Agent Runtime V1.5 记忆检索任务 进度 阻塞",
                "terms": ["agent", "runtime", "记忆", "检索", "任务", "进度", "阻塞"],
                "updated_at": now,
                "salience": 0.7,
                "confidence": 0.8,
                "status": "active",
            },
            {
                "type": "memory_item",
                "id": "item-1",
                "text": "很久以前的记忆检索想法",
                "terms": ["记忆", "检索", "想法"],
                "updated_at": old,
                "salience": 0.2,
            },
        ]

        retriever = MemoryRetriever(vector_enabled=False)
        results = retriever.search("现在任务进度和记忆检索有什么阻塞", items, limit=3)

        self.assertEqual(results[0]["source_type"], "task")
        self.assertEqual(results[0]["source_id"], "task-1")
        self.assertGreater(results[0]["score_breakdown"]["keyword"], 0)
        self.assertGreater(results[0]["score_breakdown"]["recency"], 0)
        self.assertGreater(results[0]["score_breakdown"]["task_relevance"], 0)
        self.assertIn("reason", results[0])
        self.assertEqual(results[0]["source_attribution"]["source_id"], "task-1")

    def test_retrieval_plan_exposes_vector_fallback_and_top_results(self):
        retriever = MemoryRetriever(vector_enabled=False)
        results = [
            {
                "source_type": "task",
                "source_id": "task-1",
                "score": 0.91,
                "reason": "关键词匹配",
                "score_breakdown": {"keyword": 1.0, "recency": 0.9},
                "source_attribution": {"source_type": "task", "source_id": "task-1", "task_title": "任务进度"},
                "text": "任务进度",
            }
        ]

        plan = retriever.build_plan("任务进度", results, needs_retrieval=True, filters={"types": ["task"]})

        self.assertEqual(plan["mode"], "hybrid")
        self.assertEqual(plan["vector_status"], "disabled")
        self.assertEqual(plan["filters"]["types"], ["task"])
        self.assertEqual(plan["top_results"][0]["source_id"], "task-1")
        self.assertEqual(plan["top_results"][0]["source_attribution"]["task_title"], "任务进度")
        self.assertEqual(plan["sufficiency"], "enough")

    def test_metadata_filters_limit_retrieval_scope(self):
        now = datetime.now().isoformat(timespec="seconds")
        items = [
            {
                "type": "task",
                "id": "task-active",
                "text": "记忆检索 任务 进度",
                "terms": ["记忆", "检索", "任务", "进度"],
                "status": "active",
                "task_id": "task-1",
                "task_title": "RAG 优化",
                "updated_at": now,
                "salience": 0.8,
            },
            {
                "type": "memory_item",
                "id": "item-old",
                "text": "记忆检索 旧想法",
                "terms": ["记忆", "检索", "旧想法"],
                "status": "stale",
                "updated_at": now,
                "salience": 0.4,
            },
        ]

        retriever = MemoryRetriever(vector_enabled=False)
        results = retriever.search(
            "记忆检索任务进度",
            items,
            limit=3,
            filters={"types": ["task"], "statuses": ["active"], "task_id": "task-1", "min_salience": 0.5},
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source_id"], "task-active")
        self.assertEqual(results[0]["source_attribution"]["task_title"], "RAG 优化")

    def test_custom_reranker_can_override_final_order(self):
        class ReverseReranker:
            def rerank(self, query, results, limit):
                return list(reversed(results))[:limit]

        now = datetime.now().isoformat(timespec="seconds")
        items = [
            {
                "type": "task",
                "id": "task-high",
                "text": "记忆检索 任务 进度 高分",
                "terms": ["记忆", "检索", "任务", "进度"],
                "updated_at": now,
                "salience": 0.9,
            },
            {
                "type": "memory_item",
                "id": "item-low",
                "text": "记忆检索 想法",
                "terms": ["记忆", "检索"],
                "updated_at": now,
                "salience": 0.2,
            },
        ]

        retriever = MemoryRetriever(vector_enabled=False, reranker=ReverseReranker())
        results = retriever.search("记忆检索任务进度", items, limit=2)

        self.assertEqual(results[0]["source_id"], "item-low")

    def test_search_manager_indexes_episodes_but_excludes_authoritative_state(self):
        with TemporaryDirectory() as tmpdir:
            search = SearchManager(
                index_path=f"{tmpdir}/retrieval_index.json",
                retriever=MemoryRetriever(vector_enabled=False),
            )
            index = search.build_index(
                records=[{
                    "id": "record-1",
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "user": "继续实现记忆边界",
                    "assistant": "已经记录这段经历",
                    "extracted": {},
                }],
                user_profile={"long_term_goal": "完成 Workmate Agent"},
                commitments=[{"id": "commit-1", "commitment": "完成测试", "status": "open"}],
                tasks=[
                    {
                        "id": "task-1",
                        "title": "完成 MemoryRetriever",
                        "status": "active",
                        "progress": "正在实现 hybrid scoring",
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                        "salience": 0.8,
                    }
                ],
                behavior_patterns=[
                    {
                        "id": "pattern-1",
                        "status": "active",
                        "title": "任务分散",
                        "summary": "多个任务同时推进",
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                        "salience": 0.5,
                    }
                ],
                insights=[{"id": "insight-1", "status": "active", "content": "适合单线推进"}],
            )

        indexed_types = {item["type"] for item in index}
        self.assertIn("record", indexed_types)
        self.assertTrue(indexed_types.isdisjoint(search.AUTHORITATIVE_SOURCE_TYPES))
        self.assertEqual(search.source_policy()["mode"], "episodic_only")

    def test_loading_legacy_index_filters_authoritative_entries(self):
        with TemporaryDirectory() as tmpdir:
            index_path = f"{tmpdir}/retrieval_index.json"
            with open(index_path, "w", encoding="utf-8") as file:
                json.dump([
                    {"type": "task", "id": "task-1", "text": "当前任务"},
                    {"type": "user_profile", "id": "profile-1", "text": "用户画像"},
                    {"type": "memory_item", "id": "item-profile", "text": "profile profile active 低压力"},
                    {"type": "semantic_dialogue", "id": "dialogue-1", "text": "历史讨论"},
                ], file, ensure_ascii=False)
            search = SearchManager(
                index_path=index_path,
                retriever=MemoryRetriever(vector_enabled=False),
            )
            search.chroma_enabled = False

            loaded = search.load_index()

        self.assertEqual([item["id"] for item in loaded], ["dialogue-1"])

    def test_chroma_sync_uses_incremental_upsert_and_delete(self):
        with TemporaryDirectory() as tmpdir:
            search = SearchManager(
                index_path=f"{tmpdir}/retrieval_index.json",
                retriever=MemoryRetriever(vector_enabled=False),
            )
            collection = FakeChromaCollection()
            search.chroma_enabled = True
            search.collection = collection

            record = {
                "id": "record-source-1",
                "time": datetime.now().isoformat(timespec="seconds"),
                "user": "完成增量索引",
                "assistant": "已记录",
                "extracted": {},
            }
            search.build_index(records=[record])
            first_upserts = list(collection.upserted)
            self.assertIn("record-0", first_upserts)

            collection.upserted = []
            search.build_index(records=[record])
            self.assertEqual(collection.upserted, [])

            search.build_index(records=[])
            self.assertIn("record-0", collection.deleted)


if __name__ == "__main__":
    unittest.main()
