#!/usr/bin/python3
"""A native, optional dashboard. The window does not handle keyboard events."""
import argparse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path
import sys
import subprocess
import threading

sys.dont_write_bytecode = True
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk

from dashboard import Dashboard
from profiles import DEFAULTS, LAYERS

CHROME = ('google-chrome', 'Google-chrome', 'chromium', 'Chromium',
          'chromium-browser', 'chromium_chromium', 'org.chromium.Chromium')


def label(text, css=None):
    widget = Gtk.Label(label=text, xalign=0, wrap=True)
    if css:
        widget.add_css_class(css)
    return widget


def button(title, callback, style=None):
    widget = Gtk.Button(label=title)
    if style:
        widget.add_css_class(style)
    widget.connect('clicked', lambda *_: callback())
    return widget


class Window(Adw.ApplicationWindow):
    def __init__(self, application, backend):
        super().__init__(application=application, title='Gnome MacLike', default_width=980, default_height=800)
        self.backend = backend
        self.busy = False
        self.loaded = False
        self.state = {}
        self.switches = {}
        self.guarded = []
        self.preview_folder = None
        self.refreshing = False
        self.gallery_loading = False
        self.gallery_generation = 0
        self.gallery_job = None
        self.images = ThreadPoolExecutor(max_workers=1, thread_name_prefix='wallpapers')
        self.image_cache = OrderedDict()  # Worker-only, bounded, memory-only thumbnails.
        self.connect('close-request', self.close_requested)
        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class('background')
        self.toast.set_child(root)
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title='Gnome MacLike', subtitle='Your desktop, with a familiar feel'))
        self.check_button = button('Check setup', self.refresh)
        header.pack_end(self.check_button)
        root.append(header)
        self.banner = Adw.Banner(title='Check setup to load your saved choices and enable controls. No settings will change.')
        root.append(self.banner)
        self.banner.set_revealed(True)
        self.banner.connect('button-clicked', lambda *_: self.install_clicked())
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        switcher.set_halign(Gtk.Align.CENTER)
        switcher.set_margin_top(8)
        switcher.set_margin_bottom(8)
        root.append(switcher)
        root.append(self.stack)
        self.stack.set_vexpand(True)
        self.keyboard_page()
        self.wallpaper_page()
        self.dock_page()
        self.restore_page()
        self.status_row.set_title('Keyboard status not checked')
        self.status_row.set_subtitle('Click Check setup to read the current session and saved choices.')
        self.sensitivity()

    def close_requested(self, *_):
        if self.busy:
            self.toast.add_toast(Adw.Toast(title='Wait for the current operation to finish, or cancel its authentication prompt.'))
            return True
        self.gallery_generation += 1
        self.images.shutdown(wait=False, cancel_futures=True)
        return False

    def page(self, title, icon, subtitle):
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        content.set_margin_top(24)
        content.set_margin_bottom(28)
        content.set_margin_start(26)
        content.set_margin_end(26)
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        heading.append(label(title, 'title-1'))
        heading.append(label(subtitle, 'dim-label'))
        content.append(heading)
        clamp = Adw.Clamp(maximum_size=900, tightening_threshold=750)
        clamp.set_child(content)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=clamp)
        self.stack.add_titled_with_icon(scroll, title.lower(), title, icon)
        return content

    def group(self, page, title, description=None):
        group = Adw.PreferencesGroup(title=title)
        if description:
            group.set_description(description)
        page.append(group)
        return group

    def action_row(self, group, title, subtitle, action, callback, style=None, managed=True):
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        row.set_subtitle_lines(0)
        control = button(action, callback, style)
        control.set_valign(Gtk.Align.CENTER)
        row.add_suffix(control)
        group.add(row)
        if managed:
            self.guarded.append(control)
        return control

    def keyboard_page(self):
        page = self.page('Keyboard', 'input-keyboard-symbolic',
                         'A small set of layers. Apply when ready; Stop restores native key behavior.')
        group = self.group(page, 'Session')
        self.status_row = Adw.ActionRow(title='Keyboard stopped', subtitle='Nothing starts automatically at login.')
        self.apply_button = button('Apply and start', self.apply_keyboard, 'suggested-action')
        self.stop_button = button('Stop', lambda: self.work(self.backend.stop))
        for control in (self.stop_button, self.apply_button):
            control.set_valign(Gtk.Align.CENTER)
            self.status_row.add_suffix(control)
            self.guarded.append(control)
        group.add(self.status_row)
        self.hardware = Adw.ComboRow(title='Keyboard layout', model=Gtk.StringList.new(['PC keyboard', 'Apple keyboard']))
        self.hardware.set_subtitle('On PC keyboards, left Alt is Command and left Super is Option.')
        group.add(self.hardware)
        group = self.group(page, 'Mapping layers', 'Changes take effect only when you press Apply and start.')
        for key, (title, subtitle) in LAYERS.items():
            row = Adw.SwitchRow(title=title, subtitle=subtitle, active=True)
            row.set_subtitle_lines(0)
            self.switches[key] = row
            group.add(row)
        self.switches['command'].connect('notify::active', lambda *_: self.layer_sensitivity())
        group = self.group(page, 'Application exceptions',
                           'Keep the base modifier swap, but skip terminal, desktop and text-navigation shortcuts in these apps.')
        self.exclusions = Adw.EntryRow(title='Application names, separated by commas')
        group.add(self.exclusions)
        self.chrome = Adw.SwitchRow(title='Use only the base swap in Chrome / Chromium',
                                    subtitle='No browser-specific patches are installed.')
        group.add(self.chrome)
        page.append(label('Text navigation: Command-←/→ goes to line edges; Command-↑/↓ to document edges; '
                          'Option-←/→ moves by words. Add Shift to select. These mappings also apply outside '
                          'text fields and replace Option-arrow browser navigation. Embedded terminals follow '
                          'their host app, not the standalone-terminal rule.', 'dim-label'))

    def layer_sensitivity(self):
        active = self.switches['command'].get_active()
        for key, row in self.switches.items():
            if key != 'command':
                row.set_sensitive(active)

    def selected(self):
        prefs = copy.deepcopy(self.state.get('preferences', DEFAULTS))
        prefs['keyboard'] = 'apple' if self.hardware.get_selected() == 1 else 'pc'
        prefs['layers'] = {key: row.get_active() for key, row in self.switches.items()}
        names = [name.strip() for name in self.exclusions.get_text().split(',') if name.strip()]
        if self.chrome.get_active():
            names.extend(CHROME)
        prefs['excluded_apps'] = list(dict.fromkeys(names))
        if self.preview_folder:
            prefs['wallpaper_folder'] = str(self.preview_folder)
        return prefs

    def apply_keyboard(self):
        prefs = self.selected()
        self.work(lambda: self.backend.apply_keyboard(prefs))

    def wallpaper_page(self):
        page = self.page('Wallpapers', 'preferences-desktop-wallpaper-symbolic',
                         'Your own collection. Images stay in their original folder and are never bundled or uploaded.')
        toolbar = Gtk.Box(spacing=12)
        toolbar.append(button('Choose folder…', self.choose_folder))
        toolbar.append(button('Restore previous wallpaper', lambda: self.work(lambda: self.backend.appearance('restore-wallpaper'))))
        self.guarded.append(toolbar.get_last_child())
        self.fivek = Gtk.CheckButton(label='5K landscape only', active=True)
        self.fivek.connect('toggled', lambda *_: self.load_gallery())
        toolbar.append(self.fivek)
        page.append(toolbar)
        self.gallery_label = label('Choose a folder to browse wallpapers.', 'dim-label')
        page.append(self.gallery_label)
        self.gallery = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                   min_children_per_line=3, max_children_per_line=3, row_spacing=16, column_spacing=16)
        css = Gtk.CssProvider()
        css.load_from_string('.wallpaper-tile { padding: 0; border-radius: 12px; }')
        Gtk.StyleContext.add_provider_for_display(self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        page.append(self.gallery)

    def choose_folder(self):
        chooser = Gtk.FileChooserNative(title='Choose a wallpaper folder', transient_for=self,
                                         action=Gtk.FileChooserAction.SELECT_FOLDER, accept_label='Choose')
        def selected(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                self.preview_folder = Path(dialog.get_file().get_path())
                self.load_gallery()
                self.work(lambda: self.backend.save_folder(self.preview_folder), quiet=True)
            dialog.destroy()
        chooser.connect('response', selected)
        chooser.show()

    def load_gallery(self):
        # Snapshot GTK state here; directory reads and image decoding never run
        # on the GTK thread. One worker and a generation token bound rapid toggles.
        self.gallery_generation += 1
        generation = self.gallery_generation
        if self.gallery_job:
            self.gallery_job.cancel()
        child = self.gallery.get_first_child()
        while child:
            following = child.get_next_sibling()
            self.gallery.remove(child)
            child = following
        folder = self.preview_folder
        if not folder:
            self.gallery_loading = False
            self.gallery_label.set_text('Choose a folder to browse wallpapers. No image files are copied.')
            return
        fivek = self.fivek.get_active()
        self.gallery_loading = True
        self.gallery_label.set_text(f'{folder}\nLoading images…')

        def add_tile(path, width, height, pixbuf):
            if generation != self.gallery_generation:
                return False
            picture = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
            picture.set_content_fit(Gtk.ContentFit.COVER)
            picture.set_can_shrink(True)
            frame = Gtk.AspectFrame(ratio=1.6, obey_child=False, child=picture)
            frame.set_size_request(210, 135)
            tile = Gtk.Button(child=frame)
            tile.add_css_class('card')
            tile.add_css_class('wallpaper-tile')
            tile.set_overflow(Gtk.Overflow.HIDDEN)
            tile.set_tooltip_text(f'{path.name}\nClick to preview and see details')
            tile.update_property([Gtk.AccessibleProperty.LABEL], [f'Preview {path.name}'])
            tile.connect('clicked', lambda _: self.preview_wallpaper(path, width, height, pixbuf))
            self.gallery.append(tile)
            return False

        def done(count, below, skipped, error):
            if generation != self.gallery_generation:
                return False
            self.gallery_loading = False
            text = (f'{folder}\n{count} images shown' +
                    (f' · {below} below the 5K landscape filter' if below else '') +
                    (f' · {skipped} unreadable or oversized' if skipped else ''))
            self.gallery_label.set_text(f'Could not load folder: {error}' if error else text)
            return False

        def worker():
            count = below = skipped = 0
            error = None
            try:
                candidates = sorted(p for p in folder.iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'))[:200]
                for path in candidates:
                    if generation != self.gallery_generation:
                        return
                    try:
                        stat = path.stat()
                        key = (str(path), stat.st_mtime_ns, stat.st_size)
                        cached = self.image_cache.get(key)
                        if cached:
                            width, height, pixbuf = cached
                            self.image_cache.move_to_end(key)
                        else:
                            fmt, width, height = GdkPixbuf.Pixbuf.get_file_info(str(path))
                            if not fmt or width * height > 200_000_000:
                                skipped += 1
                                continue
                        if fivek and not (width >= 5120 and height >= 2880 and width >= height):
                            below += 1
                            continue
                        if not cached:
                            # Reuse this scaled image in the preview too: never
                            # decode a full-resolution original when opening it.
                            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 650, 400, True)
                            self.image_cache[key] = (width, height, pixbuf)
                            if len(self.image_cache) > 64:
                                self.image_cache.popitem(last=False)
                    except (GLib.Error, TypeError, OSError):
                        skipped += 1
                        continue
                    if generation != self.gallery_generation:
                        return
                    GLib.idle_add(add_tile, path, width, height, pixbuf)
                    count += 1
            except Exception as exc:
                error = str(exc)
            GLib.idle_add(done, count, below, skipped, error)
        self.gallery_job = self.images.submit(worker)

    def preview_wallpaper(self, path, width, height, pixbuf):
        dialog = Adw.AlertDialog(heading='Use this wallpaper?', body=f'{path.name}\n{width:,} × {height:,}')
        dialog.set_extra_child(Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pixbuf)))
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('apply', 'Set wallpaper')
        dialog.set_response_appearance('apply', Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_enabled('apply', bool(self.state.get('installed')) and not self.state.get('update') and not self.busy)
        dialog.connect('response', lambda _, response: self.work(lambda: self.backend.appearance('wallpaper', path)) if response == 'apply' else None)
        dialog.present(self)

    def dock_page(self):
        page = self.page('Dock', 'view-grid-symbolic', 'Familiar placement, with a distinctly Linux panel.')
        preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        preview.add_css_class('card')
        preview.set_margin_top(6)
        preview.append(Gtk.Label(label='Desktop', vexpand=True, height_request=130))
        bar = Gtk.Box(spacing=16, halign=Gtk.Align.CENTER, margin_top=16, margin_bottom=16)
        for icon in ('system-file-manager-symbolic', 'web-browser-symbolic', 'utilities-terminal-symbolic', 'view-app-grid-symbolic'):
            bar.append(Gtk.Image(icon_name=icon, pixel_size=28))
        preview.append(Gtk.Separator())
        preview.append(bar)
        page.append(preview)
        group = self.group(page, 'Bottom panel', 'Uses the existing Ubuntu Dock / Dash to Dock extension. No new extension is installed.')
        self.action_row(group, 'Bottom, full width, centered icons',
                        'Changes four settings. Icon size, pinned apps and other preferences stay as they are.',
                        'Apply panel', lambda: self.work(lambda: self.backend.appearance('dock')), 'suggested-action')
        self.action_row(group, 'Restore previous dock', 'Restores the values saved before this app first changed them.',
                        'Restore', lambda: self.work(lambda: self.backend.appearance('restore-dock')))
        self.dock_status = label('No dock changes recorded.', 'dim-label')
        page.append(self.dock_status)

    def restore_page(self):
        page = self.page('Restore', 'edit-undo-symbolic', 'See what the app owns, and undo it without guessing.')
        group = self.group(page, 'Your exit routes')
        self.action_row(group, 'Stop keyboard remapping', 'Immediately returns physical keys to their original behavior. No system keybindings were overwritten.',
                        'Stop', lambda: self.work(self.backend.stop))
        self.action_row(group, 'Restore desktop changes', 'Stops the keyboard session and restores the dock and wallpaper. Keeps the application installed.',
                        'Restore all', lambda: self.confirm('Restore your desktop?', 'Stop keyboard remapping and restore managed appearance settings?', self.backend.restore))
        self.action_row(group, 'Uninstall Gnome MacLike', 'Stops both services, restores managed settings and removes installed files and saved choices. Your wallpaper images stay untouched.',
                        'Uninstall', lambda: self.confirm('Uninstall Gnome MacLike?', 'Restore managed changes and remove the application? Your source checkout and original image files will remain.', self.backend.uninstall), 'destructive-action')
        page.append(label('Restoration means your values from before this app changed them—not factory defaults. '
                          'If you change a managed appearance setting elsewhere, its newer value is preserved. '
                          'Modified installation files and unknown files block removal instead of being deleted. '
                          'If authentication or cleanup fails, recovery records remain so you can retry.', 'dim-label'))
        group = self.group(page, 'Footprint and recovery record')
        self.action_row(group, 'Inspect the saved record', 'Exact installed paths, original settings and managed appearance values.',
                        'View details', self.show_details, managed=False)
        page.append(label('No packages, device-permission rules, startup services or boot settings are installed. '
                          'The remapper runs only after you start it and ends at logout. Closing this window '
                          'does not stop an active keyboard session. Physical Ctrl+Alt+Esc is the emergency stop.', 'dim-label'))

    def show_details(self):
        dialog = Adw.AlertDialog(heading='Installation and restoration record')
        view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text('Reading recovery record…')
        def worker():
            try:
                text = self.backend.details()
            except Exception as exc:
                text = str(exc)
            GLib.idle_add(view.get_buffer().set_text, text)
        threading.Thread(target=worker, daemon=True).start()
        scroll = Gtk.ScrolledWindow(child=view, min_content_height=320, min_content_width=560)
        dialog.set_extra_child(scroll)
        dialog.add_response('close', 'Close')
        dialog.present(self)

    def confirm(self, title, body, action):
        dialog = Adw.AlertDialog(heading=title, body=body)
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('confirm', 'Continue')
        dialog.set_response_appearance('confirm', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect('response', lambda _, response: self.work(action) if response == 'confirm' else None)
        dialog.present(self)

    def install_clicked(self):
        if self.state.get('installed'):
            self.confirm('Replace the installed version?',
                         'This stops the old session, restores its managed desktop settings, then installs this version. Saved layer choices reset. Nothing starts until you apply it.',
                         self.backend.install_current)
        else:
            self.work(self.backend.install_current)

    def work(self, action, quiet=False):
        if self.busy or self.refreshing:
            return
        self.busy = True
        self.sensitivity()
        self.banner.set_title('Working… Ubuntu may ask you to authenticate.')
        self.banner.set_button_label('')
        self.banner.set_revealed(True)
        def worker():
            try:
                result, error = action(), None
            except Exception as exc:
                result, error = None, str(exc)
                if isinstance(exc, subprocess.CalledProcessError) and exc.cmd and Path(exc.cmd[0]).name == 'pkexec':
                    error = ('Administrator authentication was cancelled or declined.' if exc.returncode == 126 else
                             'Desktop authentication could not start. Open Gnome MacLike from your applications menu or a normal terminal.')
            GLib.idle_add(done, result, error)
        def done(result, error):
            self.busy = False
            if error:
                dialog = Adw.AlertDialog(heading='The operation did not finish', body=error + '\n\nNo further steps were run. Any existing recovery record has been kept so you can retry.')
                dialog.add_response('close', 'Close')
                dialog.present(self)
            elif result and not quiet:
                self.toast.add_toast(Adw.Toast(title=result, timeout=8))
            if result and result.startswith('Uninstalled.') and self.backend.install.source == self.backend.install.app:
                self.close()
            else:
                self.refresh()
        threading.Thread(target=worker, daemon=True).start()

    def sensitivity(self):
        idle = not self.busy and not self.refreshing
        enabled = bool(self.state.get('installed')) and not self.state.get('update') and idle
        for control in self.guarded:
            control.set_sensitive(enabled)
        self.stop_button.set_sensitive(bool(self.state.get('running')) and idle)
        self.banner.set_sensitive(idle)
        self.check_button.set_sensitive(idle)

    def refresh(self):
        # systemctl and file reads run off the GTK event loop.
        if self.refreshing or self.busy:
            return
        self.refreshing = True
        self.check_button.set_label('Checking…')
        self.banner.set_title('Reading your setup… You can keep browsing.')
        self.banner.set_button_label('')
        self.sensitivity()
        def worker():
            try:
                state, error = self.backend.status(), None
            except Exception as exc:
                state, error = {}, str(exc)
            GLib.idle_add(done, state, error)
        def done(state, error):
            self.refreshing = False
            self.check_button.set_label('Check setup')
            if self.busy:
                return
            self.state = state
            if error:
                self.banner.set_title('Could not read the installation: ' + error)
                self.banner.set_button_label('')
            elif not state['installed'] or state['update']:
                self.banner.set_title('Install the dashboard to manage reversible changes.' if not state['installed'] else 'A previous version is installed. Replace it to use these controls.')
                self.banner.set_button_label('Install' if not state['installed'] else 'Update installation')
            else:
                self.banner.set_title('Installed · changes are tracked for restoration')
                self.banner.set_button_label('')
            running = state.get('running')
            self.status_row.set_title('Keyboard status unavailable' if error else 'Keyboard running' if running else 'Keyboard stopped')
            self.status_row.set_subtitle('Selected changes need Apply and start.' if running else 'Native key behavior. Nothing starts automatically at login.')
            if running and not state.get('bridge'):
                self.status_row.set_subtitle('Desktop adapter is unavailable. Stop and restart the keyboard session.')
            self.apply_button.set_label('Apply and restart' if running else 'Apply and start')
            if not self.loaded and not error:
                prefs = state.get('preferences', DEFAULTS)
                self.hardware.set_selected(1 if prefs['keyboard'] == 'apple' else 0)
                for key, row in self.switches.items():
                    row.set_active(prefs['layers'][key])
                self.exclusions.set_text(', '.join(name for name in prefs['excluded_apps'] if name not in CHROME))
                self.chrome.set_active(any(name in CHROME for name in prefs['excluded_apps']))
                self.layer_sensitivity()
                folder = prefs['wallpaper_folder']
                if not folder:
                    folder = next((str(p) for p in (Path.home()/'Pictures/Wallpapers', Path.home()/'Downloads/wallpapers', Path.home()/'Downloads/wp') if p.is_dir()), '')
                self.preview_folder = self.preview_folder or (Path(folder) if folder else None)
                self.load_gallery()
                self.loaded = True
            count = sum('dash-to-dock' in p for p in state.get('appearance', {}))
            self.dock_status.set_text(f'{count} dock settings saved for restoration.' if count else 'No dock changes recorded by this app.')
            self.sensitivity()
        threading.Thread(target=worker, daemon=True).start()


class Application(Adw.Application):
    def __init__(self, backend):
        super().__init__(application_id='dev.mplb.GnomeMacLike', flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.backend = backend

    def do_activate(self):
        window = self.get_active_window()
        if not window:
            window = Window(self, self.backend)
        window.present()



def main():
    parser = argparse.ArgumentParser(description='Gnome MacLike desktop dashboard')
    parser.add_argument('--archive', type=Path, help='Verified Xremap release archive for offline installation')
    args = parser.parse_args()
    return Application(Dashboard(archive=args.archive)).run([])


if __name__ == '__main__':
    raise SystemExit(main())
