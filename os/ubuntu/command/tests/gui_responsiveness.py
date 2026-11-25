#!/usr/bin/python3
"""Real GTK event-loop regression check with deliberately slow reads/decodes."""
from pathlib import Path
import copy
import sys
import tempfile
import time
from unittest.mock import patch
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui import Application, Adw, Gio, GLib, Gtk, GdkPixbuf
from profiles import DEFAULTS


class Backend:
    calls = 0
    def status(self):
        self.calls += 1
        time.sleep(.4)
        prefs = copy.deepcopy(DEFAULTS)
        prefs['wallpaper_folder'] = str(folder)
        return dict(installed=True, update=False, running=False, bridge=False,
                    preferences=prefs, appearance={})


class Check(Application):
    def __init__(self):
        Adw.Application.__init__(self, application_id='dev.mplb.GnomeMacLike.Responsiveness',
                                 flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.backend = Backend()
        self.phase = 0
        self.complete = False
        self.started = self.last = time.monotonic()
        self.gaps = []

    def do_activate(self):
        super().do_activate()
        GLib.timeout_add(20, self.tick)

    def tick(self):
        now = time.monotonic()
        self.gaps.append(now - self.last)
        self.last = now
        window = self.get_active_window()
        try:
            assert now - self.started < 15, 'GUI test timed out'
            if self.phase == 0 and now - self.started > .3:
                assert self.backend.calls == 0, 'Startup triggered a check'
                assert not window.apply_button.get_sensitive()
                window.check_button.emit('clicked')
                assert window.refreshing
                self.phase = 1
            elif self.phase == 1 and window.loaded and not window.gallery_loading:
                assert '1 images shown' in window.gallery_label.get_text()
                window.fivek.set_active(False)
                self.phase = 2
            elif self.phase == 2:
                # Cancel an in-flight load, then request the final filter state.
                window.fivek.set_active(True)
                window.fivek.set_active(False)
                self.phase = 3
            elif self.phase == 3 and not window.gallery_loading:
                assert '2 images shown' in window.gallery_label.get_text()
                child, count = window.gallery.get_first_child(), 0
                while child:
                    count += 1
                    child = child.get_next_sibling()
                assert count == 2, f'Stale tiles leaked: {count}'
                before = len(decodes)
                window.gallery.get_first_child().get_child().emit('clicked')
                assert len(decodes) == before, 'Preview decoded the original again'
                assert self.backend.calls == 1, 'Unexpected automatic status check'
                assert max(self.gaps[1:]) < .25, f'Blocked GTK loop: {max(self.gaps):.3f}s'
                self.complete = True
                print(f'GUI responsiveness passed; largest event-loop gap {max(self.gaps[1:]):.3f}s.')
                window.images.shutdown(wait=False, cancel_futures=True)
                self.quit()
                return False
        except Exception:
            window.images.shutdown(wait=False, cancel_futures=True)
            self.quit()
            raise
        return True


with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 100, 80)
    pixbuf.fill(0x4488AAFF)
    for name in ('high.png', 'low.png'):
        pixbuf.savev(str(folder / name), 'png', [], [])
    decoder = GdkPixbuf.Pixbuf.new_from_file_at_scale
    decodes = []
    def slow_decode(path, *args):
        decodes.append(path)
        time.sleep(.4)
        return decoder(path, *args)
    def metadata(path):
        return (True, 6000, 4000) if Path(path).name == 'high.png' else (True, 2000, 1500)
    with patch.object(GdkPixbuf.Pixbuf, 'new_from_file_at_scale', side_effect=slow_decode), \
         patch.object(GdkPixbuf.Pixbuf, 'get_file_info', side_effect=metadata):
        app = Check()
        app.run([])
        raise SystemExit(0 if app.complete else 1)
