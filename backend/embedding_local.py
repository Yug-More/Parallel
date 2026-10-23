"""Offline trained-model subprocess. Operator supplies trusted safetensors artifacts."""

import hashlib
import json
import sys
from pathlib import Path


def run():
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    request = json.loads(sys.stdin.buffer.read(200001))
    texts, dimensions = request["texts"], request["dimensions"]
    if (
        not isinstance(dimensions, int)
        or not 1 <= dimensions <= 1536
        or not isinstance(texts, list)
        or not 1 <= len(texts) <= 16
        or any(not isinstance(text, str) or not text or len(text.encode()) > 6000 for text in texts)
    ):
        raise ValueError
    root = Path(request["path"]).resolve(strict=True)
    if not root.is_dir():
        raise ValueError
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if (
        not files
        or len(files) > 100
        or any(
            p.is_symlink()
            or not p.resolve().is_relative_to(root)
            or p.suffix in {".py", ".pkl", ".pickle", ".bin"}
            for p in files
        )
        or sum(p.stat().st_size for p in files) > 300 * 1024**2
    ):
        raise ValueError
    digest = hashlib.sha256()
    for file in files:
        digest.update(str(file.relative_to(root)).encode() + b"\0")
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024**2), b""):
                digest.update(block)
    if digest.hexdigest() != request["sha256"] or not any(
        p.suffix == ".safetensors" for p in files
    ):
        raise ValueError
    modules = json.loads((root / "modules.json").read_text())
    allowed = {
        "sentence_transformers.models.Transformer",
        "sentence_transformers.models.Pooling",
        "sentence_transformers.models.Normalize",
    }
    if any(
        m["type"] not in allowed or not (root / m["path"]).resolve().is_relative_to(root)
        for m in modules
    ):
        raise ValueError
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        str(root),
        local_files_only=True,
        trust_remote_code=False,
        device="cpu",
        model_kwargs={"use_safetensors": True},
        token=False,
    )
    if model.get_sentence_embedding_dimension() != dimensions:
        raise ValueError
    model.max_seq_length = 256
    vectors = model.encode(
        request["texts"],
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return {"vectors": vectors.tolist()}


if __name__ == "__main__":
    try:
        print(json.dumps(run()))
    except Exception:
        sys.exit(1)
