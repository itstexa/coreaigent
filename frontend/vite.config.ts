import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const proxy = (target: string, authorization?: string) => ({
  target,
  changeOrigin: true,
  rewrite: (path: string) => path.replace(/^\/api\/[^/]+/, ""),
  headers: authorization ? { Authorization: authorization } : undefined,
});

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/real": proxy("http://localhost:8080"),
      "/api/ocr": proxy("http://localhost:8081"),
      "/api/classification": proxy("http://localhost:8082"),
      "/api/validation": proxy("http://localhost:8083"),
      "/api/validation-user": proxy("http://localhost:8083", "Bearer f03-demo-token"),
      "/api/workflow-user": proxy("http://localhost:8086", "Bearer f03-demo-token"),
      "/api/workflow-admin": proxy("http://localhost:8086", "Bearer f06-demo-admin-token"),
    },
  },
});
