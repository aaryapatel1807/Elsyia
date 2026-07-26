/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#05050a",
        surface: "#0b0b14",
        accent: "#5eead4",
        "accent-dim": "#2dd4bf33",
      },
      fontFamily: {
        display: ["Sora", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "sans-serif"],
      },
      backdropBlur: { xs: "2px" },
    },
  },
  plugins: [],
};
