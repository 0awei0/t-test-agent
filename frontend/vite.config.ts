import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the built assets resolve correctly when served from the
// stdlib live server at "/" (assets are requested as /assets/...).
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
