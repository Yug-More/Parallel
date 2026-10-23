"""Transport/authorization tests use fabricated vectors, never model-quality evidence."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_collaboration import project
from test_documents import upload

from config import Settings
from embedding_providers import EmbeddingFailure, LocalEmbeddings, OpenAIEmbeddings, normalized
from models import Membership, RetrievalIndex
from semantic import hybrid, index_once


def settings(**values):
    return Settings(database_url="sqlite://", secret_key="x" * 32, **values)


def test_configuration_opt_in_dimensions_and_artifact_identity():
    for values in [
        {"embedding_provider": "openai"},
        {"embedding_dimensions": 1537},
        {
            "embedding_provider": "local",
            "embedding_local_path": "/tmp/model",
            "embedding_artifact_sha256": "z" * 64,
        },
        {"embedding_model": "model\nsecret"},
    ]:
        with pytest.raises(ValueError):
            settings(**values)
    config = settings(
        embedding_provider="local",
        embedding_local_path="/tmp/model",
        embedding_artifact_sha256="a" * 64,
    )
    assert "a" * 64 in LocalEmbeddings(config).model
    assert (
        LocalEmbeddings(replace(config, embedding_revision="v2")).model
        != LocalEmbeddings(config).model
    )


def test_vector_validation_rejects_nonfinite_zero_and_wrong_dimensions():
    for vector in [[0, 0], [1], [float("nan"), 1], [float("inf"), 1], ["secret", 1]]:
        with pytest.raises(EmbeddingFailure):
            normalized([vector], 2)
    assert normalized([[3, 4]], 2) == [[0.6, 0.8]]


def test_openai_transport_is_bounded_ordered_normalized_and_sanitized(monkeypatch):
    import openai

    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["timeout"] == 15 and kwargs["max_retries"] == 0
            self.embeddings = self

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=1, embedding=[0, 2]),
                    SimpleNamespace(index=0, embedding=[3, 4]),
                ],
                usage=SimpleNamespace(total_tokens=7),
            )

    monkeypatch.setattr(openai, "OpenAI", Client)
    provider = OpenAIEmbeddings(
        settings(
            embedding_provider="openai",
            external_embeddings_enabled=True,
            openai_api_key="test-only",
            embedding_dimensions=2,
        )
    )
    assert provider.embed(["one", "two"]) == [[0.6, 0.8], [0, 1]]
    assert provider.usage_tokens == 7 and calls[0]["encoding_format"] == "float"
    for texts in [[], ["x"] * 17, ["x" * 3001]]:
        with pytest.raises(EmbeddingFailure):
            provider.embed(texts)
    assert len(calls) == 1
    monkeypatch.setattr(
        Client,
        "create",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("private token")),
    )
    with pytest.raises(EmbeddingFailure, match="^embedding_unavailable$"):
        provider.embed(["one"])


def test_local_subprocess_has_no_downloads_shell_or_inherited_secrets(monkeypatch):
    import subprocess

    def run(argv, **kwargs):
        assert argv[1] == "-I" and argv[-1].endswith("embedding_local.py")
        assert kwargs["timeout"] == 30 and not kwargs.get("shell")
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        assert "OPENAI_API_KEY" not in kwargs["env"]
        return SimpleNamespace(returncode=0, stdout=b'{"vectors":[[3,4]]}')

    monkeypatch.setattr(subprocess, "run", run)
    provider = LocalEmbeddings(
        settings(
            embedding_provider="local",
            embedding_dimensions=2,
            embedding_local_path="/operator/model",
            embedding_artifact_sha256="a" * 64,
        )
    )
    assert provider.embed(["source"]) == [[0.6, 0.8]]


def trained_workspace(accounts, application, monkeypatch):
    import api.semantic
    from documents import ingest_once

    class Fake:
        # Deliberately synthetic adapter, not a trained model evaluation.
        name, model, trained, external = "trained-fixture", "fixture-v1", True, False
        usage_tokens = 0

        def embed(self, texts):
            assert len(texts) <= 16
            return [[1.0, 0.0] for _ in texts]

    owner, user = accounts()
    wid = project(owner)
    upload(owner, wid)
    ingest_once(application.state.session_factory)
    monkeypatch.setattr(api.semantic, "configured_provider", lambda _: Fake())
    queued = owner.post(f"/workspaces/{wid}/retrieval-index", json={"provider": "trained"})
    assert queued.status_code == 202, queued.text
    return owner, user, wid, queued.json(), Fake


def test_trained_index_metadata_live_filters_and_changed_model(accounts, application, monkeypatch):
    owner, _, wid, queued, fake = trained_workspace(accounts, application, monkeypatch)
    assert index_once(application.state.session_factory, fake())
    row = owner.get(f"/workspaces/{wid}/retrieval-index").json()["items"][0]
    assert row["dimensions"] == 2 and row["duration_ms"] >= 0 and row["input_characters"] > 0
    with application.state.session_factory() as db:
        assert (
            hybrid(db, wid, q="synonym", provider=fake(), kind="document")["method"]
            == "trained_hybrid_rrf_v1"
        )
        assert not hybrid(db, wid, q="synonym", provider=fake(), kind="task")["items"]
        different = fake()
        different.model = "fixture-v2"
        assert (
            hybrid(db, wid, q="synonym", provider=different)["index_status"] == "lexical_fallback"
        )
        assert db.get(RetrievalIndex, queued["id"]).options["scope"] == "authorized_sources"


def test_membership_removed_during_embedding_never_returns_old_results(
    accounts, application, monkeypatch
):
    _, user, wid, _, fake = trained_workspace(accounts, application, monkeypatch)
    index_once(application.state.session_factory, fake())

    class Removed(fake):
        def embed(self, texts):
            with application.state.session_factory() as other:
                other.delete(other.get(Membership, (wid, user["id"])))
                other.commit()
            return super().embed(texts)

    from fastapi import HTTPException

    with application.state.session_factory() as db, pytest.raises(HTTPException) as error:
        hybrid(db, wid, q="revocable", provider=Removed(), user_id=user["id"])
    assert error.value.status_code == 404


def test_explicit_extended_agent_evidence_is_bound_and_revocable(accounts, application):
    from test_intelligence import detail, drain, start

    from documents import ingest_once

    owner, _ = accounts()
    wid = project(owner)
    document = upload(owner, wid).json()
    ingest_once(application.state.session_factory)
    passage = owner.get(f"/workspaces/{wid}/knowledge?kind=document").json()["items"][0]
    refs = [{"kind": "document", "id": passage["id"]}]
    run = start(
        owner,
        wid,
        agent_type="local.research.v1",
        objective="examine evidence",
        knowledge_refs=refs,
    )
    assert run["knowledge_refs"] == refs
    assert (
        owner.post(
            f"/workspaces/{wid}/runs",
            json={
                "agent_type": "local.research.v1",
                "objective": "examine evidence",
                "idempotency_key": "request-key-0001",
                "knowledge_refs": [],
            },
        ).status_code
        == 409
    )
    drain(application)
    report = detail(owner, wid, run)
    assert report["state"] == "completed"
    assert any(
        source["kind"] == "document"
        for fact in report["outcome"]["facts"]
        for source in fact["sources"]
    )
    assert (
        owner.post(
            f"/workspaces/{wid}/documents/{document['id']}/archive", json={"version": 1}
        ).status_code
        == 200
    )
    assert detail(owner, wid, run)["evidence_unavailable"]


def test_trained_answers_explicit_opt_in_fallback_and_idempotency(
    accounts, application, monkeypatch
):

    owner, _, wid, _, fake = trained_workspace(accounts, application, monkeypatch)
    monkeypatch.setattr("embedding_providers.configured_provider", lambda _: fake())
    index_once(application.state.session_factory, fake())
    payload = {
        "question": "alternate vocabulary",
        "retrieval_mode": "trained",
        "idempotency_key": "trained-answer-one",
    }
    result = owner.post(f"/workspaces/{wid}/answers", json=payload)
    assert result.status_code == 201, result.text
    assert result.json()["evidence"] and result.json()["retrieval_mode"] == "trained"
    assert (
        owner.post(
            f"/workspaces/{wid}/answers", json={**payload, "retrieval_mode": "lexical"}
        ).status_code
        == 409
    )


def test_native_addition_invalidates_trained_snapshot_before_query(
    accounts, application, monkeypatch
):
    from test_collaboration import task

    owner, _, wid, _, fake = trained_workspace(accounts, application, monkeypatch)
    index_once(application.state.session_factory, fake())
    task(owner, wid, title="New native source")

    class MustNotCall(fake):
        def embed(self, _texts):
            raise AssertionError("Stale index must not spend a provider call")

    with application.state.session_factory() as db:
        result = hybrid(db, wid, q="New native", provider=MustNotCall())
        assert result["index_status"] == "lexical_fallback"
        assert any(row["kind"] == "task" for row in result["items"])


def test_external_consent_and_budgets_are_explicit(accounts, application, monkeypatch):
    import api.semantic
    from config import Settings

    owner, _ = accounts()
    wid = project(owner)
    provider = OpenAIEmbeddings(
        Settings(
            database_url="sqlite://",
            secret_key="x" * 32,
            embedding_provider="openai",
            external_embeddings_enabled=True,
            openai_api_key="test-only",
        )
    )
    monkeypatch.setattr(api.semantic, "configured_provider", lambda _: provider)
    assert (
        owner.post(f"/workspaces/{wid}/retrieval-index", json={"provider": "trained"}).status_code
        == 422
    )
    response = owner.post(
        f"/workspaces/{wid}/retrieval-index", json={"provider": "trained", "external_consent": True}
    )
    assert response.status_code == 202
    assert response.json()["options"]["maximum_calls"] == 4
    assert response.json()["options"]["maximum_input_bytes"] == 64000
