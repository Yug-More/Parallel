import base64
from datetime import timedelta

from test_collaboration import join, project

from documents import ingest_once
from models import DocumentPassage, DocumentRevision, utc_now


def upload(client, wid, text=b"Architecture uses revocable sessions.", **changes):
    return client.post(
        f"/workspaces/{wid}/documents",
        json={
            "filename": "architecture.md",
            "title": "Architecture notes",
            "content_base64": base64.b64encode(text).decode(),
            **changes,
        },
    )


def test_document_lifecycle_isolation_and_revocation(accounts, application):
    alice, a = accounts()
    bob, b = accounts("bob@example.test", "Bob")
    outsider, _ = accounts("outsider@example.test", "Outsider")
    wid = project(alice)
    join(alice, bob, wid)
    response = upload(alice, wid)
    assert response.status_code == 202, response.text
    doc = response.json()
    assert doc["revisions"][0]["state"] == "queued"
    assert upload(alice, wid).json()["id"] == doc["id"]
    assert outsider.get(f"/workspaces/{wid}/documents").status_code == 404
    assert ingest_once(application.state.session_factory)
    assert not ingest_once(application.state.session_factory)
    results = bob.get(
        f"/workspaces/{wid}/knowledge", params={"q": "revocable", "kind": "document"}
    ).json()
    assert results["total"] == 1
    passage = results["items"][0]
    path = f"/workspaces/{wid}/sources/document/{passage['id']}"
    assert bob.get(path).json()["body"] == "Architecture uses revocable sessions."
    assert "page_number" not in bob.get(path).json()  # preserve Phase 6 source fingerprints
    assert outsider.get(path).status_code == 404
    assert (
        alice.post(
            f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 2}
        ).status_code
        == 409
    )
    assert (
        alice.post(
            f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 1}
        ).status_code
        == 200
    )
    assert bob.get(path).status_code == 404
    assert (
        bob.get(
            f"/workspaces/{wid}/knowledge",
            params={"q": "revocable", "include_historical": True, "include_archived": True},
        ).json()["total"]
        == 0
    )
    with application.state.session_factory() as db:
        assert db.query(DocumentRevision).one().raw_content is None
        assert db.query(DocumentPassage).count() == 1  # archive preserves user records


def test_revisions_and_stable_passages(accounts, application):
    client, _ = accounts()
    wid = project(client)
    doc = upload(client, wid).json()
    factory = application.state.session_factory
    ingest_once(factory)
    old = client.get(f"/workspaces/{wid}/knowledge?kind=document").json()["items"][0]
    payload = {
        "filename": "new.txt",
        "title": "Corrected notes",
        "version": 1,
        "content_base64": base64.b64encode(b"Use database sessions and CSRF validation.").decode(),
    }
    response = client.post(f"/workspaces/{wid}/documents/{doc['id']}/revisions", json=payload)
    assert response.status_code == 202, response.text
    assert (
        client.post(f"/workspaces/{wid}/documents/{doc['id']}/revisions", json=payload).status_code
        == 409
    )
    ingest_once(factory)
    current = client.get(f"/workspaces/{wid}/knowledge?kind=document").json()
    assert current["total"] == 1 and current["items"][0]["version"] == 2
    assert (
        client.get(f"/workspaces/{wid}/knowledge?kind=document&include_historical=true").json()[
            "total"
        ]
        == 2
    )
    assert (
        client.get(f"/workspaces/{wid}/sources/document/{old['id']}").json()["status"]
        == "historical"
    )
    with factory() as db:
        assert all(r.raw_content is None for r in db.query(DocumentRevision))


def test_validation_failure_recovery_and_cancellation(accounts, application):
    client, _ = accounts()
    wid = project(client)
    for name in ["../secret.txt", "bad.exe", "bad\x00.txt", "bad\\path.md"]:
        assert upload(client, wid, filename=name).status_code == 422
    assert upload(client, wid, content_base64="!notbase64").status_code == 422
    assert upload(client, wid, text=b"x" * 524289).status_code == 422
    factory = application.state.session_factory
    doc = upload(client, wid, text=b"\xff\x00").json()
    ingest_once(factory)
    listing = client.get(f"/workspaces/{wid}/documents").json()["items"][0]
    assert listing["revisions"][0]["error_code"] == "invalid_utf8"
    doc = upload(client, wid).json()
    with factory() as db:
        revision = db.query(DocumentRevision).filter_by(document_id=doc["id"]).one()
        revision.state, revision.lease_token = "processing", "interrupted"
        revision.lease_until = utc_now() - timedelta(seconds=1)
        db.commit()
    assert ingest_once(factory)
    with factory() as db:
        revision = db.query(DocumentRevision).filter_by(document_id=doc["id"]).one()
        assert revision.state == "failed" and revision.error_code == "lease_expired"
        assert revision.raw_content is None
    doc = upload(client, wid, text=b"Queued for cancellation").json()
    client.post(f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 1})
    assert not ingest_once(factory)
    with factory() as db:
        revision = db.query(DocumentRevision).filter_by(document_id=doc["id"]).one()
        assert revision.state == "cancelled" and revision.raw_content is None


def test_archive_during_processing_drops_result(accounts, application):
    client, _ = accounts()
    wid = project(client)
    doc = upload(client, wid).json()

    def extract(raw):
        assert (
            client.post(
                f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 1}
            ).status_code
            == 200
        )
        return raw.decode()

    assert ingest_once(application.state.session_factory, extract_fn=extract)
    with application.state.session_factory() as db:
        assert db.query(DocumentPassage).count() == 0
        assert db.query(DocumentRevision).one().state == "cancelled"


def test_removed_member_loses_documents_answers_and_retrieval(accounts, application):
    owner, _ = accounts()
    member, profile = accounts("bob@example.test", "Bob")
    wid = project(owner)
    join(owner, member, wid)
    upload(member, wid)
    ingest_once(application.state.session_factory)
    source = member.get(f"/workspaces/{wid}/knowledge?kind=document").json()["items"][0]
    assert owner.delete(f"/workspaces/{wid}/members/{profile['id']}").status_code == 200
    for path in [
        "documents",
        "answers",
        "knowledge",
        f"sources/document/{source['id']}",
        "overview",
        "action-proposals",
    ]:
        assert member.get(f"/workspaces/{wid}/{path}").status_code == 404
    assert owner.get(f"/workspaces/{wid}/sources/document/{source['id']}").status_code == 200
