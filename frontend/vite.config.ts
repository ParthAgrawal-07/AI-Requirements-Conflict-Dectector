import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // needed so the dev server is reachable from outside the Docker container
    port: 5173,
  },
});
