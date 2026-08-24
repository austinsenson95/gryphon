import path from "path"
import fs from "fs"
import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"

// https://vite.dev/config/
const tlsCert = process.env.GRIFFIN_TLS_CERT_FILE
const tlsKey = process.env.GRIFFIN_TLS_KEY_FILE
const backendProxyTarget = process.env.GRIFFIN_BACKEND_PROXY_TARGET ?? "http://127.0.0.1:8000"
const websocketProxyTarget = backendProxyTarget.replace(/^http/, "ws")

export default defineConfig({
  plugins: [react()],
  server: {
    fs: { allow: [path.resolve(__dirname, "..")] },
    https: tlsCert && tlsKey ? {
      cert: fs.readFileSync(tlsCert),
      key: fs.readFileSync(tlsKey),
    } : undefined,
    proxy: {
      "/api": { target: backendProxyTarget, changeOrigin: true },
      "/ws": { target: websocketProxyTarget, ws: true },
    },
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
