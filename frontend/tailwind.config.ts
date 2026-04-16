import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#09111f",
        mist: "#eef4ff",
        signal: "#5eead4",
        ember: "#fb7185",
        gold: "#fbbf24"
      },
      boxShadow: {
        panel: "0 24px 80px rgba(6, 16, 35, 0.22)"
      },
      backgroundImage: {
        grid:
          "linear-gradient(rgba(148, 163, 184, 0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px)"
      }
    }
  },
  plugins: []
};

export default config;
