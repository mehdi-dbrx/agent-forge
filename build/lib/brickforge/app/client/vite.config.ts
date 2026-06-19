import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const shikiStub = path.resolve(__dirname, './src/stubs/shiki.ts');
const langStub = path.resolve(__dirname, './src/stubs/shiki-lang.ts');
const cssStub = path.resolve(__dirname, './src/stubs/empty.css');

const shikiLangs = ['bash','css','go','html','javascript','json','jsx','markdown','python','shellscript','sql','toml','tsx','typescript','yaml'];

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // Stub heavy deps to reduce bundle (16MB -> ~2MB)
      'shiki/engine/javascript': shikiStub,
      ...Object.fromEntries(shikiLangs.map(l => [`shiki/langs/${l}.mjs`, langStub])),
      'shiki': shikiStub,
      'mermaid': shikiStub,
      'cytoscape': shikiStub,
      'katex/dist/katex.min.css': cssStub,
      'katex': shikiStub,
    },
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
