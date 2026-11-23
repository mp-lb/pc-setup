"""Small, removable Nautilus 50 sidebar customization.

Nautilus has no public sidebar customization API. Match its widget type and row
URI properties, leaving navigation and context menus to the original widgets.
"""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Nautilus", "4.1")
from gi.repository import GLib, GObject, Gtk, Nautilus


def children(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        child = child.get_next_sibling()


def sidebar_list(widget):
    if GObject.type_name(widget.__gtype__) == "NautilusSidebar":
        return next((w for w in descendants(widget) if isinstance(w, Gtk.ListBox)), None)
    for child in children(widget):
        result = sidebar_list(child)
        if result is not None:
            return result
    return None


def descendants(widget):
    for child in children(widget):
        yield child
        yield from descendants(child)


class PcSetupSidebar(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        super().__init__()
        home = Path.home()
        desktop = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP)
        downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        locations = [home.as_uri(), Path(desktop or home / "Desktop").as_uri(),
                     Path(downloads or home / "Downloads").as_uri(),
                     (home / "Work").as_uri(), "x-network-view:///", "trash:///"]
        self.order = {uri: i for i, uri in enumerate(locations)}
        GLib.idle_add(self.start)

    def start(self):
        app = Gtk.Application.get_default()
        if app is not None:
            app.connect("window-added", self.window_added)
            for window in app.get_windows():
                self.window_added(app, window)
        return GLib.SOURCE_REMOVE

    def rank(self, row):
        if row.find_property("uri") is None:
            return 99
        return self.order.get(row.get_property("uri"), 99)

    def window_added(self, app, window):
        attempts = 0

        def attach():
            nonlocal attempts
            attempts += 1
            box = sidebar_list(window)
            if box is None:
                return attempts < 30 and window.get_application() is not None
            # These callbacks also handle rows rebuilt after bookmark/mount changes.
            box.set_filter_func(lambda row: self.rank(row) < 99)
            box.set_sort_func(lambda first, second: self.rank(first) - self.rank(second))
            box.set_header_func(lambda row, before: row.set_header(None))
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(100, attach)
