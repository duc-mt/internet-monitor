/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        panel: "var(--color-panel)",
        "panel-alt": "var(--color-panel-alt)",
        border: "var(--color-border)",
        text: "var(--color-text)",
        muted: "var(--color-muted)",
        accent: "var(--color-accent)",
        "accent-soft": "var(--color-accent-soft)",
        healthy: "var(--color-healthy)",
        degraded: "var(--color-degraded)",
        offline: "var(--color-offline)",
        unknown: "var(--color-unknown)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["'JetBrains Mono'", "'SFMono-Regular'", "Consolas", "monospace"],
      },
      borderRadius: {
        card: "10px",
        control: "6px",
      },
    },
  },
  plugins: [],
};
