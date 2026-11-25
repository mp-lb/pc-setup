#!/usr/bin/python3
"""Render the real GTK window and exercise UI dependencies without changing settings."""
import argparse
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui import Application, Adw, Gio, GLib, Gtk
from dashboard import Dashboard

class Preview(Application):
    def __init__(self, output):
        Adw.Application.__init__(self, application_id='dev.mplb.GnomeMacLike.Preview', flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.backend = Dashboard()
        self.smoke = output
        self.complete = False

    def do_activate(self):
        Gtk.Settings.get_default().set_property('gtk-enable-animations', False)
        super().do_activate()
        window = self.get_active_window()
        assert not window.loaded and not window.refreshing
        assert not window.apply_button.get_sensitive()
        window.check_button.emit('clicked')
        def ready():
            if window.refreshing or window.gallery_loading:
                return True
            self.capture(window, 0)
            return False
        GLib.timeout_add(100, ready)

    def capture(self, window, index):
        """Render actual GTK pages for local visual checks; no desktop screenshots."""
        import ctypes
        pages = ['keyboard', 'wallpapers', 'dock', 'restore']
        if index >= len(pages):
            # Exercise dependency controls without writing settings.
            window.switches['command'].set_active(False)
            assert not window.switches['navigation'].get_sensitive()
            window.switches['command'].set_active(True)
            window.chrome.set_active(True)
            assert 'chromium' in window.selected()['excluded_apps']
            self.complete = True
            print('GUI smoke check passed.', flush=True)
            self.quit()
            return False
        window.stack.set_visible_child_name(pages[index])
        window.present()
        window.queue_draw()
        def snapshot():
            snap = Gtk.Snapshot.new()
            content = window.get_content()
            content.queue_resize()
            content.allocate(window.get_width(), window.get_height(), -1, None)
            content.get_parent().snapshot_child(content, snap)
            # GI cannot marshal some GSK node subtypes; use the same public C API.
            gtk = ctypes.CDLL('libgtk-4.so.1')
            gtk.gtk_snapshot_to_node.argtypes = [ctypes.c_void_p]
            gtk.gtk_snapshot_to_node.restype = ctypes.c_void_p
            gtk.gsk_renderer_render_texture.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            gtk.gsk_renderer_render_texture.restype = ctypes.c_void_p
            gtk.gdk_texture_save_to_png.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            gtk.gsk_render_node_unref.argtypes = [ctypes.c_void_p]
            obj = ctypes.CDLL('libgobject-2.0.so.0')
            obj.g_object_unref.argtypes = [ctypes.c_void_p]
            node = gtk.gtk_snapshot_to_node(hash(snap))
            if not node:
                self.quit()
                raise RuntimeError('GTK page did not render.')
            texture = gtk.gsk_renderer_render_texture(hash(window.get_renderer()), node, None)
            path = Path(self.smoke) / (pages[index] + '.png')
            path.parent.mkdir(parents=True, exist_ok=True)
            if not gtk.gdk_texture_save_to_png(texture, str(path).encode()):
                raise RuntimeError('Could not capture GTK page.')
            obj.g_object_unref(texture)
            gtk.gsk_render_node_unref(node)
            GLib.timeout_add(200, self.capture, window, index + 1)
            return False
        GLib.timeout_add(700, snapshot)
        return False

if __name__ == '__main__':
    app = Preview(Path(sys.argv[1]))
    app.run([])
    raise SystemExit(0 if app.complete else 1)
