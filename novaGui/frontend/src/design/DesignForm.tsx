/* ========================================
   DESIGN FORM
   The left of the window, beside the result pane. Every config key, grouped into collapsible
   sections in the order of the shipped
   NOVANozzle.json. Each section leads with the fields a design is made from and folds the rest
   into Advanced settings or a named fold. Rows the config makes irrelevant are hidden by the
   schema's own predicates, evaluated on the server. A search box and a changed-only filter
   narrow the form; a copper dot marks a value that differs from the shipped nozzle.

   The server's cross-field checks (novaGui/design.py) show in a strip above the form, and
   the rows they name are marked in amber with the problem written under them; they warn rather
   than block. The wall material row carries a panel of the alloy's sampled properties, and the
   extension material row a note of what the material store holds. Choosing an extension
   material fills the shell properties the store carries.

   An outline of the sections stays in view beside the form when it is wide, and above it as a
   row of sections when it is narrow. Each entry counts its section's changed fields, problems and
   fields to fix, marks the section the form is scrolled to, and opens and scrolls to its
   section on a click.
   Sean Bowman [11/16/2026]
   ======================================== */

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../api';
import { NozzleGlyph, ResetIcon, SearchIcon } from '../components/Icons';
import type { Config, ConfigValue, FormState, GroupSpec, ItemSpec, Schema } from '../types';
import { FieldRow } from './FieldRow';
import { ExtensionNote, MaterialPanel } from './MaterialInfo';
import { SelectorRow } from './SelectorRow';
import { blocksOf, isChanged, matchesSearch } from './formModel';

interface DesignFormProps {
    schema: Schema;
    config: Config;
    formVersion: number;
    formState: FormState;
    errors: Record<string, string>;
    onPatch: (patch: Config) => void;
    onError: (id: string, message: string | null) => void;
    onReset: () => void;
    onLoadExample: (name: string) => void;
    onSave: () => void;
}

export function DesignForm({ schema, config, formVersion, formState, errors, onPatch, onError, onReset, onLoadExample,
                             onSave }: DesignFormProps) {
    const [query, setQuery] = useState('');
    const [changedOnly, setChangedOnly] = useState(false);
    const [openSections, setOpenSections] = useState<Record<string, boolean>>(
        () => Object.fromEntries(schema.groups.map((group) => [group.id, !group.collapsed])));
    const [openFolds, setOpenFolds] = useState<Record<string, boolean>>({});
    const [current, setCurrent] = useState(schema.groups[0]?.id ?? '');
    const scroller = useRef<HTMLDivElement>(null);
    const outline = useRef<HTMLElement>(null);
    const jumped = useRef('');          // the section an outline click scrolled to, until the user scrolls

    // A section whose expandWhen predicate turns true opens itself, once, as in the legacy Tkinter form
    const previousExpand = useRef<Set<string>>(new Set(formState.expand));
    useEffect(() => {
        const opened = formState.expand.filter((id) => !previousExpand.current.has(id));
        previousExpand.current = new Set(formState.expand);
        if (opened.length > 0) {
            setOpenSections((previous) => ({ ...previous, ...Object.fromEntries(opened.map((id) => [id, true])) }));
        }
    }, [formState.expand]);

    const hidden = useMemo(() => new Set(formState.hidden), [formState.hidden]);
    const flagged = useMemo(() => new Set(formState.flagged), [formState.flagged]);
    const search = query.trim().toLowerCase();
    const filtering = search !== '' || changedOnly;

    const rowVisible = (item: ItemSpec) =>
        !hidden.has(item.id) && matchesSearch(item, search) && (!changedOnly || isChanged(item, config, schema.defaults));

    const changedCount = useMemo(() => schema.groups.reduce((count, group) =>
        count + group.items.filter((item) => !(item.type === 'field' && item.hidden)
            && isChanged(item, config, schema.defaults)).length, 0), [schema, config]);

    // Per section: fields changed from the shipped nozzle, problems to check, entries to fix
    const counts = useMemo(() => Object.fromEntries(schema.groups.map((group) => [group.id, {
        changes: group.items.filter((item) => !(item.type === 'field' && item.hidden)
            && isChanged(item, config, schema.defaults)).length,
        errors: group.items.filter((item) => errors[item.id]).length,
        flags: group.items.filter((item) => flagged.has(item.id) && !errors[item.id]).length,
    }])), [schema, config, errors, flagged]);

    // -- The outline marks the section at the top of the scrolled form -- //
    useEffect(() => {
        const element = scroller.current;
        if (!element) {
            return;
        }
        let frame = 0;
        const follow = () => {
            window.cancelAnimationFrame(frame);
            frame = window.requestAnimationFrame(() => {
                const top = element.getBoundingClientRect().top + 24;
                // A section near the end cannot scroll to the top; the one clicked stays marked while in view
                const target = jumped.current
                    ? element.querySelector<HTMLElement>(`section[data-section="${jumped.current}"]`) : null;
                if (target && target.getBoundingClientRect().top < element.getBoundingClientRect().bottom) {
                    setCurrent(jumped.current);
                    return;
                }
                let found = '';
                for (const section of element.querySelectorAll<HTMLElement>('section[data-section]')) {
                    if (section.hidden) {
                        continue;
                    }
                    if (!found || section.getBoundingClientRect().top <= top) {
                        found = section.dataset.section ?? found;
                    }
                }
                if (found) {
                    setCurrent(found);
                }
            });
        };
        const release = () => {
            jumped.current = '';
        };
        element.addEventListener('scroll', follow, { passive: true });
        element.addEventListener('wheel', release, { passive: true });
        element.addEventListener('pointerdown', release);
        element.addEventListener('keydown', release);
        follow();
        return () => {
            element.removeEventListener('scroll', follow);
            element.removeEventListener('wheel', release);
            element.removeEventListener('pointerdown', release);
            element.removeEventListener('keydown', release);
            window.cancelAnimationFrame(frame);
        };
    }, [formVersion]);

    // In the narrow row the marked section stays in view
    useEffect(() => {
        const chip = outline.current?.querySelector<HTMLElement>('.outline-item.is-current');
        const row = outline.current;
        if (chip && row && row.scrollWidth > row.clientWidth) {
            row.scrollTo({ left: chip.offsetLeft - row.clientWidth / 2 + chip.clientWidth / 2, behavior: 'smooth' });
        }
    }, [current]);

    const jumpTo = useCallback((groupId: string) => {
        setOpenSections((previous) => ({ ...previous, [groupId]: true }));
        setCurrent(groupId);
        jumped.current = groupId;
        window.requestAnimationFrame(() => {
            scroller.current?.querySelector<HTMLElement>(`section[data-section="${groupId}"]`)
                ?.scrollIntoView({ block: 'start', behavior: 'smooth' });
        });
    }, []);

    // Choosing an extension material fills the shell properties the store carries for it
    const fillExtension = (value: ConfigValue) => {
        if (typeof value !== 'string' || !value) {
            return;
        }
        api.extensionMaterial(value)
            .then((entry) => Object.keys(entry.fill).length > 0 && onPatch(entry.fill))
            .catch(() => undefined);
    };

    const renderItem = (item: ItemSpec) => {
        const visible = rowVisible(item);
        const changed = isChanged(item, config, schema.defaults);
        if (item.type === 'selector') {
            return <SelectorRow key={item.id} selector={item} config={config} units={schema.units} visible={visible}
                                changed={changed} error={errors[item.id] ?? null} flagged={flagged.has(item.id)}
                                notes={formState.notes?.[item.id]} onChange={onPatch} onError={onError} />;
        }
        const row = (
            <FieldRow spec={item} value={config[item.key] ?? null} defaultValue={schema.defaults[item.key] ?? null}
                      units={schema.units} visible={visible} changed={changed} error={errors[item.id] ?? null}
                      flagged={flagged.has(item.id)} notes={formState.notes?.[item.id]} onChange={onPatch} onError={onError}
                      onChoose={item.key === 'extensionMaterial' ? fillExtension : undefined} />
        );
        if (item.key === 'material') {
            return (
                <Fragment key={item.id}>
                    {row}
                    <MaterialPanel material={String(config.material ?? '')} units={schema.units} visible={visible} />
                </Fragment>
            );
        }
        if (item.key === 'extensionMaterial') {
            const material = typeof config.extensionMaterial === 'string' ? config.extensionMaterial : null;
            return (
                <Fragment key={item.id}>
                    {row}
                    <ExtensionNote material={material} visible={visible} />
                </Fragment>
            );
        }
        return <Fragment key={item.id}>{row}</Fragment>;
    };

    const renderSection = (group: GroupSpec) => {
        const blocks = blocksOf(group);
        const anyVisible = blocks.some((block) =>
            block.kind === 'item' ? rowVisible(block.item) : block.items.some(rowVisible));
        const sectionHidden = hidden.has(group.id) || (filtering && !anyVisible);
        const open = filtering || openSections[group.id];
        const { changes: sectionChanges, errors: sectionErrors, flags: sectionFlags } = counts[group.id];

        return (
            <section key={group.id} className={`card section ${open ? 'is-open' : ''}`} hidden={sectionHidden}
                     data-section={group.id}>
                <button type="button" className="section-header" aria-expanded={open}
                        onClick={() => setOpenSections((previous) => ({ ...previous, [group.id]: !previous[group.id] }))}>
                    <NozzleGlyph className="section-glyph" />
                    <span className="section-title">{group.title}</span>
                    {sectionErrors > 0 && <span className="badge badge-error">{sectionErrors} to fix</span>}
                    {sectionFlags > 0 && <span className="badge badge-warn">{sectionFlags} to check</span>}
                    {sectionChanges > 0 && <span className="badge">{sectionChanges} changed</span>}
                </button>
                <div className="section-body" hidden={!open}>
                    {group.note && <p className="section-note">{group.note}</p>}
                    <div className="form-grid">
                        {blocks.map((block) => {
                            if (block.kind === 'item') {
                                return renderItem(block.item);
                            }
                            const foldKey = `${group.id}:${block.name}`;
                            const foldOpen = filtering || Boolean(openFolds[foldKey]);
                            const foldHidden = !block.items.some(rowVisible);
                            return (
                                <div key={foldKey} className={`fold ${foldOpen ? 'is-open' : ''}`} hidden={foldHidden}>
                                    <button type="button" className="fold-header" aria-expanded={foldOpen}
                                            onClick={() => setOpenFolds((previous) => ({ ...previous, [foldKey]: !previous[foldKey] }))}>
                                        <NozzleGlyph className="section-glyph" />
                                        <span>{block.name}</span>
                                    </button>
                                    <div className="form-grid fold-body" hidden={!foldOpen}>
                                        {block.items.map(renderItem)}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </section>
        );
    };

    return (
        <div className="design-form">
            <div className="toolbar form-toolbar">
                <button type="button" className="button" onClick={onReset} title="Return every field to the shipped nozzle">
                    <ResetIcon /> Reset to example
                </button>
                <select className="input toolbar-select" value="" aria-label="Load example"
                        onChange={(event) => event.target.value && onLoadExample(event.target.value)}>
                    <option value="">Load example...</option>
                    {schema.examples.map((example) => <option key={example.name} value={example.name}>{example.title}</option>)}
                </select>
                <button type="button" className="button" onClick={onSave} title="Save the config as JSON  Ctrl+S">
                    Save config
                </button>
                <span className="toolbar-break" />
                <div className="search">
                    <SearchIcon />
                    <input className="input search-input" placeholder="Find a field" value={query} spellCheck={false}
                           onChange={(event) => setQuery(event.target.value)} aria-label="Find a field" />
                </div>
                <label className="check">
                    <input type="checkbox" checked={changedOnly} onChange={(event) => setChangedOnly(event.target.checked)} />
                    Changed only
                </label>
                <span className="muted changed-count">{changedCount} changed from the shipped nozzle</span>
            </div>
            {formState.problems.length > 0 && (
                <div className="form-warnings" role="status">
                    <span className="eyebrow eyebrow-inline">Check before running</span>
                    <ul>
                        {formState.problems.map((problem) => <li key={problem}>{problem}</li>)}
                    </ul>
                </div>
            )}
            <div className="design-body">
                <nav ref={outline} className="outline" aria-label="Form sections">
                    {schema.groups.filter((group) => !hidden.has(group.id)).map((group) => {
                        const { changes, errors: toFix, flags } = counts[group.id];
                        return (
                            <button key={group.id} type="button"
                                    className={`outline-item ${current === group.id ? 'is-current' : ''}`}
                                    aria-current={current === group.id ? 'location' : undefined}
                                    onClick={() => jumpTo(group.id)}
                                    title={[group.title, changes ? `${changes} changed` : '', flags ? `${flags} to check` : '',
                                            toFix ? `${toFix} to fix` : ''].filter(Boolean).join(', ')}>
                                <span className="outline-title">{group.title}</span>
                                {toFix > 0 && <span className="outline-count is-error">{toFix}</span>}
                                {flags > 0 && <span className="outline-count is-warn">{flags}</span>}
                                {changes > 0 && <span className="outline-count">{changes}</span>}
                            </button>
                        );
                    })}
                </nav>
                <div className="pane-scroll" ref={scroller}>
                    <div className="pane-column" key={formVersion}>
                        {schema.groups.map(renderSection)}
                        {filtering && !schema.groups.some((group) => blocksOf(group).some((block) =>
                            block.kind === 'item' ? rowVisible(block.item) : block.items.some(rowVisible))) && (
                            <p className="empty">No field matches.</p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
