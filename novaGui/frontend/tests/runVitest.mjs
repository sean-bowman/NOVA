/* ========================================
   VITEST LAUNCHER
   `npm test` starts Vitest through this file. On Windows, Vitest loads a second copy of its own
   runtime when the path it is started from has a lower-case drive letter, as a VS Code or Git
   Bash terminal gives it, and every suite then fails with "Vitest failed to find the current
   suite" (vitest-dev/vitest#11872, open on 5.1). Importing the CLI from its canonical path, which
   carries the drive letter's true case, keeps one copy. Arguments pass through:
   `npm test -- tests/units.test.ts`.
   Sean Bowman [11/27/2026]
   ======================================== */

import { realpathSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';

const cli = fileURLToPath(new URL('../node_modules/vitest/vitest.mjs', import.meta.url));
await import(pathToFileURL(realpathSync.native(cli)).href);
