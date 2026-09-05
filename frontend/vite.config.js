import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/annotated": "http://localhost:8000",
      "/static": "http://localhost:8000",
      "/crops": "http://localhost:8000",
    },
  },
});
