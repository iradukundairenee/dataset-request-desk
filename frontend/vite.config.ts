import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` (outside Docker): forward /api to the API on :8000, the same
// way nginx does in the Docker image, so the code always calls "/api/...".
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", rewrite: (path) => path.replace(/^\/api/, "") },
    },
  },
});
