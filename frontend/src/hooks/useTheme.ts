import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";

// The theme is the only thing the app keeps in localStorage (docs/design-app.md). Light is
// the default; a saved "dark" choice is kept.
const STORAGE_KEY = "mantle.theme";

function stored(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(stored);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Private windows can refuse storage; the theme still works for this visit.
    }
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }, []);
  return [theme, toggle];
}
