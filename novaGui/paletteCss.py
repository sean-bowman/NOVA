
# -- Palette CSS Writer -- #

'''

Write the front end's palette stylesheet from novaGui.themeColors.palettes.

The Engineering Flat Metal palette is held in Python, where the Matplotlib drawers, the legacy
Tkinter front end and NOVA's figures read it. The React app reads it as CSS custom properties, one block per mode, keyed
on the root element's data-theme attribute. This module renders that stylesheet, and
tests/testWebServer.py checks the committed file against it, so the three copies cannot drift.

    python -m novaGui.paletteCss        rewrite novaGui/frontend/src/styles/palette.css

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import os
import re
import sys

cssPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'src', 'styles', 'palette.css')

def _cssName(name: str) -> str:

    '''A palette key as a CSS custom property: textMuted becomes --text-muted, surface2 --surface-2.'''

    spaced = re.sub(r'(?<=[a-z])([A-Z0-9])', r'-\1', name)
    return '--' + spaced.lower()

def cssText() -> str:

    '''

    The stylesheet: dark on the root by default and under [data-theme='dark'], light under
    [data-theme='light'].

    '''

    from .themeColors import palettes

    lines = [
        '/* ========================================',
        '   NOVA PALETTE',
        '   Engineering Flat Metal, dark and light, from novaGui.themeColors.palettes.',
        '   Written by `python -m novaGui.paletteCss`; edit the Python palette, not this file.',
        '   ======================================== */',
        '',
    ]
    for mode, selector in (('dark', ":root,\n:root[data-theme='dark']"), ('light', ":root[data-theme='light']")):
        lines.append(selector + ' {')
        lines.append(f'    color-scheme: {mode};')
        for name, value in palettes[mode].items():
            lines.append(f'    {_cssName(name)}: {value};')
        lines.append('}')
        lines.append('')

    return '\n'.join(lines)

def main() -> int:

    os.makedirs(os.path.dirname(cssPath), exist_ok = True)
    with open(cssPath, 'w', encoding = 'utf-8', newline = '\n') as handle:
        handle.write(cssText())
    print(f'wrote {cssPath}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
