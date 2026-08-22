import path from "path"
import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    fs: { allow: [path.resolve(__dirname, "..")] },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // Tests live outside the frontend root; resolve test-only deps locally.
      "@testing-library/jest-dom/vitest": path.resolve(
        __dirname,
        "./node_modules/@testing-library/jest-dom/vitest",
      ),
      "@testing-library/react": path.resolve(
        __dirname,
        "./node_modules/@testing-library/react",
      ),
      "@testing-library/user-event": path.resolve(
        __dirname,
        "./node_modules/@testing-library/user-event",
      ),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    include: ["../tests/frontend/**/*.test.{ts,tsx}"],
    setupFiles: [path.resolve(__dirname, "../tests/frontend/setup.ts")],
    css: false,
  },
})
