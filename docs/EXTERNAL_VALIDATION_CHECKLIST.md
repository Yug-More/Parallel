# Owner validation checklist

Phase 15 · ordinary tests require no private credentials, model weights, email provider or production data. None was supplied or used for this finalization. Synthetic adapters prove local boundaries, not external outcomes. Do not paste credentials into issues or browser token fields.

## Trained retrieval quality and ML compatibility

1. Create a separate disposable Python 3.12/3.13 environment. Install `backend/requirements-embeddings.txt`; run `pip check` and a full resolved dependency advisory audit. Record operating system, Python, resolved versions and audit date. The optional full ML runtime has not been installed/audited here.
2. Provision a licensed, trusted immutable model directory offline. Do not let the application download weights. Validate safetensors/artifact SHA256 and the allowed module configuration described in [hardening](INTELLIGENCE_HARDENING.md); do not enable remote code or pickle/bin loading.
3. Configure `EMBEDDING_PROVIDER=local`, local path/artifact digest, provider/model/revision/dimensions consistently for HTTP/worker. Use an isolated test database and no real user documents.
4. Run `python backend/evaluation/pilot.py --offline-trained --output /private/new-trained-evaluation.json` with that operator configuration. Retain per-query results, strict precision@5, recall/MRR, latency workload, abstentions and failures. Compare the same frozen labels to lexical coverage; never tune and report on the same holdout.
5. Recruit independent reviewers to assess evidence relevance/entailment and ambiguous/multilingual questions. Existing judgments are developer-created, not independent, and no semantic-quality claim follows from fabricated-vector tests.

External embeddings/model answers additionally need explicit cost approval, server opt-in, owner indexing consent/per-query consent and bounded test evidence. Use documented explicit settings; no paid call is part of this checklist execution here.

## Live private GitHub

1. The owner/operator registers a read-only GitHub App with selected repositories and the exact permissions/configuration in [integrations](INTEGRATIONS.md). Provision a distinct encryption key and private key backups; do not reuse signing keys or CLI/browser tokens.
2. In a disposable workspace, use the UI device flow, authorize only an owned synthetic private repository, select the verified installation/repository and record live authorization/sync timestamps without grants or secrets.
3. Inspect imported records and original links; revalidate before an explicit model request. Verify ordinary access expiry and the separate 30-second transmission boundary.
4. Revoke repository/App/user access and verify subsequent sync/revalidation denies retrieval, invalidates derived evidence and discards late work. Test ownership changes/refresh rotation in that isolated fixture repository.
5. Record actual provider responses as sanitized outcomes and dates. Existing fake transport checks and historical public GET checks do not establish live private access. Repository writes remain unavailable.

## Recovery and email delivery

The only implemented delivery adapter is a development/test private local outbox. Production rejects it. The owner cannot simply configure SMTP and claim supported real email: a production delivery adapter, channel verification, secrets management, abuse controls and failure monitoring require a separate reviewed implementation. Then test known/unknown generic responses, one-use/expiry, replay, reset session revocation and actual mailbox receipt using synthetic accounts. In-app invitations do not deliver email. Local outbox completion does not prove mailbox ownership.

## Independent usability and accessibility

Recruit participants who did not build the app. Use synthetic content and observe sign-in/recovery, switching workspaces, composing code/prose, finding a citation, understanding local contract limits, rejecting/approving exact actions, removing access and interpreting retention exceptions. Record completion, errors, comprehension, assistive technology/browser/viewport, and consented feedback. Include keyboard-only users and screen readers, zoom/reflow, OS high contrast and touch. Engineering browser checks and token contrast calculations do not establish full WCAG conformance or real-user success.

## Production operations and backups

No deployment/release is authorized by internal finalization. Before an owner-authorized pilot, establish TLS/ingress protections, explicit production settings, PostgreSQL/key ownership, least-privilege service accounts, installed supervision, monitoring, queue alerts, encrypted offsite backups, retention policy and operator response procedures. Test restoration into an **exclusive new** environment with required keys and receipt/content checks; keep live data untouched. Measure recovery time/point objectives under a stated workload and perform a supervised failure exercise. The existing isolated SQLite/PostgreSQL restore scripts demonstrate synthetic restoration only. Historical Plivo credential revocation/rotation remains an owner action; source cleanup did not revoke it.

Publish a dated evidence record for each completed external check. Until then keep these gaps explicit in product demonstrations and documentation.
