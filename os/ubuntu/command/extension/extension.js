import Gio from 'gi://Gio';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const XML = `<node><interface name="dev.mplb.UbuntuCommand">
<method name="Context"><arg type="s" direction="out"/></method>
<method name="Quit"><arg type="b" direction="out"/></method>
</interface></node>`;

export default class UbuntuCommand extends Extension {
    enable() {
        this._object = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._object.export(Gio.DBus.session, '/dev/mplb/UbuntuCommand');
    }

    disable() {
        this._object?.unexport();
        this._object = null;
    }

    Context() {
        const window = global.display.focus_window;
        const locked = Main.sessionMode.isLocked || Main.sessionMode.isGreeter;
        const app = window ? Shell.WindowTracker.get_default().get_window_app(window) : null;
        return JSON.stringify({
            locked,
            wm_class: locked ? '' : (window?.get_wm_class() ?? ''),
            app_id: locked ? '' : (app?.get_id()?.replace(/\.desktop$/, '') ?? ''),
        });
    }

    Quit() {
        if (Main.sessionMode.isLocked || Main.sessionMode.isGreeter)
            return false;
        const window = global.display.focus_window;
        const app = window ? Shell.WindowTracker.get_default().get_window_app(window) : null;
        if (!app)
            return false;
        return app.request_quit();
    }
}
