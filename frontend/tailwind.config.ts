import type { Config } from "tailwindcss";

export default {
  content: ["./pages/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  prefix: "",
  theme: {
    extend: {
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "'SF Pro Display'", "system-ui", "sans-serif"],
      },
      colors: {
        apple: {
          bg: "#ffffff",
          surface: "#f5f5f7",
          card: "#fbfbfd",
          blue: "#0071e3",
          text: "#1d1d1f",
          secondary: "#6e6e73",
          hover: "#ebebed",
          input: "#f5f5f5",
          divider: "#e5e5ea",
          red: "#ff3b30",
          green: "#34c759",
          amber: "#f59e0b",
          "btn-secondary": "#e8e8ed",
        },
      },
      borderRadius: {
        apple: "18px",
        "apple-sm": "14px",
        pill: "980px",
      },
      boxShadow: {
        apple: "0 2px 12px rgba(0, 0, 0, 0.08)",
        "apple-lg": "0 4px 20px rgba(0, 0, 0, 0.10)",
        "apple-focus": "0 0 0 3px rgba(0, 113, 227, 0.3)",
      },
      animation: {
        "pulse-dot": "pulse-dot 1.5s ease-in-out infinite",
        "pulse-ring": "pulse-ring 1.5s ease-out infinite",
        "fade-in": "fade-in 0.6s ease-in-out both",
        "roll-in": "roll-in 0.5s cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  plugins: [],
} satisfies Config;
