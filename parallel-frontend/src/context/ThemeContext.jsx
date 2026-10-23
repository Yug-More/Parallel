import { useState, useEffect } from "react";

import { ThemeContext } from "./theme-state";

export function ThemeProvider({ children }) {
  // Read theme from global variable OR fallback to light
  const initial = window.__PARALLEL_THEME || "light";

  const [theme, setTheme] = useState(initial);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.__PARALLEL_THEME = theme; // store globally to avoid overrides
  }, [theme]);

  function toggleTheme() {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  }

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
