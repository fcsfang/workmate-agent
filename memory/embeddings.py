import os
import json
import time
import urllib.request
import urllib.error
from typing import Any, List, Optional

from observability import record_provider_call


class BaseEmbeddingClient:
    def embed(self, text: str) -> List[float]:
        raise NotImplementedError


class NullEmbeddingClient(BaseEmbeddingClient):
    def embed(self, text: str) -> List[float]:
        # Return empty list, retriever will score it as 0.0 safely
        record_provider_call(
            "embedding",
            provider="none",
            operation="embed.disabled",
            model="",
            metadata={"text_chars": len(text or "")},
        )
        return []


class OllamaEmbeddingClient(BaseEmbeddingClient):
    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        self.model = model

    def embed(self, text: str) -> List[float]:
        # Try /api/embeddings first, fallback to /api/embed
        url = f"{self.host}/api/embeddings"
        data = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
        started = time.perf_counter()
        
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                embedding = result.get("embedding", [])
                record_provider_call(
                    "embedding",
                    provider="ollama",
                    operation="/api/embeddings",
                    model=self.model,
                    started_perf=started,
                    metadata={"text_chars": len(text or ""), "embedding_dimensions": len(embedding)},
                )
                return embedding
        except Exception as exc:
            record_provider_call(
                "embedding",
                provider="ollama",
                operation="/api/embeddings",
                model=self.model,
                status="fallback",
                started_perf=started,
                error=exc,
                fallback="/api/embed",
                metadata={"text_chars": len(text or "")},
            )
            # Fallback to /api/embed
            url = f"{self.host}/api/embed"
            data = json.dumps({"model": self.model, "input": text}).encode("utf-8")
            fallback_started = time.perf_counter()
            try:
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    # /api/embed returns "embeddings" which is a list of lists (one per input)
                    embeddings = result.get("embeddings", [])
                    if embeddings and isinstance(embeddings, list):
                        embedding = embeddings[0]
                        record_provider_call(
                            "embedding",
                            provider="ollama",
                            operation="/api/embed",
                            model=self.model,
                            started_perf=fallback_started,
                            metadata={"text_chars": len(text or ""), "embedding_dimensions": len(embedding)},
                        )
                        return embedding
            except Exception as e:
                record_provider_call(
                    "embedding",
                    provider="ollama",
                    operation="/api/embed",
                    model=self.model,
                    status="error",
                    started_perf=fallback_started,
                    error=e,
                    metadata={"text_chars": len(text or "")},
                )
                print(f"[OllamaEmbeddingClient] Failed to get embedding: {e}")
        return []


class OpenAIEmbeddingClient(BaseEmbeddingClient):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def embed(self, text: str) -> List[float]:
        # Call OpenAI embeddings endpoint
        url = f"{self.base_url}/embeddings"
        data = json.dumps({"model": self.model, "input": text}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        started = time.perf_counter()
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                data_list = result.get("data", [])
                if data_list:
                    embedding = data_list[0].get("embedding", [])
                    record_provider_call(
                        "embedding",
                        provider=self._provider_label(),
                        operation="/embeddings",
                        model=self.model,
                        started_perf=started,
                        metadata={"text_chars": len(text or ""), "embedding_dimensions": len(embedding)},
                    )
                    return embedding
        except Exception as e:
            record_provider_call(
                "embedding",
                provider=self._provider_label(),
                operation="/embeddings",
                model=self.model,
                status="error",
                started_perf=started,
                error=e,
                metadata={"text_chars": len(text or "")},
            )
            print(f"[OpenAIEmbeddingClient] Failed to get embedding: {e}")
        return []

    def _provider_label(self) -> str:
        value = str(self.base_url or "").lower()
        if "openrouter" in value:
            return "openrouter"
        if "openai" in value:
            return "openai"
        return "custom" if value else "unknown"


class LocalEmbeddingClient(BaseEmbeddingClient):
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.model = None
        self._initialized = False

    def _init_model(self):
        if self._initialized:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            self._initialized = True
        except ImportError as e:
            print(f"[LocalEmbeddingClient] sentence-transformers library not installed. Please run `pip install sentence-transformers`. Error: {e}")
            raise e

    def embed(self, text: str) -> List[float]:
        started = time.perf_counter()
        try:
            self._init_model()
            if self.model:
                vector = self.model.encode(text)
                # Convert numpy array to standard list of floats
                if hasattr(vector, "tolist"):
                    embedding = vector.tolist()
                else:
                    embedding = list(vector)
                record_provider_call(
                    "embedding",
                    provider="local",
                    operation="sentence_transformers.encode",
                    model=self.model_name,
                    started_perf=started,
                    metadata={"text_chars": len(text or ""), "embedding_dimensions": len(embedding)},
                )
                return embedding
        except Exception as e:
            record_provider_call(
                "embedding",
                provider="local",
                operation="sentence_transformers.encode",
                model=self.model_name,
                status="error",
                started_perf=started,
                error=e,
                metadata={"text_chars": len(text or "")},
            )
            print(f"[LocalEmbeddingClient] Failed to get embedding locally: {e}")
        return []


def get_embedding_client() -> BaseEmbeddingClient:
    provider = os.getenv("EMBEDDING_PROVIDER", "").lower()
    
    # Auto-detect if provider is empty or not configured
    if not provider:
        # Check if Ollama responds quickly
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        try:
            resp = urllib.request.urlopen(ollama_host, timeout=0.5)
            resp.close()
            provider = "ollama"
        except Exception:
            # Check if OpenAI is configured
            if os.getenv("LLM_API_KEY") or os.getenv("VISION_API_KEY"):
                provider = "openai"
            else:
                provider = "none"

    if provider == "ollama":
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        return OllamaEmbeddingClient(host=host, model=model)
        
    elif provider == "openai":
        api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("VISION_API_KEY") or ""
        base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv("LLM_BASE_URL") or os.getenv("VISION_BASE_URL") or "https://api.openai.com/v1"
        model = os.getenv("EMBEDDING_MODEL_ID") or "text-embedding-3-small"
        return OpenAIEmbeddingClient(api_key=api_key, base_url=base_url, model=model)
        
    elif provider == "local":
        model_name = os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        return LocalEmbeddingClient(model_name=model_name)
        
    return NullEmbeddingClient()
