/* Shared dark/light theme toggle. Persists choice in localStorage and
   respects the user's OS preference the first time they visit. */

(function () {
  const STORAGE_KEY = "nexlyticx-theme";

  function getPreferredTheme() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }

  // Apply immediately (before paint) to avoid a light-mode flash.
  applyTheme(getPreferredTheme());

  window.addEventListener("DOMContentLoaded", () => {
    const toggles = document.querySelectorAll(".theme-toggle");
    toggles.forEach((btn) => {
      btn.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme");
        applyTheme(current === "dark" ? "light" : "dark");
        document.dispatchEvent(new CustomEvent("nx:themechange"));
      });
    });
  });
})();
