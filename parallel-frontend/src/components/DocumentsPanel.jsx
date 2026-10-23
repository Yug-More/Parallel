import { useState } from "react";
import { api } from "../api";
import { useProjectAction, useWorkspaceQuery } from "./projectHooks";

export default function DocumentsPanel({
  workspaceId,
  onAccessLost,
  onConfirm,
}) {
  const base = `/workspaces/${workspaceId}/documents`;
  const [externalConsent, setExternalConsent] = useState(false);
  const [includeHistory, setIncludeHistory] = useState(false);
  const [offset, setOffset] = useState(0);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [target, setTarget] = useState(null);
  const query = useWorkspaceQuery(
    `${base}?offset=${offset}`,
    workspaceId,
    onAccessLost,
    2000,
  );
  const index = useWorkspaceQuery(
    `/workspaces/${workspaceId}/retrieval-index`,
    workspaceId,
    onAccessLost,
    3000,
  );
  const actions = useProjectAction(workspaceId, onAccessLost);
  async function upload(event) {
    event.preventDefault();
    const result = await actions.act(async () => {
      if (!file || file.size > 524288 || !/\.(txt|md|pdf)$/i.test(file.name))
        throw new Error(
          "Choose a .txt, .md or extractable-text .pdf file up to 512 KiB.",
        );
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (const byte of bytes) binary += String.fromCharCode(byte);
      return api(target ? `${base}/${target.id}/revisions` : base, {
        method: "POST",
        body: {
          filename: file.name,
          title,
          content_base64: btoa(binary),
          ...(target ? { version: target.version } : {}),
        },
      });
    }, "Upload accepted. Identical content reuses its document; queued revisions await local extraction.");
    if (result) {
      setTarget(null);
      query.reload();
    }
  }
  return (
    <section className="project-section" aria-label="Documents">
      <div className="section-heading">
        <div>
          <h2>Workspace documents</h2>
          <p>
            UTF-8 text, Markdown and extractable-text PDFs. Searchable after
            extraction; source text is untrusted evidence.
          </p>
        </div>
      </div>
      {actions.error && <p role="alert">{actions.error}</p>}
      {query.error && <p role="alert">{query.error}</p>}
      {actions.notice && <p role="status">{actions.notice}</p>}
      <form className="surface project-form" onSubmit={upload}>
        <h3>{target ? `Revise ${target.title}` : "Add a document"}</h3>
        <label>
          Document title
          <input
            required
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          Text, Markdown or PDF file
          <input
            type="file"
            required
            accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
            onChange={(e) => setFile(e.target.files[0] || null)}
          />
        </label>
        <p>
          Maximum 512 KiB, 200,000 extracted characters and 30 PDF pages.
          Encrypted files and scanned-image PDFs without text are rejected. No
          OCR. Run the backend worker to process uploads.
        </p>
        <div className="button-row">
          <button disabled={actions.busy}>
            {actions.busy ? "Uploading…" : "Upload document"}
          </button>
          {target && (
            <button type="button" onClick={() => setTarget(null)}>
              Cancel revision
            </button>
          )}
        </div>
      </form>
      {(index.data?.enabled || index.data?.trained_enabled) && (
        <article className="surface">
          <h3>Optional passage index</h3>
          <p>
            Local character similarity; not a trained semantic model. Rebuild
            after source changes. Search falls back to lexical results when
            unavailable.
          </p>
          {index.data.enabled && (
            <button
              disabled={actions.busy}
              onClick={async () => {
                await actions.act(
                  () =>
                    api(`/workspaces/${workspaceId}/retrieval-index`, {
                      method: "POST",
                    }),
                  "Index requested.",
                );
                index.reload();
              }}
            >
              Build local passage index
            </button>
          )}
          {index.data.trained_enabled && (
            <>
              <p>
                Trained embeddings index current tasks, decisions, documents and
                imported records. Maximum 64 sources per job. Similarity is not
                confidence.
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={includeHistory}
                  onChange={(event) => setIncludeHistory(event.target.checked)}
                />
                Include historical decision revisions
              </label>
              {index.data.external && (
                <label>
                  <input
                    type="checkbox"
                    checked={externalConsent}
                    onChange={(event) =>
                      setExternalConsent(event.target.checked)
                    }
                  />
                  I authorize sending this workspace's indexed source text to
                  the configured external embedding provider. Provider costs may
                  apply.
                </label>
              )}
              <button
                disabled={
                  actions.busy || (index.data.external && !externalConsent)
                }
                onClick={async () => {
                  await actions.act(
                    () =>
                      api(`/workspaces/${workspaceId}/retrieval-index`, {
                        method: "POST",
                        body: {
                          provider: "trained",
                          external_consent: externalConsent,
                          include_historical: includeHistory,
                        },
                      }),
                    "Trained index requested.",
                  );
                  index.reload();
                }}
              >
                Build trained index · owner only
              </button>
            </>
          )}
          {index.data.items.map((item) => (
            <p key={item.id}>
              {item.state} · {item.passage_count} passages · {item.model}
              {item.duration_ms != null
                ? ` · ${item.duration_ms} ms · ${item.input_characters} characters · ${item.usage_tokens} provider tokens`
                : ""}
              {item.error_code ? ` · ${item.error_code}` : ""}
            </p>
          ))}
        </article>
      )}
      {!query.data && !query.error && <p role="status">Loading documents…</p>}
      {query.data?.items.length === 0 && (
        <p>No documents yet. Add project context to make it searchable.</p>
      )}
      {query.data?.items.map((document) => (
        <article className="surface" key={document.id}>
          <h3>{document.title}</h3>
          <p>
            {document.filename} · Version {document.version} ·{" "}
            {document.archived ? "Archived" : document.revisions[0]?.state}
          </p>
          <details>
            <summary>Revision history</summary>
            <ul>
              {document.revisions.map((revision) => (
                <li key={revision.id}>
                  Revision {revision.version}: {revision.state}
                  {revision.error_code ? ` (${revision.error_code})` : ""}
                </li>
              ))}
            </ul>
          </details>
          {!document.archived && (
            <div className="button-row">
              <button
                disabled={actions.busy}
                onClick={() => {
                  setTarget(document);
                  setTitle(document.title);
                }}
              >
                Upload revision
              </button>
              <button
                disabled={actions.busy}
                onClick={() =>
                  onConfirm({
                    title: "Archive document?",
                    message:
                      "All passages, including historical revisions, will become unavailable in search and source previews.",
                    label: "Archive document",
                    action: async () => {
                      const result = await actions.act(
                        () =>
                          api(`${base}/${document.id}/archive`, {
                            method: "POST",
                            body: { version: document.version },
                          }),
                        "Document archived.",
                      );
                      if (result) query.reload();
                    },
                  })
                }
              >
                Archive document
              </button>
            </div>
          )}
        </article>
      ))}
      {query.data && (
        <div className="button-row">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 20))}
          >
            Previous documents
          </button>
          <span>{query.data.total} documents</span>
          <button
            disabled={offset + 20 >= query.data.total}
            onClick={() => setOffset(offset + 20)}
          >
            Next documents
          </button>
        </div>
      )}
    </section>
  );
}
