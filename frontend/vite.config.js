import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the API runs on 127.0.0.1:8001; the proxy keeps everything same-origin (no CORS).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8001" },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
    include: ["src/**/*.test.{js,jsx}"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{js,jsx}"],
      exclude: ["src/test/**", "src/main.jsx"],
      reporter: ["text-summary", "json-summary"],
      thresholds: { lines: 85, statements: 85, functions: 80, branches: 70 },
    },
  },
});
