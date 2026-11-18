/* ========================================
   MATERIAL INFORMATION
   Two notes the Design form shows under a material row, from NOVA's material store on the
   server (novaWeb/design.py):

   MaterialPanel   the wall alloy's sampled properties at a temperature the panel sets:
                   conductivity, density, modulus, yield, expansion and elongation, with the
                   data source. A name the store does not carry falls back to GRCop-42, and the
                   panel says so.
   ExtensionNote   the radiative extension material's temperature limits and the shell
                   properties the store fills, in the Tkinter form's words.
   Sean Bowman [11/17/2026]
   ======================================== */

import { useEffect, useState } from 'react';

import { api } from '../api';
import type { ExtensionEntry, WallSample } from '../types';
import { siUnit, toSI, unitsFor, type UnitTable } from './units';

const measuredNames: Record<string, string> = {
    thermalConductivity: 'conductivity',
    yieldStrength: 'yield',
    cte: 'expansion',
    elongation: 'elongation',
};

interface MaterialPanelProps {
    material: string;
    units: UnitTable;
    visible: boolean;
}

export function MaterialPanel({ material, units, visible }: MaterialPanelProps) {
    const [text, setText] = useState('300');
    const [unit, setUnit] = useState(() => siUnit(units, 'temperature'));
    const [sample, setSample] = useState<WallSample | null>(null);
    const [error, setError] = useState('');

    // The temperature in kelvin, or 300 K while the entry is not a number, as the Tkinter panel reads it
    const typed = Number(text.trim());
    const temperatureK = text.trim() !== '' && Number.isFinite(typed) ? toSI(units, typed, 'temperature', unit) : 300;
    const name = material || 'GRCop-42';

    useEffect(() => {
        if (!visible) {
            return;
        }
        let cancelled = false;
        const timer = window.setTimeout(() => {
            api.wallMaterial(name, Math.max(temperatureK, 1))
                .then((loaded) => {
                    if (!cancelled) {
                        setSample(loaded);
                        setError('');
                    }
                })
                .catch((failure: Error) => !cancelled && setError(failure.message));
        }, 150);
        return () => {
            cancelled = true;
            window.clearTimeout(timer);
        };
    }, [name, temperatureK, visible]);

    const roomOnly = sample
        ? Object.entries(sample.measured).filter(([, measured]) => !measured).map(([key]) => measuredNames[key] ?? key)
        : [];

    return (
        <div className="material-panel" hidden={!visible}>
            <div className="material-heading">
                <span className="eyebrow eyebrow-inline">Sampled properties</span>
                <span className="muted">at</span>
                <input className="input material-temperature" value={text} inputMode="decimal" spellCheck={false}
                       aria-label="Sampling temperature" onChange={(event) => setText(event.target.value)} />
                <select className="input input-unit" value={unit} aria-label="Sampling temperature unit"
                        onChange={(event) => setUnit(event.target.value)}>
                    {unitsFor(units, 'temperature').map((candidate) => <option key={candidate}>{candidate}</option>)}
                </select>
            </div>
            {error && <div className="material-note form-note-error">Material data unavailable: {error}</div>}
            {sample && !error && (
                <>
                    <dl className="material-values">
                        <div><dt>Conductivity</dt><dd>{sample.thermalConductivity.toFixed(0)} <span>W/m-K</span></dd></div>
                        <div><dt>Density</dt><dd>{sample.density.toFixed(0)} <span>kg/m³</span></dd></div>
                        <div><dt>Modulus</dt><dd>{(sample.elasticModulus / 1e9).toFixed(0)} <span>GPa</span></dd></div>
                        <div><dt>Yield</dt><dd>{(sample.yieldStrength / 1e6).toFixed(0)} <span>MPa</span></dd></div>
                        <div><dt>Expansion</dt><dd>{(sample.cte * 1e6).toFixed(1)} <span>10⁻⁶/K</span></dd></div>
                        <div><dt>Elongation</dt><dd>{sample.elongation.toFixed(0)} <span>%</span></dd></div>
                    </dl>
                    {sample.fallback ? (
                        <div className="material-note label-warn">
                            '{name}' is not in the database; showing GRCop-42. {sample.source}
                        </div>
                    ) : (
                        <div className="material-note">
                            Resolved as {sample.material} at {sample.temperatureK.toFixed(0)} K: {sample.source}
                        </div>
                    )}
                    {roomOnly.length > 0 && (
                        <div className="material-note">
                            The store holds a room-temperature {roomOnly.join(', ')} only, shown at any temperature.
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

interface ExtensionNoteProps {
    material: string | null;
    visible: boolean;
}

export function ExtensionNote({ material, visible }: ExtensionNoteProps) {
    const [entry, setEntry] = useState<{ name: string; value: ExtensionEntry } | null>(null);

    useEffect(() => {
        if (!visible || !material) {
            return;
        }
        let cancelled = false;
        api.extensionMaterial(material)
            .then((loaded) => !cancelled && setEntry({ name: material, value: loaded }))
            .catch(() => undefined);
        return () => {
            cancelled = true;
        };
    }, [material, visible]);

    const shown = visible && material && entry?.name === material;
    return <div className="form-note" hidden={!shown}>{shown ? entry.value.note : ''}</div>;
}
