import { useState } from "react";
import { api } from "../api";
import { SourceLink, SourceViewer } from "./ProjectSources";
import { useProjectAction, useWorkspaceQuery } from "./projectHooks";

export default function AnswersPanel({ workspaceId, onAccessLost }) {
  const base = `/workspaces/${workspaceId}/answers`;
  const [question, setQuestion] = useState("");
  const [retrievalMode, setRetrievalMode] = useState("lexical");
  const [externalConsent, setExternalConsent] = useState(false);
  const [mode, setMode] = useState("extractive");
  const [source, setSource] = useState(null);
  const query = useWorkspaceQuery(base, workspaceId, onAccessLost, 5000);
  const actions = useProjectAction(workspaceId, onAccessLost);
  async function ask(event) {
    event.preventDefault();
    if (
      await actions.act(
        () =>
          api(base, {
            method: "POST",
            body: {
              question,
              mode,
              retrieval_mode: retrievalMode,
              external_consent: externalConsent,
              idempotency_key: crypto.randomUUID(),
            },
          }),
        "Answer saved with its evidence references.",
      )
    )
      query.reload();
  }
  return (
    <section className="project-section" aria-label="Grounded answers">
      <div className="section-heading">
        <div>
          <h2>Ask the workspace</h2>
          <p>
            Find matching evidence, inspect citations, and keep source excerpts
            separate from model interpretation.
          </p>
        </div>
      </div>
      {(actions.error || query.error) && (
        <p role="alert">{actions.error || query.error}</p>
      )}
      {actions.notice && <p role="status">{actions.notice}</p>}
      <form className="surface project-form" onSubmit={ask}>
        <label>
          Project question
          <input
            required
            minLength={3}
            maxLength={200}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </label>
        <label>
          Evidence retrieval
          <select
            value={retrievalMode}
            onChange={(event) => setRetrievalMode(event.target.value)}
          >
            <option value="lexical">
              Lexical with explicit blocker/change scope
            </option>
            <option value="trained">
              Optional trained hybrid with lexical fallback
            </option>
          </select>
        </label>
        {retrievalMode === "trained" && (
          <label>
            <input
              type="checkbox"
              checked={externalConsent}
              onChange={(event) => setExternalConsent(event.target.checked)}
            />
            Authorize sending this question to the external embedding provider
            if configured. Owner access and provider costs may apply.
          </label>
        )}
        <label>
          Answer mode
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="extractive">Matching source excerpts · local</option>
            {query.data?.model_enabled && (
              <option value="model">
                Model interpretation · configured paid provider
              </option>
            )}
          </select>
        </label>
        <p>
          Lexical retrieval may miss different wording or return partial
          matches. Excerpts do not establish that a source is correct. No
          matching evidence means abstention.
        </p>
        <button disabled={actions.busy}>
          {actions.busy ? "Finding evidence…" : "Ask with evidence"}
        </button>
      </form>
      {!query.data && !query.error && (
        <p role="status">Loading answer history…</p>
      )}
      {query.data?.items.length === 0 && <p>No saved questions yet.</p>}
      {query.data?.items.map((answer) => (
        <article className="surface" key={answer.id}>
          <h3>{answer.question}</h3>
          {answer.evidence_plan && (
            <p>
              Evidence scope: {answer.evidence_plan.scope} ·{" "}
              {answer.evidence_plan.strategy}
            </p>
          )}
          <p>
            {answer.mode === "model"
              ? "Model interpretation"
              : "Source excerpts"}{" "}
            · {answer.state.replaceAll("_", " ")}
          </p>
          {answer.state === "abstained" && (
            <p>
              No sufficient matching evidence was found. Try more specific
              project terms.
            </p>
          )}
          {answer.state === "evidence_unavailable" && (
            <p>
              Source evidence changed, was archived, or its connection was
              revoked. The saved answer is hidden; ask again for current
              evidence.
            </p>
          )}
          {answer.error_code && (
            <p role="status">
              {answer.error_code.replaceAll("_", " ")}. You can ask again with a
              new request.
            </p>
          )}
          {answer.warnings?.map((warning) => (
            <p className="feedback" key={warning}>
              {warning}
            </p>
          ))}
          {answer.claims.map((claim, index) => (
            <div key={index}>
              <p className="muted">
                {answer.mode === "extractive" ? "Source quotation" : claim.kind}
              </p>
              <blockquote className="source-body">{claim.text}</blockquote>
              <div className="button-row">
                {claim.citations.map((ref) => {
                  const item = answer.evidence.find((item) => item.ref === ref);
                  return item ? (
                    <SourceLink key={ref} source={item} onOpen={setSource} />
                  ) : null;
                })}
              </div>
            </div>
          ))}
          <p className="muted">{answer.note}</p>
        </article>
      ))}
      <SourceViewer
        source={source}
        workspaceId={workspaceId}
        onAccessLost={onAccessLost}
        onClose={() => setSource(null)}
        onNavigate={setSource}
      />
    </section>
  );
}
