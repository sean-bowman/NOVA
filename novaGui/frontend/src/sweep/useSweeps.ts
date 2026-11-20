/* ========================================
   SWEEPS
   The trade sweeps the server keeps (novaGui.sweeps), fetched again whenever the event stream
   says a sweep or the kept runs changed: a point started or ended, a sweep was added or deleted,
   or one of its runs was deleted or named.
   Sean Bowman [11/20/2026]
   ======================================== */

import { useEffect, useRef, useState } from 'react';

import { api } from '../api';
import type { RunView } from '../run/useRunEvents';
import type { SweepList } from '../types';

export function useSweeps(run: RunView, onError?: (title: string, message: string) => void): SweepList | null {
    const [list, setList] = useState<SweepList | null>(null);
    const request = useRef(0);
    const errorHandler = useRef(onError);
    errorHandler.current = onError;

    useEffect(() => {
        const asked = ++request.current;
        api.sweeps()
            .then((loaded) => asked === request.current && setList(loaded))
            .catch((failure: Error) => errorHandler.current?.('Sweeps unavailable', failure.message));
    }, [run.sweepsVersion, run.runsVersion]);

    return list;
}
