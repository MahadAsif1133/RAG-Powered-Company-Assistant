import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        brand: {
          50: "hsl(222, 100%, 97%)",
          100: "hsl(222, 96%, 93%)",
          200: "hsl(222, 90%, 84%)",
          300: "hsl(222, 80%, 72%)",
          400: "hsl(222, 72%, 60%)",
          500: "hsl(222, 68%, 50%)",
          600: "hsl(222, 74%, 42%)",
          700: "hsl(222, 78%, 34%)",
          800: "hsl(222, 80%, 26%)",
          900: "hsl(222, 82%, 18%)",
          950: "hsl(222, 86%, 11%)",
        },
        surface: {
          DEFAULT: "hsl(222, 20%, 10%)",
          card: "hsl(222, 18%, 14%)",
          elevated: "hsl(222, 16%, 18%)",
          border: "hsl(222, 14%, 22%)",
        },
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
