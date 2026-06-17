import os
import json
import urllib.request
import urllib.error
from typing import Any, List, Optional


class BaseEmbeddingClient:
    def embed(self, text: str) -> List[float]:
        raise NotImplementedError


class NullEmbeddingClient(BaseEmbeddingClient):
    def embed(self, text: str) -> List[float]:
        # Return empty list, retriever will score it as 0.0 safely
        return []


class OllamaEmbeddingClient(BaseEmbeddingClient):
    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        self.model = model

    def embed(self, text: str) -> List[float]:
        # Try /api/embeddings first, fallback to /api/embed
        url = f"{self.host}/api/embeddings"
        data = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
        
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("embedding", [])
        except Exception:
            # Fallback to /api/embed
            url = f"{self.host}/api/embed"
            data = json.dumps({"model": self.model, "input": text}).encode("utf-8")
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
                        return embeddings[0]
            except Exception as e:
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
                    return data_list[0].get("embedding", [])
        except Exception as e:
            print(f"[OpenAIEmbeddingClient] Failed to get embedding: {e}")
        return []


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
        try:
            self._init_model()
            if self.model:
                vector = self.model.encode(text)
                # Convert numpy array to standard list of floats
                if hasattr(vector, "tolist"):
                    return vector.tolist()
                return list(vector)
        except Exception as e:
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
