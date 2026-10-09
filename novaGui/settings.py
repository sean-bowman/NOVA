# -- NOVA GUI Settings -- #

'''

The GUI's own preferences, kept between launches: at present only the theme mode.

They live in `%APPDATA%\\NOVA\\guiSettings.json` on Windows and `~/.config/NOVA/guiSettings.json`
elsewhere, apart from any nozzle configuration. A missing, unreadable or out-of-date file reads as
the defaults, and a file that cannot be written is left alone: a preference is never worth an
error.

Author: Sean Bowman

'''

import json
import os
import sys

defaults = {'themeMode': 'dark'}
themeModes = ('dark', 'light')

def settingsPath() -> str:

    '''Where the settings file lives on this machine.'''

    if sys.platform == 'win32' and os.environ.get('APPDATA'):
        folder = os.path.join(os.environ['APPDATA'], 'NOVA')
    else:
        folder = os.path.join(os.path.expanduser('~'), '.config', 'NOVA')

    return os.path.join(folder, 'guiSettings.json')

def load() -> dict:

    '''

    The saved settings over the defaults. Anything unreadable or unknown falls back to the default.

    '''

    settings = dict(defaults)
    try:
        with open(settingsPath(), encoding = 'utf-8') as handle:
            saved = json.load(handle)
    except (OSError, ValueError):
        return settings

    if isinstance(saved, dict) and saved.get('themeMode') in themeModes:
        settings['themeMode'] = saved['themeMode']

    return settings

def save(settings: dict) -> None:

    '''Write the settings, through a temporary file so a crash cannot leave half of one.'''

    path = settingsPath()
    try:
        os.makedirs(os.path.dirname(path), exist_ok = True)
        temporary = path + '.part'
        with open(temporary, 'w', encoding = 'utf-8') as handle:
            json.dump({**defaults, **settings}, handle, indent = 2)
        os.replace(temporary, path)
    except OSError:
        pass
