// Vite: `npm run dev` (desenvolvimento, com proxy para a API do mundo) e
// `npm run build` (gera viewer/dist, que o `python -m server` serve em /viewer).
import { defineConfig } from 'vite';
import { resolve } from 'node:path';

// onde está o `python -m server` durante o `npm run dev`
const api = process.env.DW_API || 'http://localhost:8000';

export default defineConfig({
  base: '/viewer/',
  publicDir: 'public',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // os modelos do João são servidos direto de public/models pelo servidor
    copyPublicDir: true,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      input: {
        index: resolve(import.meta.dirname, 'index.html'),
        layout: resolve(import.meta.dirname, 'layout.html'),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': api,
      '/health': api,
      '/chat': api,
      '/ws': { target: api.replace(/^http/, 'ws'), ws: true },
    },
  },
});
