/* ========================================
   TOOLTIP
   A hover or focus popover for help text, drawn in a portal on the page body so a card's
   overflow never clips it, and kept inside the viewport.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { InfoIcon } from './Icons';

interface TooltipProps {
    text: string;
    children: ReactNode;
    delayMs?: number;
}

export function Tooltip({ text, children, delayMs = 250 }: TooltipProps) {
    const anchor = useRef<HTMLSpanElement>(null);
    const popover = useRef<HTMLDivElement>(null);
    const timer = useRef<number | undefined>(undefined);
    const [open, setOpen] = useState(false);
    const [position, setPosition] = useState({ left: -9999, top: -9999 });

    const show = () => {
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setOpen(true), delayMs);
    };
    const hide = () => {
        window.clearTimeout(timer.current);
        setOpen(false);
    };

    useLayoutEffect(() => {
        if (!open || !anchor.current || !popover.current) {
            return;
        }
        const from = anchor.current.getBoundingClientRect();
        const box = popover.current.getBoundingClientRect();
        const margin = 8;
        let left = from.left;
        let top = from.bottom + 6;
        if (left + box.width > window.innerWidth - margin) {
            left = window.innerWidth - margin - box.width;
        }
        if (top + box.height > window.innerHeight - margin) {
            top = from.top - 6 - box.height;
        }
        setPosition({ left: Math.max(margin, left), top: Math.max(margin, top) });
    }, [open]);

    if (!text) {
        return <>{children}</>;
    }

    return (
        <span ref={anchor} className="tooltip-anchor" onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
            {children}
            {open && createPortal(
                <div ref={popover} className="tooltip" role="tooltip" style={position}>{text}</div>,
                document.body,
            )}
        </span>
    );
}

/** The (i) marker beside a label, carrying the field's help. */
export function HelpMarker({ text }: { text: string }) {
    if (!text) {
        return null;
    }
    return (
        <Tooltip text={text}>
            <span className="help-marker" tabIndex={0} aria-label="Help">
                <InfoIcon />
            </span>
        </Tooltip>
    );
}
