/* ========================================
   VITE CONFIGURATION
   The dev server proxies /api to the NOVA API started with `python -m novaWeb --api`.
   The build lands in dist/, which the NOVA server serves.
   Sean Bowman [11/16/2026]
   ======================================== */

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        strictPort: true,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8765',
            },
        },
    },
    build: {
        outDir: 'dist',
        // plotly.js is about 3.5 MB minified and loads in its own chunk on the first figure
        chunkSizeWarningLimit: 5000,
    },
});
