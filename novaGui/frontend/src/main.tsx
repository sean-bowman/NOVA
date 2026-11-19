/* ========================================
   ENTRY
   Mounts the NOVA app, or a popped-out figure window when the page is opened as one. The
   palette, the wordmark face and the app styles load here.
   Sean Bowman [11/16/2026]
   ======================================== */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import '@fontsource/share-tech-mono/400.css';
import './styles/palette.css';
import './styles/app.css';

import { App } from './App';
import { Popout, popoutParams } from './Popout';

const popout = popoutParams();

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        {popout ? <Popout initial={popout} /> : <App />}
    </StrictMode>,
);
