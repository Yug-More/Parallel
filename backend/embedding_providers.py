"""Real trained adapters. No automatic model downloads or implicit external use."""

import json
import math
import os
import subprocess
import sys
from pathlib import Path


class EmbeddingFailure(Exception):
    pass


def normalized(vectors, dimensions):
    result = []
    for vector in vectors:
        if len(vector) != dimensions or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in vector
        ):
            raise EmbeddingFailure("invalid_vector")
        norm = math.hypot(*vector)
        if not norm or not math.isfinite(norm):
            raise EmbeddingFailure("zero_vector")
        result.append([float(v) / norm for v in vector])
    return result


class TrainedProvider:
    external = False
    trained = True

    def __init__(self, settings):
        self.settings = settings
        self.name = "trained-" + settings.embedding_provider
        self.model = f"{settings.embedding_model}@{settings.embedding_revision}:{settings.embedding_dimensions}"
        if settings.embedding_provider == "local":
            self.model += ":" + settings.embedding_artifact_sha256
        self.dimensions = settings.embedding_dimensions
        self.usage_tokens = 0

    def embed(self, texts):
        if not 1 <= len(texts) <= 16 or any(
            not isinstance(t, str) or not t or len(t) > 3000 or len(t.encode()) > 6000
            for t in texts
        ):
            raise EmbeddingFailure("batch_limit")
        try:
            result = self.compute(texts)
            if len(result) != len(texts):
                raise EmbeddingFailure("invalid_batch")
            return normalized(result, self.dimensions)
        except Exception:
            raise EmbeddingFailure("embedding_unavailable") from None


class OpenAIEmbeddings(TrainedProvider):
    external = True

    def compute(self, texts):
        from openai import OpenAI

        with OpenAI(api_key=self.settings.openai_api_key, timeout=15, max_retries=0) as client:
            response = client.embeddings.create(
                model=self.settings.embedding_model,
                input=texts,
                dimensions=self.dimensions,
                encoding_format="float",
            )
        rows = sorted(response.data, key=lambda row: row.index)
        if [r.index for r in rows] != list(range(len(texts))):
            raise EmbeddingFailure("invalid_indices")
        self.usage_tokens += response.usage.total_tokens
        return [row.embedding for row in rows]


class LocalEmbeddings(TrainedProvider):
    def compute(self, texts):
        request = {
            "path": self.settings.embedding_local_path,
            "sha256": self.settings.embedding_artifact_sha256,
            "dimensions": self.dimensions,
            "texts": texts,
        }
        result = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("embedding_local.py"))],
            input=json.dumps(request).encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            env={
                "PATH": os.defpath,
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "TOKENIZERS_PARALLELISM": "false",
                "OMP_NUM_THREADS": "1",
            },
            check=False,
        )
        if result.returncode or len(result.stdout) > 1_000_000:
            raise EmbeddingFailure("local_model_unavailable")
        return json.loads(result.stdout)["vectors"]


def configured_provider(settings):
    if not settings or settings.embedding_provider == "disabled":
        return None
    return (
        OpenAIEmbeddings(settings)
        if settings.embedding_provider == "openai"
        else LocalEmbeddings(settings)
    )
