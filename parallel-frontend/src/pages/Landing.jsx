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
        The AI Operating System<br />for Remote Teams
      </Motion.h1>

      <Motion.p
        className="landing-subtitle"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
      >
        Parallel OS unifies your company’s knowledge, tasks, updates, and agent workflows — in one clean, powerful workspace.
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
        <h3>AI-Powered Team Insights</h3>
        <p>Your entire team’s progress, code activity, and updates — summarized instantly.</p>
        <div className="preview-bar"></div>
        <div className="preview-bar bar-2"></div>
        <div className="preview-bar bar-3"></div>
      </Motion.div>

    </div>
  );
}
