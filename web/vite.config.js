import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./", // <--- This ./ is the most important part!
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
