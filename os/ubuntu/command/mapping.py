"""Small, deterministic Command-key translation; no I/O or desktop settings."""
ESC, TAB, Q, W, ENTER, CTRL, A, SHIFT, Z = 1, 15, 16, 17, 28, 29, 30, 42, 44
C, V, RSHIFT, ALT, SPACE, F4 = 46, 47, 54, 56, 57, 62
RCTRL, RALT, INSERT, SUPER, RSUPER = 97, 100, 110, 125, 126
MODIFIERS = {CTRL, RCTRL, SHIFT, RSHIFT, ALT, RALT, SUPER, RSUPER}
TERMINALS = {'gnome-terminal-server', 'org.gnome.Terminal', 'org.gnome.Console',
             'kgx', 'org.gnome.Ptyxis', 'ptyxis', 'Alacritty', 'kitty',
             'org.wezfurlong.wezterm', 'konsole', 'xterm'}


class Mapper:
    def __init__(self, context, quit_app, apple=False):
        self.context, self.quit_app = context, quit_app
        self.command = SUPER if apple else ALT
        self.option = ALT if apple else SUPER
        self.held = set()  # (device, physical key), including both keyboards
        self.outputs = {}  # key-down mapping is retained until its matching key-up
        self.requirements = {}  # synthetic modifiers needed by each held Command chord
        self.output_mods = set()
        self.command_mods = set()
        self.last_context = {}

    def _physical(self):
        return {code for _, code in self.held}

    def _mods(self):
        physical = self._physical()
        desired = {ALT if code == self.option else code for code in physical
                   if code in MODIFIERS and code != self.command}
        if self.command in physical:
            desired |= self.command_mods
            for modifiers in self.requirements.values():
                desired |= modifiers
        releases = [(code, 0) for code in sorted(self.output_mods - desired)]
        presses = [(code, 1) for code in sorted(desired - self.output_mods)]
        self.output_mods = desired
        return releases + presses

    def event(self, device, code, value):
        token = (device, code)
        if value == 2:  # repeat the original output, not a newly focused app's mapping
            if token in self.requirements and self.command not in self._physical():
                return []
            output = self.outputs.get(token)
            return [(output, 2)] if output is not None else []
        if value == 0:
            if token not in self.held:
                return []
            self.held.remove(token)
            self.requirements.pop(token, None)
            output = self.outputs.pop(token, None)
            result = []
            if output is not None and output not in self.outputs.values():
                result.append((output, 0))
            if self.command not in self._physical():
                self.command_mods.clear()
            return result + self._mods()
        if token in self.held:
            return []
        self.held.add(token)
        if code in MODIFIERS:
            return self._mods()
        if self.command in self._physical():
            self.last_context = self.context()  # raises on unavailable/locked session: stop safely
            terminal = bool(TERMINALS & {self.last_context.get('wm_class'), self.last_context.get('app_id')})
            if code == Q:
                self.outputs[token] = None
                self.quit_app()  # normal GNOME quit request, never kill a process
                return []
            if code == TAB:
                self.command_mods = {SUPER}  # stay held until Command is released
            elif code in (C, V):
                if terminal:
                    self.command_mods = {CTRL, SHIFT}
                else:
                    # Also works in many embedded terminals without sending SIGINT.
                    self.command_mods = {CTRL} if code == C else {SHIFT}
                    code = INSERT
            elif code == W and terminal:
                self.command_mods = {CTRL, SHIFT}
                if self._physical() & {SHIFT, RSHIFT}:
                    code = Q  # GNOME Terminal: close window
            else:
                self.command_mods = {CTRL}
            self.requirements[token] = set(self.command_mods)
        already_down = code in self.outputs.values()
        self.outputs[token] = code
        return self._mods() + ([] if already_down else [(code, 1)])

    def release_all(self):
        result = [(code, 0) for code in sorted({x for x in self.outputs.values() if x is not None})]
        result += [(code, 0) for code in sorted(self.output_mods)]
        self.held.clear()
        self.outputs.clear()
        self.requirements.clear()
        self.output_mods.clear()
        self.command_mods.clear()
        return result
