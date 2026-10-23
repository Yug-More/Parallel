from dataclasses import replace

from test_collaboration import project, task
from test_documents import upload

from documents import ingest_once
from models import KnowledgeAnswer


def ask(client, wid, **changes):
    return client.post(
        f"/workspaces/{wid}/answers",
        json={
            "question": "revocable sessions",
            "idempotency_key": "question-request-0001",
            **changes,
        },
    )


def test_extractive_answers_persist_abstain_and_revoke(accounts, application):
    client, _ = accounts()
    outsider, _ = accounts("outsider@example.test", "Other")
    wid = project(client)
    assert ask(client, wid).json()["state"] == "abstained"
    doc = upload(client, wid).json()
    ingest_once(application.state.session_factory)
    response = ask(client, wid, idempotency_key="question-request-0002")
    assert response.status_code == 201, response.text
    answer = response.json()
    assert answer["mode"] == "extractive" and answer["state"] == "completed"
    assert answer["claims"][0]["citations"] == [answer["evidence"][0]["ref"]]
    assert ask(client, wid, idempotency_key="question-request-0002").json()["id"] == answer["id"]
    assert (
        ask(client, wid, question="different", idempotency_key="question-request-0002").status_code
        == 409
    )
    assert outsider.get(f"/workspaces/{wid}/answers").status_code == 404
    client.post(f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 1})
    listing = client.get(f"/workspaces/{wid}/answers").json()
    assert listing["items"][0]["state"] == "evidence_unavailable"
    assert listing["items"][0]["claims"] == [] and listing["items"][0]["evidence"] == []
    with application.state.session_factory() as db:
        assert db.query(KnowledgeAnswer).count() == 2


def test_model_requires_opt_in_and_validates_actual_citations(accounts, application, monkeypatch):
    client, _ = accounts()
    wid = project(client)
    task(client, wid, title="Revocable sessions")
    assert ask(client, wid, mode="model").status_code == 503
    application.state.settings = replace(
        application.state.settings,
        grounded_model_enabled=True,
        openai_api_key="test-adapter-only-key",
    )
    calls = []

    def adapter(settings, question, evidence):
        calls.append(evidence)
        return {
            "claims": [
                {
                    "kind": "inference",
                    "text": "Review session design.",
                    "citations": [evidence[0]["ref"]],
                }
            ]
        }

    monkeypatch.setattr("providers.generate_grounded", adapter)
    response = ask(client, wid, mode="model")
    assert response.json()["state"] == "completed"
    assert response.json()["claims"][0]["kind"] == "inference"
    assert len(calls) == 1 and len(calls[0]) <= 8
    assert ask(client, wid, mode="model").json()["id"] == response.json()["id"]
    assert len(calls) == 1
    monkeypatch.setattr(
        "providers.generate_grounded",
        lambda *_: {
            "claims": [{"kind": "fact", "text": "Fabricated", "citations": ["task:not-retrieved"]}]
        },
    )
    failed = ask(client, wid, mode="model", idempotency_key="invalid-citation-0001").json()
    assert failed["state"] == "failed" and failed["claims"] == []
    assert failed["error_code"] == "answer_generation_failed"


def test_provider_revalidation_failure_and_safe_errors(accounts, application, monkeypatch):
    client, _ = accounts()
    wid = project(client)
    doc = upload(client, wid).json()
    ingest_once(application.state.session_factory)
    application.state.settings = replace(
        application.state.settings,
        grounded_model_enabled=True,
        openai_api_key="test-adapter-only-key",
    )

    def adapter(settings, question, evidence):
        client.post(f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 1})
        return {
            "claims": [
                {"kind": "fact", "text": "Should never appear", "citations": [evidence[0]["ref"]]}
            ]
        }

    monkeypatch.setattr("providers.generate_grounded", adapter)
    result = ask(client, wid, mode="model").json()
    assert result["state"] == "evidence_unavailable" and result["claims"] == []
    task(client, wid, title="Revocable sessions")

    def broken(*_args):
        raise RuntimeError("provider-secret-token-and-body")

    monkeypatch.setattr("providers.generate_grounded", broken)
    response = ask(client, wid, mode="model", idempotency_key="provider-error-0001")
    assert response.json()["state"] == "failed"
    assert "provider-secret" not in response.text


def test_overview_and_request_body_limit(accounts):
    client, _ = accounts()
    wid = project(client)
    task(client, wid, status="blocked")
    response = client.get(f"/workspaces/{wid}/overview")
    assert response.status_code == 200, response.text
    assert response.json()["blocked_task_total"] == 1
    assert response.json()["documents"] == response.json()["connections"] == 0
    assert (
        client.post(
            f"/workspaces/{wid}/answers",
            content=b"x" * 800001,
            headers={"content-type": "application/json"},
        ).status_code
        == 413
    )


def test_historical_decision_revision_is_explicit_and_resolvable(accounts):
    from test_intelligence import decision, edit

    client, _ = accounts()
    wid = project(client)
    item = decision(client, wid, title="Storage policy", statement="Use SQLite")
    response = client.patch(
        f"/workspaces/{wid}/decisions/{item['id']}", json=edit(item, statement="Use PostgreSQL")
    )
    assert response.status_code == 200
    assert client.get(f"/workspaces/{wid}/knowledge?q=SQLite&kind=decision").json()["total"] == 0
    revisions = client.get(f"/workspaces/{wid}/knowledge?q=SQLite&kind=decision_revision").json()
    assert revisions["total"] == 1
    source = client.get(
        f"/workspaces/{wid}/sources/decision_revision/{revisions['items'][0]['id']}"
    ).json()
    assert source["version"] == 1 and source["current_version"] == 2
    assert source["authority"] == "historical_decision_revision"


def test_conversation_model_derivations_obey_document_revocation(
    accounts, application, monkeypatch
):
    from api.messages import recent_context

    owner, _ = accounts()
    wid = project(owner)
    doc = upload(owner, wid).json()
    ingest_once(application.state.session_factory)
    question = owner.post(
        f"/workspaces/{wid}/messages", json={"content": "Summarize the report"}
    ).json()
    monkeypatch.setattr(
        "providers.generate_reply", lambda *_: "Revocable sessions use copied-token protection."
    )
    response = owner.post(f"/workspaces/{wid}/agent-replies", json={"message_id": question["id"]})
    assert response.status_code == 201 and "copied-token" in response.json()["content"]
    owner.post(f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 1})
    messages = owner.get(f"/workspaces/{wid}/messages").json()
    assert "Report hidden" in next(m for m in messages if m["role"] == "assistant")["content"]
    with application.state.session_factory() as db:
        assert all("copied-token" not in row["content"] for row in recent_context(db, wid))
    assert (
        owner.get(f"/workspaces/{wid}/knowledge?q=copied-token&kind=message").json()["total"] == 0
    )


def test_conversation_provider_late_result_cannot_outlive_revocation(
    accounts, application, monkeypatch
):
    owner, _ = accounts()
    wid = project(owner)
    doc = upload(owner, wid).json()
    question = owner.post(f"/workspaces/{wid}/messages", json={"content": "Summarize"}).json()

    def adapter(*_args):
        owner.post(f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 1})
        return "Must be discarded"

    monkeypatch.setattr("providers.generate_reply", adapter)
    response = owner.post(f"/workspaces/{wid}/agent-replies", json={"message_id": question["id"]})
    assert response.status_code == 409
    assert all(m["role"] != "assistant" for m in owner.get(f"/workspaces/{wid}/messages").json())


def test_grounded_provider_adapter_bounds_and_sanitizes_transport(application, monkeypatch):
    import json
    import sys
    from types import SimpleNamespace

    import pytest

    import providers

    calls = []

    class Transport:
        def __init__(self, **options):
            calls.append(options)
            self.responses = SimpleNamespace(create=self.create)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            calls.append({"closed": True})

        def create(self, **options):
            calls.append(options)
            return SimpleNamespace(status="completed", output_text=json.dumps({"claims": []}))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Transport))
    settings = replace(
        application.state.settings,
        grounded_model_enabled=True,
        openai_api_key="test-only-adapter-key-not-a-real-credential",
    )
    assert providers.generate_grounded(
        settings, "Question", [{"ref": "task:one", "body": "Untrusted"}]
    ) == {"claims": []}
    assert calls[0]["timeout"] == 20 and calls[0]["max_retries"] == 0
    request = calls[1]
    assert request["store"] is False and request["max_output_tokens"] == 1600
    assert "tools" not in request and request["text"]["format"]["strict"] is True
    assert calls[-1] == {"closed": True}

    def broken(_self, **_options):
        raise RuntimeError("private-provider-body-and-credential")

    monkeypatch.setattr(Transport, "create", broken)
    with pytest.raises(providers.ProviderFailure) as error:
        providers.generate_grounded(settings, "Question", [])
    assert "private-provider" not in str(error.value)
