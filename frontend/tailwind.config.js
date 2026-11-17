/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // Dark mode is opt-in via the header toggle (`.dark` on <html>, see src/lib/colors.ts).
  darkMode: "class",
  theme: { extend: {} },
  plugins: [],
};
