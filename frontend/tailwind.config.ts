import type { Config } from "tailwindcss";
import formsPlugin from "@tailwindcss/forms";

// Design tokens per ADR-015 decision 5 ("the reference archive," not a
// generic AI-product look): cool ink-slate on cool paper-white, with a
// single narrowly-scoped amber accent reserved for citations only.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#1B2430",
          50: "#F3F4F6",
          100: "#E4E7EB",
          300: "#9AA4B2",
          500: "#5B6472",
          700: "#323C4A",
          900: "#1B2430",
        },
        paper: {
          DEFAULT: "#F7F5F0",
          dim: "#EDEAE2",
        },
        amber: {
          DEFAULT: "#C9932E",
          dim: "#F1E2C2",
          deep: "#8F6A1F",
        },
        forest: {
          DEFAULT: "#3D7A5C",
          dim: "#DCEBE3",
        },
        brick: {
          DEFAULT: "#B23A34",
          dim: "#F5DEDC",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        body: ["var(--font-body)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        lg: "10px",
      },
    },
  },
  plugins: [formsPlugin],
};

export default config;
