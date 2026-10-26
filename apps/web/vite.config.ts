import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const apiTarget = process.env.NAZAR_API_PROXY_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The 3D viewer is lazy-loaded; pre-bundle its deps at startup so Vite never
  // re-optimizes and reloads the page the first time the viewer chunk is requested.
  optimizeDeps: { include: ['three', '@react-three/fiber', '@react-three/drei'] },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: false, ws: true },
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
});
