import { motion as Motion } from "framer-motion";
import "./Landing.css";

export default function Landing({ goLogin }) {
  return (
    <div className="landing-wrapper">

      {/* Background Animated Gradient */}
      <div className="gradient-bg"></div>

      {/* Floating Orbs */}
      <div className="orb orb-1"></div>
      <div className="orb orb-2"></div>
      <div className="orb orb-3"></div>

      <Motion.h1
        className="landing-title"
        initial={{ opacity: 0, y: -40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7 }}
      >
        A Persistent Workspace<br />for Project Teams
      </Motion.h1>

      <Motion.p
        className="landing-subtitle"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
      >
        Keep project conversations and collaborators together in private workspaces. Return to saved context when you are ready to continue.
      </Motion.p>

      <Motion.button
        onClick={goLogin}
        className="cta-button"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        Enter Dashboard →
      </Motion.button>

      {/* Product Preview Card */}
      <Motion.div
        className="preview-card glass"
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5, duration: 0.6 }}
      >
        <h3>Shared Project Conversations</h3>
        <p>Workspace membership controls access to your conversations. Tasks and decision tracking are planned for later phases.</p>
        <div className="preview-bar"></div>
        <div className="preview-bar bar-2"></div>
        <div className="preview-bar bar-3"></div>
      </Motion.div>

    </div>
  );
}
