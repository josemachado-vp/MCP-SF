/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: "#1B2D4F",
          dark: "#0F1B33",
        },
        "gray-secondary": "#8A8D8F",
        "bg-soft": "#F7F8FA",
        success: "#0E8F5E",
        danger: "#B42318",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
