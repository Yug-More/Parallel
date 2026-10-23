"""Real parser tests; all PDF bytes are synthetic, no network or fixture keys."""

import io
import subprocess

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from test_collaboration import project
from test_documents import upload

from documents import ingest_once
from models import DocumentPassage, DocumentRevision
from pdf_extract import extract_pdf


def pdf_bytes(
    texts=("First page has revocable sessions", "Second page has database backups"), encrypt=False
):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 250 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypt:
        writer.encrypt("test-password")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_pdf_pages_persistence_revision_dedup_and_revocation(accounts, application):
    owner, _ = accounts()
    stranger, _ = accounts("stranger@example.test", "Stranger")
    wid = project(owner)
    raw = pdf_bytes()
    doc = upload(owner, wid, raw, filename="design.pdf").json()
    assert upload(owner, wid, raw, filename="same.pdf").json()["id"] == doc["id"]
    factory = application.state.session_factory
    assert ingest_once(factory)
    results = owner.get(f"/workspaces/{wid}/knowledge?kind=document").json()["items"]
    assert len(results) == 2
    sources = [owner.get(f"/workspaces/{wid}/sources/document/{r['id']}").json() for r in results]
    assert {s["page_number"] for s in sources} == {1, 2}
    assert stranger.get(f"/workspaces/{wid}/sources/document/{results[0]['id']}").status_code == 404
    owner.post(f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 1})
    assert (
        owner.get(f"/workspaces/{wid}/knowledge?kind=document&include_historical=true").json()[
            "total"
        ]
        == 0
    )
    with factory() as db:
        assert db.query(DocumentRevision).one().raw_content is None
        assert db.query(DocumentPassage).count() == 2


@pytest.mark.parametrize(
    "raw,code",
    [
        (b"%PDF-broken", "pdf_invalid"),
        (pdf_bytes(encrypt=True), "pdf_encrypted"),
        (pdf_bytes(("",)), "pdf_no_text"),
        (pdf_bytes(tuple("page" for _ in range(31))), "pdf_page_limit"),
    ],
    ids=["malformed", "encrypted", "empty", "too-many-pages"],
)
def test_pdf_safe_failures(accounts, application, raw, code):
    owner, _ = accounts()
    wid = project(owner)
    response = upload(owner, wid, raw, filename="notes.pdf")
    assert response.status_code == 202
    assert ingest_once(application.state.session_factory)
    doc = owner.get(f"/workspaces/{wid}/documents").json()["items"][0]
    assert doc["revisions"][0]["state"] == "failed"
    assert doc["revisions"][0]["error_code"] == code


def test_pdf_signature_size_timeout_and_segmentation(accounts, monkeypatch):
    from segmentation import segments

    owner, _ = accounts()
    wid = project(owner)
    for raw, name in [
        (b"not PDF", "a.pdf"),
        (pdf_bytes(), "a.txt"),
        (b"%PDF-" + b"x" * 524288, "a.pdf"),
    ]:
        assert upload(owner, wid, raw, filename=name).status_code == 422

    def timeout(*args, **kwargs):
        assert kwargs["env"] == {"PATH": __import__("os").defpath}
        assert args[0][1] == "-I"
        raise subprocess.TimeoutExpired("parser", 8)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ValueError, match="pdf_timeout"):
        extract_pdf(pdf_bytes())
    text = "alpha " * 160 + "\n\n" + "bravo " * 180
    parts = list(segments(text))
    assert all(len(p) <= 1200 for p in parts) and "".join(parts) == text


def test_pdf_revision_keeps_old_page_provenance_and_immutable_identifiers(accounts, application):
    import base64

    owner, _ = accounts()
    wid = project(owner)
    doc = upload(owner, wid, pdf_bytes(), filename="design.pdf").json()
    ingest_once(application.state.session_factory)
    original = owner.get(f"/workspaces/{wid}/knowledge?kind=document").json()["items"]
    response = owner.post(
        f"/workspaces/{wid}/documents/{doc['id']}/revisions",
        json={
            "version": 1,
            "filename": "corrected.pdf",
            "title": "Corrected design",
            "content_base64": base64.b64encode(pdf_bytes(("Corrected session policy",))).decode(),
        },
    )
    assert response.status_code == 202
    ingest_once(application.state.session_factory)
    current = owner.get(f"/workspaces/{wid}/knowledge?kind=document").json()["items"]
    assert len(current) == 1 and current[0]["version"] == 2
    for old in original:
        source = owner.get(f"/workspaces/{wid}/sources/document/{old['id']}").json()
        assert (
            source["status"] == "historical"
            and source["page_number"] in {1, 2}
            and source["filename"] == "design.pdf"
        )
    assert (
        owner.get(f"/workspaces/{wid}/knowledge?kind=document&include_historical=true").json()[
            "total"
        ]
        == 3
    )
