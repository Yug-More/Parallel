import { useTheme } from "../context/theme-state";

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button onClick={toggleTheme} className="theme-toggle-btn">
      {theme === "dark" ? "☀️ Light" : "🌙 Dark"}
    </button>
  );
}
