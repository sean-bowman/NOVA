/* ========================================
   VITEST CONFIGURATION
   The front end's unit tests (`npm test`), in tests/. They run in jsdom, which stands in for
   the window, so a component renders and takes input without a browser. The tests sit outside
   src/ and this file outside the build's stamp inputs (vite.config.ts): neither is part of what
   the build makes, so a change to a test does not call for a new build.
   Sean Bowman [11/27/2026]
   ======================================== */

import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    test: {
        include: ['tests/**/*.test.{ts,tsx}'],
        environment: 'jsdom',
        setupFiles: ['tests/setup.ts'],
    },
});
