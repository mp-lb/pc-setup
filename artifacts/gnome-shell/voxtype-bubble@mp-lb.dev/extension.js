// Recording bubble for Voxtype on GNOME, which lacks the Layer Shell protocol
// that Voxtype's own overlay needs. It reads the daemon's public interfaces:
// $XDG_RUNTIME_DIR/voxtype/state (idle, recording, transcribing, ...) and
// $XDG_RUNTIME_DIR/voxtype/audio.sock (16-byte level frames at 100 Hz).
import Cairo from 'cairo';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const FRAME_BYTES = 16;
const BARS = 32;
const FRAMES_PER_BAR = 4; // 40 ms of audio per bar.
const FLOOR_DB = -60;
const BOTTOM_GAP = 24;
const ACTIVE = new Set(['recording', 'streaming', 'transcribing']);

export default class VoxtypeBubble extends Extension {
    enable() {
        this._dir = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_runtime_dir(), 'voxtype']));
        this._levels = new Array(BARS).fill(0);
        this._pending = [];
        this._phase = 0;
        this._state = 'idle';
        this._buildUi();
        this._monitor = this._dir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
        this._monitor.connect('changed', (_m, file, other) => {
            if (file?.get_basename() === 'state' || other?.get_basename() === 'state')
                this._readState();
        });
        this._readState();
    }

    disable() {
        this._monitor?.cancel();
        this._monitor = null;
        this._stopAnimation();
        this._disconnect();
        this._bubble?.destroy();
        this._bubble = null;
    }

    _buildUi() {
        this._bubble = new St.BoxLayout({
            style_class: 'voxtype-bubble',
            reactive: true,
            opacity: 0,
            visible: false,
        });
        this._dot = new St.Widget({style_class: 'voxtype-bubble-dot', y_align: Clutter.ActorAlign.CENTER});
        this._meter = new St.DrawingArea({style_class: 'voxtype-bubble-meter', y_align: Clutter.ActorAlign.CENTER});
        this._meter.connect('repaint', area => this._paint(area));
        this._stop = new St.Button({
            style_class: 'voxtype-bubble-stop',
            can_focus: false,
            y_align: Clutter.ActorAlign.CENTER,
            child: new St.Widget({
                style_class: 'voxtype-bubble-stop-square',
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            }),
        });
        this._stop.connect('clicked', () => this._run('stop'));
        this._bubble.add_child(this._dot);
        this._bubble.add_child(this._meter);
        this._bubble.add_child(this._stop);
        // The shell can destroy chrome on shutdown without calling disable().
        this._bubble.connect('destroy', () => {
            this._stopAnimation();
            this._disconnect();
        });
        Main.layoutManager.addTopChrome(this._bubble);
    }

    _readState() {
        this._dir.get_child('state').load_contents_async(null, (file, res) => {
            let state = 'idle';
            try {
                state = new TextDecoder().decode(file.load_contents_finish(res)[1]).trim();
            } catch {
                // A missing state file means the daemon is not running.
            }
            if (this._bubble)
                this._setState(state);
        });
    }

    _setState(state) {
        if (state === this._state)
            return;
        const wasActive = ACTIVE.has(this._state);
        this._state = state;
        const recording = state === 'recording' || state === 'streaming';
        this._bubble.remove_style_pseudo_class('transcribing');
        if (state === 'transcribing')
            this._bubble.add_style_pseudo_class('transcribing');
        // Dim rather than hide, so the bubble keeps its size and position.
        this._stop.reactive = recording;
        this._stop.ease({opacity: recording ? 255 : 0, duration: 120});
        if (recording)
            this._connect();
        else
            this._disconnect();
        if (ACTIVE.has(state) && !wasActive)
            this._show();
        else if (!ACTIVE.has(state) && wasActive)
            this._hide();
    }

    _show() {
        this._levels.fill(0);
        this._bubble.remove_all_transitions();
        this._bubble.show();
        const monitor = Main.layoutManager.currentMonitor ?? Main.layoutManager.primaryMonitor;
        const area = Main.layoutManager.getWorkAreaForMonitor(monitor.index);
        const [, width] = this._bubble.get_preferred_width(-1);
        const [, height] = this._bubble.get_preferred_height(width);
        this._bubble.set_position(
            Math.round(area.x + (area.width - width) / 2),
            Math.round(area.y + area.height - height - BOTTOM_GAP));
        this._bubble.translation_y = 12;
        this._bubble.ease({opacity: 255, translation_y: 0, duration: 160, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
        this._startAnimation();
    }

    _hide() {
        this._bubble.ease({
            opacity: 0,
            translation_y: 12,
            duration: 200,
            mode: Clutter.AnimationMode.EASE_IN_QUAD,
            onComplete: () => {
                if (!ACTIVE.has(this._state)) {
                    this._bubble.hide();
                    this._stopAnimation();
                }
            },
        });
    }

    _startAnimation() {
        if (this._tick)
            return;
        this._tick = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 33, () => {
            this._phase += 0.12;
            this._meter.queue_repaint();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _stopAnimation() {
        if (this._tick)
            GLib.source_remove(this._tick);
        this._tick = 0;
    }

    _connect() {
        if (this._conn)
            return;
        const cancellable = new Gio.Cancellable();
        this._cancellable = cancellable;
        this._leftover = new Uint8Array(0);
        const path = this._dir.get_child('audio.sock').get_path();
        new Gio.SocketClient().connect_async(Gio.UnixSocketAddress.new(path), cancellable, (client, res) => {
            try {
                this._conn = client.connect_finish(res);
            } catch (e) {
                if (!cancellable.is_cancelled())
                    console.warn(`Voxtype bubble: level socket unavailable: ${e.message}`);
                return;
            }
            this._read(this._conn.get_input_stream(), cancellable);
        });
    }

    _read(stream, cancellable) {
        stream.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, cancellable, (s, res) => {
            let bytes;
            try {
                bytes = s.read_bytes_finish(res);
            } catch {
                return; // Cancelled or the daemon went away.
            }
            if (cancellable.is_cancelled())
                return;
            if (bytes.get_size() === 0) {
                this._conn = null; // The daemon dropped us; retry while recording.
                if (this._state === 'recording')
                    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
                        if (this._state === 'recording' && !cancellable.is_cancelled())
                            this._connect();
                        return GLib.SOURCE_REMOVE;
                    });
                return;
            }
            this._consume(bytes.toArray());
            this._read(s, cancellable);
        });
    }

    _consume(chunk) {
        const data = new Uint8Array(this._leftover.length + chunk.length);
        data.set(this._leftover);
        data.set(chunk, this._leftover.length);
        const whole = data.length - (data.length % FRAME_BYTES);
        const view = new DataView(data.buffer, data.byteOffset, whole);
        for (let offset = 0; offset < whole; offset += FRAME_BYTES) {
            const peakDb = view.getFloat32(offset + 12, true);
            const level = Number.isFinite(peakDb) ? (peakDb - FLOOR_DB) / -FLOOR_DB : 0;
            this._pending.push(Math.min(1, Math.max(0, level)));
            if (this._pending.length >= FRAMES_PER_BAR) {
                this._levels.shift();
                this._levels.push(Math.max(...this._pending));
                this._pending = [];
            }
        }
        this._leftover = data.slice(whole);
    }

    _disconnect() {
        this._cancellable?.cancel();
        this._cancellable = null;
        this._conn?.close(null);
        this._conn = null;
        this._pending = [];
    }

    _paint(area) {
        const cr = area.get_context();
        const [width, height] = area.get_surface_size();
        const step = width / BARS;
        const barWidth = Math.max(2, step * 0.55);
        const transcribing = this._state === 'transcribing';
        cr.setLineCap(Cairo.LineCap.ROUND);
        cr.setLineWidth(barWidth);
        for (let i = 0; i < BARS; i++) {
            let level = this._levels[i];
            if (transcribing)
                level = 0.18 + 0.14 * Math.sin(this._phase * 2 - i * 0.45);
            const extent = Math.max(barWidth, level * (height - barWidth)) / 2;
            const x = step * (i + 0.5);
            cr.setSourceRGBA(1, 1, 1, transcribing ? 0.55 : 0.35 + 0.65 * Math.min(1, level * 1.6));
            cr.moveTo(x, height / 2 - extent + barWidth / 2);
            cr.lineTo(x, height / 2 + extent - barWidth / 2);
            cr.stroke();
        }
        cr.$dispose();
    }

    _run(action) {
        try {
            Gio.Subprocess.new(['voxtype', 'record', action], Gio.SubprocessFlags.NONE);
        } catch (e) {
            console.warn(`Voxtype bubble: record ${action} failed: ${e.message}`);
        }
    }
}
