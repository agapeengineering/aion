import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ root: 'apps/web', plugins: [react()], build: { outDir: 'dist', sourcemap: false }, server: { port: 5173, strictPort: true }, preview: { port: 4173, strictPort: true } });
