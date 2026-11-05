import { existsSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const demo = fileURLToPath(new URL('./public/demo', import.meta.url));
const photos = existsSync(demo) ? readdirSync(demo, { withFileTypes: true })
  .filter((file) => file.isFile() && /\.jpe?g$/i.test(file.name))
  .map((file) => 'demo/' + encodeURIComponent(file.name)) : [];

// base './': die App laeuft spaeter aus einem Ordner (Liftpictures Display, WebView2) und als Demo.
export default defineConfig({ base: './', define: { __DEMO_PHOTOS__: JSON.stringify(photos) }, plugins: [react()], build: { outDir: 'dist', assetsInlineLimit: 0 } });
