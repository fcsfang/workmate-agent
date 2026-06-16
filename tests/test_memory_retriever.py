import unittest
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory

from memory import MemoryRetriever, SearchManager


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
        self.assertIn("reason", results[0])

    def test_retrieval_plan_exposes_vector_fallback_and_top_results(self):
        retriever = MemoryRetriever(vector_enabled=False)
        results = [
            {
                "source_type": "task",
                "source_id": "task-1",
                "score": 0.91,
                "reason": "关键词匹配",
                "score_breakdown": {"keyword": 1.0, "recency": 0.9},
                "text": "任务进度",
            }
        ]

        plan = retriever.build_plan("任务进度", results, needs_retrieval=True)

        self.assertEqual(plan["mode"], "hybrid")
        self.assertEqual(plan["vector_status"], "disabled")
        self.assertEqual(plan["top_results"][0]["source_id"], "task-1")
        self.assertEqual(plan["sufficiency"], "enough")

    def test_search_manager_indexes_tasks_and_behavior_patterns(self):
        with TemporaryDirectory() as tmpdir:
            search = SearchManager(
                index_path=f"{tmpdir}/retrieval_index.json",
                retriever=MemoryRetriever(vector_enabled=False),
            )
            index = search.build_index(
                records=[],
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
            )

        self.assertIn("task", {item["type"] for item in index})
        self.assertIn("behavior_pattern", {item["type"] for item in index})


if __name__ == "__main__":
    unittest.main()
