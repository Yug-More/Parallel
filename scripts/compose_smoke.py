"""Exercise a disposable local Compose stack; never point at a user database.

Creates synthetic records, uses no providers, and leaves records for restart checks.
"""

import base64
import http.cookiejar
import json
import secrets
import time
import urllib.error
import urllib.request
from uuid import uuid4

BASE = "http://127.0.0.1:8000"


def client():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def request(session, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=body, headers={"Content-Type": "application/json"}
    )
    with session.open(req, timeout=10) as response:
        return json.load(response)


def wait_for(read, done):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        value = read()
        if done(value):
            return value
        time.sleep(0.25)
    raise RuntimeError("Worker did not complete the synthetic job within 60 seconds")


def main():
    owner, outsider = client(), client()
    for session in (owner, outsider):
        request(
            session,
            "/auth/register",
            {
                "name": "Compose validation",
                "email": f"compose-{uuid4().hex}@example.test",
                "password": secrets.token_urlsafe(24),
            },
        )
    workspace = request(owner, "/workspaces", {"name": "Synthetic Compose validation"})
    path = f"/workspaces/{workspace['id']}"
    task = request(owner, path + "/tasks", {"title": "Verify persisted worker outcome"})
    document = request(
        owner,
        path + "/documents",
        {
            "title": "Compose evidence",
            "filename": "compose.txt",
            "content_base64": base64.b64encode(
                b"Synthetic local worker evidence."
            ).decode(),
        },
    )
    wait_for(
        lambda: request(owner, path + "/documents")["items"],
        lambda rows: any(
            row["id"] == document["id"] and row["revisions"][0]["state"] == "ready"
            for row in rows
        ),
    )
    payload = {
        "agent_type": "local.handoff.v1",
        "objective": "Inspect synthetic task readiness",
        "idempotency_key": uuid4().hex,
    }
    run = request(owner, path + "/runs", payload)
    assert request(owner, path + "/runs", payload)["id"] == run["id"]
    result = wait_for(
        lambda: request(owner, path + "/runs/" + run["id"]),
        lambda row: row["state"] in {"completed", "failed", "cancelled"},
    )
    assert result["state"] == "completed", "Coordinator failed"
    for resource in ("/tasks", "/documents", "/runs/" + run["id"]):
        try:
            request(outsider, path + resource)
        except urllib.error.HTTPError as exc:
            assert exc.code in {403, 404}
        else:
            raise AssertionError("Cross-workspace access was accepted")
    print(
        json.dumps(
            {
                "workspace_id": workspace["id"],
                "task_id": task["id"],
                "document_id": document["id"],
                "run_id": run["id"],
                "coordinator": "completed",
                "document": "ready",
                "idempotency": "passed",
                "cross_workspace_denial": "passed",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
