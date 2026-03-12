"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "vch-theme";

type ThemeMode = "dark" | "light";

function applyTheme(mode: ThemeMode) {
  document.documentElement.dataset.theme = mode;
}

export function ThemeToggle() {
  const [mode, setMode] = useState<ThemeMode>("dark");

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    const nextMode: ThemeMode = saved === "light" ? "light" : "dark";
    setMode(nextMode);
    applyTheme(nextMode);
  }, []);

  function onToggle() {
    const nextMode: ThemeMode = mode === "dark" ? "light" : "dark";
    setMode(nextMode);
    applyTheme(nextMode);
    window.localStorage.setItem(STORAGE_KEY, nextMode);
  }

  return (
    <button type="button" className="theme-toggle" onClick={onToggle} aria-label="Toggle theme">
      <span className="theme-toggle-track">
        <span className="theme-toggle-thumb">{mode === "dark" ? "Dark" : "Light"}</span>
      </span>
    </button>
  );
}
