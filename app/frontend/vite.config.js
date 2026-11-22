import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build straight into app/static so FastAPI serves it: "/" -> static/index.html, assets under /static/.
export default defineConfig({
  plugins: [react()],
  base: "/static/",
  build: { outDir: "../static", emptyOutDir: true, assetsDir: "assets" },
  server: {
    proxy: { "/api": "http://localhost:8765", "/india.geojson": "http://localhost:8765" },
  },
});
