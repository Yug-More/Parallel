"""Conservative invalidation for generated text derived from revocable knowledge.

Epoch changes hide the whole report, even when unrelated knowledge changed.
Human-authored native records remain their authors' responsibility.
"""

from models import Workspace


def advance(db, workspace_id):
    workspace = db.get(Workspace, workspace_id)
    workspace.knowledge_epoch += 1


def visible(db, run):
    epoch = (run.context or {}).get("knowledge_epoch")
    return epoch is None or epoch == db.get(Workspace, run.workspace_id).knowledge_epoch
