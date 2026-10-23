import ThemeToggle from "../components/ThemeToggle";
import "./Landing.css";

export default function Landing({ goLogin }) {
  return (
    <main className="landing-wrapper">
      <header className="landing-header">
        <strong>Parallel</strong>
        <ThemeToggle />
      </header>
      <section className="landing-intro">
        <p className="landing-eyebrow">
          A shared record of how work moves forward
        </p>
        <h1>
          Your project.
          <br />
          Its decisions.
          <br />A clear way back.
        </h1>
        <p className="landing-subtitle">
          Bring conversations, tasks, and source-linked decisions into one
          private workspace. Return to what changed, inspect the evidence, and
          prepare a handoff you can verify.
        </p>
        <button onClick={goLogin} className="cta-button">
          Enter Dashboard →
        </button>
        <p className="landing-note">
          Collaboration and local intelligence work without AI provider
          credentials.
        </p>
      </section>
      <section
        className="landing-capabilities"
        aria-label="Product capabilities"
      >
        <article>
          <span>01 / Collaborate</span>
          <h2>Work with explicit access.</h2>
          <p>
            Invite registered teammates, assign persistent tasks, manage
            prerequisites, and keep project conversations together.
          </p>
        </article>
        <article>
          <span>02 / Remember</span>
          <h2>Preserve the reasoning.</h2>
          <p>
            Link decisions to actual records. Inspect revisions, follow
            replacements, and find current evidence through deterministic
            search.
          </p>
        </article>
        <article>
          <span>03 / Coordinate</span>
          <h2>Review what really ran.</h2>
          <p>
            Local agents compute status and dependency reports, coordinate a
            handoff, and request owner approval before publishing it.
          </p>
        </article>
      </section>
      <footer className="landing-footer">
        Private workspaces · Inspectable sources · Durable local execution
      </footer>
    </main>
  );
}
