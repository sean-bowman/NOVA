/* ========================================
   VITE CONFIGURATION
   The dev server proxies /api to the NOVA API started with `python -m novaGui --api`.
   The build lands in dist/, which the NOVA server serves and the repository carries, so the GUI
   runs from a checkout without Node.

   The build stamps dist/buildStamp.json with a hash of every file it reads (`stampInputs`):
   SHA-256 over each file's path relative to this folder, in sorted order, each followed by a
   newline, the file's bytes with CRLF read as LF, and a newline. tests/testFrontendBuild.py
   hashes the sources the same way and fails when they no longer match the stamp, so a change to
   the front end cannot be committed without the build it makes.
   Sean Bowman [11/16/2026]
   ======================================== */

/// <reference types="node" />

import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

// What the build reads: a change to any of these changes what dist/ should hold
const stampInputs = ['index.html', 'package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts', 'src'];

function sourceHash(root: string): string {
    const files: string[] = [];
    const walk = (path: string) => {
        if (statSync(path).isDirectory()) {
            readdirSync(path).forEach((name: string) => walk(join(path, name)));
        } else {
            files.push(relative(root, path).split(sep).join('/'));
        }
    };
    stampInputs.forEach((input) => walk(join(root, input)));
    const hash = createHash('sha256');
    for (const file of files.sort()) {
        // latin1 maps each byte to one character, so the CRLF fold is byte for byte
        const text = readFileSync(join(root, file)).toString('latin1').replace(/\r\n/g, '\n');
        hash.update(`${file}\n`, 'latin1');
        hash.update(text, 'latin1');
        hash.update('\n', 'latin1');
    }
    return hash.digest('hex');
}

function buildStamp(): Plugin {
    let root = '';
    let outDir = '';
    return {
        name: 'nova-build-stamp',
        apply: 'build',
        configResolved(config) {
            root = config.root;
            outDir = join(config.root, config.build.outDir);
        },
        closeBundle() {
            const stamp = { sources: sourceHash(root), inputs: stampInputs };
            writeFileSync(join(outDir, 'buildStamp.json'), `${JSON.stringify(stamp, null, 1)}\n`);
        },
    };
}

export default defineConfig({
    plugins: [react(), buildStamp()],
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
