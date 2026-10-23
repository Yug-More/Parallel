import "./ChatBubble.css";
import { motion as Motion } from "framer-motion";

export default function ChatBubble({ sender, text }) {
  const isUser = sender === "user";

  return (
    <Motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={`chat-bubble ${isUser ? "user-bubble" : "ai-bubble"}`}
    >
      {text}
    </Motion.div>
  );
}
