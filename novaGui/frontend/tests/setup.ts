/* ========================================
   TEST SETUP
   Each test starts on an empty page: what a test renders is removed after it.
   Sean Bowman [11/27/2026]
   ======================================== */

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
    cleanup();
});
