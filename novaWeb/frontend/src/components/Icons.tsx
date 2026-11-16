/* ========================================
   ICONS
   Line and solid glyphs drawn in currentColor, sized by the caller's font size.
   Sean Bowman [11/16/2026]
   ======================================== */

interface IconProps {
    className?: string;
    title?: string;
}

function svgProps(className?: string) {
    return {
        className: `icon ${className ?? ''}`.trim(),
        viewBox: '0 0 24 24',
        width: '1em',
        height: '1em',
        'aria-hidden': true,
    } as const;
}

/**
 * A converging-diverging nozzle, flow to the right. Section headers turn it to point
 * downstream (down) when the section is open.
 */
export function NozzleGlyph({ className }: IconProps) {
    return (
        <svg {...svgProps(className)} fill="currentColor">
            <path d="M2 8.2h5.2l3.4 2.5c2.6.5 6.4-3.2 11.4-7.4v17.4c-5-4.2-8.8-7.9-11.4-7.4L7.2 15.8H2z" />
        </svg>
    );
}

export function SunIcon({ className }: IconProps) {
    return (
        <svg {...svgProps(className)} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <circle cx="12" cy="12" r="4.2" />
            <path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M5.3 5.3l1.7 1.7M17 17l1.7 1.7M5.3 18.7 7 17M17 7l1.7-1.7" />
        </svg>
    );
}

export function MoonIcon({ className }: IconProps) {
    return (
        <svg {...svgProps(className)} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
            <path d="M20 14.6A8.2 8.2 0 0 1 9.4 4a8.2 8.2 0 1 0 10.6 10.6z" />
        </svg>
    );
}

export function InfoIcon({ className }: IconProps) {
    return (
        <svg {...svgProps(className)} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 11v6" />
            <circle cx="12" cy="7.6" r="0.6" fill="currentColor" />
        </svg>
    );
}

export function ChevronIcon({ className }: IconProps) {
    return (
        <svg {...svgProps(className)} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m9 6 6 6-6 6" />
        </svg>
    );
}

export function SearchIcon({ className }: IconProps) {
    return (
        <svg {...svgProps(className)} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <circle cx="10.5" cy="10.5" r="6" />
            <path d="m15 15 5 5" />
        </svg>
    );
}

export function PlayIcon({ className }: IconProps) {
    return (
        <svg {...svgProps(className)} fill="currentColor">
            <path d="M7 4.5v15l12.5-7.5z" />
        </svg>
    );
}

export function StopIcon({ className }: IconProps) {
    return (
        <svg {...svgProps(className)} fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="1.5" />
        </svg>
    );
}

export function ResetIcon({ className }: IconProps) {
    return (
        <svg {...svgProps(className)} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 12a8 8 0 1 0 2.4-5.7" />
            <path d="M4 4v4.5h4.5" />
        </svg>
    );
}
