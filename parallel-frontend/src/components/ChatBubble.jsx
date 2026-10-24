import "./ChatBubble.css";

// A deliberately small, text-only Markdown subset. React escapes all source
// text; no HTML, images, embedded content, or arbitrary URL schemes are parsed.
function inline(text) {
  return text
    .split(/(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))/g)
    .map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**"))
        return <strong key={index}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("`") && part.endsWith("`"))
        return <code key={index}>{part.slice(1, -1)}</code>;
      const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      if (link)
        return (
          <a key={index} href={link[2]} target="_blank" rel="noreferrer">
            {link[1]}
          </a>
        );
      return part;
    });
}

export default function ChatBubble({ sender, text }) {
  const blocks = [];
  const lines = text.replaceAll("\r\n", "\n").split("\n");
  let paragraph = [];
  function flush() {
    if (paragraph.length) {
      blocks.push(<p key={blocks.length}>{inline(paragraph.join("\n"))}</p>);
      paragraph = [];
    }
  }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("```")) {
      flush();
      const language = line.slice(3).trim();
      const code = [];
      while (++i < lines.length && !lines[i].startsWith("```"))
        code.push(lines[i]);
      blocks.push(
        <div className="code-block" key={blocks.length}>
          {language && <span className="code-language">{language}</span>}
          <pre
            tabIndex={0}
            aria-label={language ? `${language} code` : "Code block"}
          >
            <code>{code.join("\n")}</code>
          </pre>
        </div>,
      );
    } else if (!line.trim()) {
      flush();
    } else if (/^#{1,6} /.test(line)) {
      flush();
      blocks.push(
        <p className="message-heading" key={blocks.length}>
          {inline(line.replace(/^#{1,6} /, ""))}
        </p>,
      );
    } else if (/^[-*] /.test(line)) {
      flush();
      const items = [];
      do {
        items.push(lines[i].slice(2));
        i++;
      } while (i < lines.length && /^[-*] /.test(lines[i]));
      i--;
      blocks.push(
        <ul key={blocks.length}>
          {items.map((item, j) => (
            <li key={j}>{inline(item)}</li>
          ))}
        </ul>,
      );
    } else paragraph.push(line);
  }
  flush();
  return (
    <div
      className={`chat-bubble ${sender === "user" ? "user-bubble" : "ai-bubble"}`}
    >
      {blocks}
    </div>
  );
}
