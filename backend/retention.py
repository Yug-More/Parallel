"""Explicit irreversible content redaction. Native authored history stays intact."""

from github_app import revoke_connection
from knowledge_lifecycle import advance
from models import (
    ActionProposal,
    AgentRun,
    Approval,
    DecisionSource,
    Document,
    DocumentPassage,
    DocumentRevision,
    GitHubAuthorization,
    ImportedRecord,
    Invitation,
    KnowledgeAnswer,
    Message,
    RepositoryConnection,
    RetrievalIndex,
    utc_now,
)

DERIVED = (AgentRun, Approval, ActionProposal, KnowledgeAnswer, RetrievalIndex)


def counts(db, wid):
    return {
        model.__tablename__: db.query(model).filter_by(workspace_id=wid).count()
        for model in (*DERIVED, DocumentRevision, DocumentPassage, ImportedRecord)
    }


def redact(db, workspace, scope, target_id):
    wid = workspace.id
    advance(db, wid)
    for run in db.query(AgentRun).filter_by(workspace_id=wid):
        # Explicitly stale even for legacy runs which had no epoch in context.
        run.context, run.outcome = {"knowledge_epoch": -1}, None
        run.lease_token = run.lease_until = None
        run.error_code = "retention_redacted"
        if run.state in {"queued", "running", "waiting_for_approval"}:
            run.state, run.completed_at = "cancelled", utc_now()
    for model in (Approval, ActionProposal):
        for row in db.query(model).filter_by(workspace_id=wid):
            row.payload = {"redacted": True}
            row.error_code = "retention_redacted"
            if row.state in {"pending", "approved"}:
                row.state = "cancelled"
    db.query(KnowledgeAnswer).filter_by(workspace_id=wid).update(
        {"claims": [], "evidence": [], "state": "failed", "error_code": "retention_redacted"}
    )
    db.query(RetrievalIndex).filter_by(workspace_id=wid).update(
        {
            "entries": [],
            "state": "cancelled",
            "lease_token": None,
            "lease_until": None,
            "error_code": "retention_redacted",
        }
    )
    generated_ids = [
        row.id
        for row in db.query(Message.id).filter(
            Message.workspace_id == wid, Message.knowledge_epoch.is_not(None)
        )
    ]
    if generated_ids:
        for row in db.query(DecisionSource).filter(
            DecisionSource.workspace_id == wid,
            DecisionSource.kind == "message",
            DecisionSource.source_id.in_(generated_ids),
        ):
            row.snapshot = {**row.snapshot, "body": "", "title": "[Derived content erased]"}
    db.query(Message).filter(
        Message.workspace_id == wid, Message.knowledge_epoch.is_not(None)
    ).update({"content": "[Derived content erased]"})
    if scope in {"document", "close"}:
        documents = db.query(Document).filter_by(workspace_id=wid)
        if scope == "document":
            documents = documents.filter_by(id=target_id)
        for document in documents:
            document.archived = True
            document.version += 1
            document.title, document.filename = "[Erased document]", "erased"
            document.updated_at = utc_now()
            revisions = (
                db.query(DocumentRevision)
                .filter_by(workspace_id=wid, document_id=document.id)
                .all()
            )
            for revision in revisions:
                revision.raw_content = None
                revision.title, revision.filename = "[Erased document]", "erased"
                revision.lease_token = revision.lease_until = None
                revision.state, revision.error_code = "cancelled", "retention_redacted"
                db.query(DocumentPassage).filter_by(
                    workspace_id=wid, revision_id=revision.id
                ).update({"title": "[Erased document]", "body": ""})
    if scope in {"connection", "close"}:
        connections = db.query(RepositoryConnection).filter_by(workspace_id=wid)
        if scope == "connection":
            connections = connections.filter_by(id=target_id)
        for connection in connections:
            revoke_connection(db, connection)
            db.query(ImportedRecord).filter_by(
                workspace_id=wid, connection_id=connection.id
            ).update({"title": "[Erased imported record]", "body": "", "available": False})
    if scope == "close":
        workspace.closed_at = utc_now()
        db.query(Invitation).filter_by(workspace_id=wid, status="pending").update(
            {"status": "revoked", "responded_at": utc_now()}
        )
        db.query(GitHubAuthorization).filter_by(workspace_id=wid, state="pending").update(
            {"state": "failed", "device_secret": None, "error_code": "workspace_closed"}
        )
