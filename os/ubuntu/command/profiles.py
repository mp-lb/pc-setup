"""Compile a few optional layers into ordinary upstream Xremap configuration."""
import copy
import json
from pathlib import Path
import re

LAYERS = {
    'command': ('Command key', 'Left Alt becomes Command on PC keyboards; left Super becomes Option.'),
    'control': ('Separate physical Control', 'Control becomes Super in apps. Standalone terminals keep Control.'),
    'terminal': ('Terminal shortcuts', 'Command-C/V copies and pastes; Command-T/W opens and closes tabs.'),
    'desktop': ('Desktop shortcuts', 'Command-Tab switches apps; Q quits; H minimizes; Control-Command-Q locks.'),
    'navigation': ('Text navigation', 'Command-arrows: line/document edges. Option-arrows: words. Shift selects.'),
}
DEFAULTS = {'keyboard': 'pc', 'layers': {key: True for key in LAYERS}, 'excluded_apps': [], 'wallpaper_folder': ''}


def validate(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise ValueError('Unrecognized dashboard preferences; preserved for review.')
    if value['keyboard'] not in ('pc', 'apple'):
        raise ValueError('Choose a PC or Apple keyboard.')
    if not isinstance(value['layers'], dict) or set(value['layers']) != set(LAYERS):
        raise ValueError('Unrecognized keyboard layers.')
    if any(type(v) is not bool for v in value['layers'].values()):
        raise ValueError('Layer selections must be on or off.')
    if not isinstance(value['excluded_apps'], list) or len(value['excluded_apps']) > 100:
        raise ValueError('Invalid application exclusions.')
    if any(not isinstance(v, str) or not re.fullmatch(r'[\w. -]{1,150}', v) for v in value['excluded_apps']):
        raise ValueError('Use application names, separated by commas; regular expressions are not accepted.')
    if not isinstance(value['wallpaper_folder'], str) or len(value['wallpaper_folder']) > 4096:
        raise ValueError('Invalid wallpaper folder.')
    return copy.deepcopy(value)


def compile_profile(source, preferences):
    prefs = validate(preferences)
    layers = prefs['layers']
    if not layers['command']:
        return {'keymap': [{'name': 'Emergency stop', 'remap': {'Ctrl-Alt-Esc': {'action': 'exit'}}}]}
    source = Path(source)
    config = json.loads((source / 'config.json').read_text())
    hardware = json.loads((source / (prefs['keyboard'] + '.json')).read_text())
    if not layers['control']:
        config['modmap'] = [config['modmap'][-1]]  # Both physical Controls stay Control.
    config['modmap'].extend(hardware['modmap'])
    keymaps = []
    for mapping in config['keymap']:
        name = mapping['name']
        emergency = name.startswith('Emergency')
        terminal = name.startswith('Terminal')
        if not emergency and not layers['terminal' if terminal else 'desktop']:
            continue
        if not emergency:
            mapping.setdefault('application', {'only': '/.+/'})
            if prefs['excluded_apps']:
                mapping['application']['not'] = prefs['excluded_apps']
        keymaps.append(mapping)
    if layers['navigation']:
        app_match = {'only': '/.+/'}
        if prefs['excluded_apps']:
            app_match['not'] = prefs['excluded_apps']
        # Command holds Ctrl_R outside Xremap's modifier tracker. Lift it for
        # line edges; keep it for document edges. Shift stays an ordinary key.
        command = {}
        for direction, target in [('Left', 'Home'), ('Right', 'End')]:
            for shift in ('', 'Shift-'):
                command[shift + direction] = [{'release': 'Ctrl_R'}, shift + target, {'press': 'Ctrl_R'}]
        for direction, target in [('Up', 'Home'), ('Down', 'End')]:
            for shift in ('', 'Shift-'):
                command[shift + direction] = shift + target
        keymaps.append({'name': 'Command text navigation', 'mode': 'command', 'exact_match': True,
                        'application': app_match, 'remap': command})
        option = {}
        for direction in ('Left', 'Right'):
            for shift in ('', 'Shift-'):
                option['Alt_L-' + shift + direction] = 'Ctrl_L-' + shift + direction
        # Only normal mode: Command+Option combinations belong to the app.
        keymaps.append({'name': 'Option word navigation', 'mode': 'default', 'exact_match': True,
                        'application': app_match, 'remap': option})
    config['keymap'] = keymaps
    return config
