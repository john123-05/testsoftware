import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base './': die App laeuft spaeter aus einem Ordner (Liftpictures Display, WebView2) und als Demo.
export default defineConfig({ base: './', plugins: [react()], build: { outDir: 'dist', assetsInlineLimit: 0 } });
