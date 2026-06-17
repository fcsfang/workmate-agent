import os
import json
import unittest
from unittest.mock import MagicMock, patch
import urllib.request
from io import BytesIO

from memory.embeddings import (
    get_embedding_client,
    NullEmbeddingClient,
    OllamaEmbeddingClient,
    OpenAIEmbeddingClient,
    LocalEmbeddingClient
)
from memory.search import SearchManager
from memory.retriever import MemoryRetriever


class MockResponse:
    def __init__(self, data, code=200):
        self.data = data
        self.code = code

    def read(self):
        return self.data

    def decode(self, encoding):
        return self.data.decode(encoding)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestVectorRAG(unittest.TestCase):
    def setUp(self):
        self.temp_index_path = "/tmp/test_retrieval_index.json"
        if os.path.exists(self.temp_index_path):
            os.remove(self.temp_index_path)

    def tearDown(self):
        if os.path.exists(self.temp_index_path):
            os.remove(self.temp_index_path)

    @patch("urllib.request.urlopen")
    def test_get_embedding_client_auto_detect(self, mock_urlopen):
        # Case 1: Ollama is running (auto-detects ollama)
        mock_urlopen.return_value = MockResponse(b"OK", 200)
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": ""}):
            client = get_embedding_client()
            self.assertIsInstance(client, OllamaEmbeddingClient)

        # Case 2: Ollama not running, but LLM API key configured (auto-detects openai)
        mock_urlopen.side_effect = Exception("Connection refused")
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "", "LLM_API_KEY": "sk-test"}):
            client = get_embedding_client()
            self.assertIsInstance(client, OpenAIEmbeddingClient)

        # Case 3: Ollama not running, no API key (auto-detects none)
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "", "LLM_API_KEY": "", "VISION_API_KEY": ""}):
            client = get_embedding_client()
            self.assertIsInstance(client, NullEmbeddingClient)

    def test_get_embedding_client_explicit(self):
        # Case 1: Explicit provider = openai
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "openai", "LLM_API_KEY": "sk-123"}):
            client = get_embedding_client()
            self.assertIsInstance(client, OpenAIEmbeddingClient)
            self.assertEqual(client.model, "text-embedding-3-small")

        # Case 2: Explicit provider = ollama
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "ollama"}):
            client = get_embedding_client()
            self.assertIsInstance(client, OllamaEmbeddingClient)
            self.assertEqual(client.model, "nomic-embed-text")

        # Case 3: Explicit provider = local
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "local"}):
            client = get_embedding_client()
            self.assertIsInstance(client, LocalEmbeddingClient)
            self.assertEqual(client.model_name, "all-MiniLM-L6-v2")

        # Case 4: Explicit provider = none
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "none"}):
            client = get_embedding_client()
            self.assertIsInstance(client, NullEmbeddingClient)

    @patch("urllib.request.urlopen")
    def test_openai_embedding_client(self, mock_urlopen):
        mock_response_data = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3]}
            ]
        }
        mock_urlopen.return_value = MockResponse(json.dumps(mock_response_data).encode("utf-8"))
        
        client = OpenAIEmbeddingClient(api_key="sk-test", base_url="https://api.openai.com/v1", model="text-embedding-3-small")
        vector = client.embed("test text")
        self.assertEqual(vector, [0.1, 0.2, 0.3])

    @patch("urllib.request.urlopen")
    def test_ollama_embedding_client_api_embeddings(self, mock_urlopen):
        # Test default endpoint /api/embeddings
        mock_response_data = {
            "embedding": [0.4, 0.5, 0.6]
        }
        mock_urlopen.return_value = MockResponse(json.dumps(mock_response_data).encode("utf-8"))
        
        client = OllamaEmbeddingClient(host="http://localhost:11434", model="nomic-embed-text")
        vector = client.embed("test text")
        self.assertEqual(vector, [0.4, 0.5, 0.6])

    @patch("urllib.request.urlopen")
    def test_ollama_embedding_client_api_embed_fallback(self, mock_urlopen):
        # First call to /api/embeddings fails, second to /api/embed succeeds
        mock_response_embed = {
            "embeddings": [[0.7, 0.8, 0.9]]
        }
        
        def mock_side_effect(req, *args, **kwargs):
            if "/api/embeddings" in req.full_url:
                raise Exception("Not found")
            return MockResponse(json.dumps(mock_response_embed).encode("utf-8"))
            
        mock_urlopen.side_effect = mock_side_effect
        
        client = OllamaEmbeddingClient(host="http://localhost:11434", model="nomic-embed-text")
        vector = client.embed("test text")
        self.assertEqual(vector, [0.7, 0.8, 0.9])

    def test_vector_similarity_scoring(self):
        retriever = MemoryRetriever(vector_enabled=True)
        # Cosine similarity of identical vectors should be 1.0
        v1 = [1.0, 2.0, 3.0]
        v2 = [1.0, 2.0, 3.0]
        score = retriever.vector_score(v1, v2)
        self.assertAlmostEqual(score, 1.0, places=4)

        # Cosine similarity of orthogonal vectors should be 0.0
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        score = retriever.vector_score(v1, v2)
        self.assertAlmostEqual(score, 0.0, places=4)

        # Cosine similarity of opposite vectors should be 0.0 (clipped to min 0.0 in vector_score)
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        score = retriever.vector_score(v1, v2)
        self.assertAlmostEqual(score, 0.0, places=4)

    def test_search_manager_incremental_caching(self):
        mock_embed_client = MagicMock()
        mock_embed_client.embed.side_effect = lambda text: [float(len(text)), 1.0, 2.0]

        # Enable vector search
        with patch.dict(os.environ, {"WORKMATE_VECTOR_RETRIEVAL": "true"}):
            retriever = MemoryRetriever(embedding_client=mock_embed_client, vector_enabled=True)
            search_manager = SearchManager(index_path=self.temp_index_path, retriever=retriever)

            records = [
                {"id": "r1", "time": "2026-06-17T12:00:00", "user": "hello", "assistant": "hi", "extracted": {}},
                {"id": "r2", "time": "2026-06-17T12:05:00", "user": "need help", "assistant": "sure", "extracted": {}}
            ]

            # First build: client should be called for each item
            search_manager.build_index(records=records)
            first_call_count = mock_embed_client.embed.call_count
            self.assertEqual(first_call_count, 2)

            # Load and verify embeddings exist in file
            loaded = search_manager.load_index()
            self.assertEqual(len(loaded), 2)
            self.assertIsNotNone(loaded[0].get("embedding"))
            self.assertEqual(loaded[0]["embedding"][1], 1.0)

            # Reset call count
            mock_embed_client.embed.reset_mock()

            # Second build (same records): should hit cache, call_count should be 0!
            search_manager.build_index(records=records)
            self.assertEqual(mock_embed_client.embed.call_count, 0)

            # Reset call count
            mock_embed_client.embed.reset_mock()

            # Third build (one new record added): only the new record should be embedded (1 call)
            records.append({"id": "r3", "time": "2026-06-17T12:10:00", "user": "new task", "assistant": "ok", "extracted": {}})
            search_manager.build_index(records=records)
            self.assertEqual(mock_embed_client.embed.call_count, 1)

    @patch("builtins.__import__")
    def test_chromadb_import_fallback(self, mock_import):
        orig_import = __import__
        def import_side_effect(name, *args, **kwargs):
            if name == "chromadb":
                raise ImportError("mock import error")
            return orig_import(name, *args, **kwargs)
        mock_import.side_effect = import_side_effect

        retriever = MemoryRetriever(vector_enabled=False)
        search_manager = SearchManager(index_path=self.temp_index_path, retriever=retriever)
        
        self.assertFalse(search_manager.chroma_enabled)

    def test_chromadb_query_retrieval(self):
        mock_embed_client = MagicMock()
        mock_embed_client.embed.side_effect = lambda text: [0.1, 0.2, 0.3] if "LangChain" in text else [0.9, 0.9, 0.9]

        with patch.dict(os.environ, {"WORKMATE_VECTOR_RETRIEVAL": "true"}):
            retriever = MemoryRetriever(embedding_client=mock_embed_client, vector_enabled=True)
            search_manager = SearchManager(index_path=self.temp_index_path, retriever=retriever)

            records = [
                {"id": "r1", "time": "2026-06-17T12:00:00", "user": "研究一下 LangChain 的优化进度", "assistant": "正在梳理 LangChain RAG 流程", "extracted": {}},
                {"id": "r2", "time": "2026-06-17T12:05:00", "user": "去健身房锻炼", "assistant": "好，去锻炼身体", "extracted": {}}
            ]
            search_manager.build_index(records=records)

            # Query should semantic match record 1
            # Mock query embedding: LangChain vector matches [0.1, 0.2, 0.3]
            mock_embed_client.embed.side_effect = lambda text: [0.1, 0.2, 0.3]

            results = search_manager.search("LangChain 进展", records=records, limit=1)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["id"], "record-0")
            self.assertIn("LangChain", results[0]["text"])
