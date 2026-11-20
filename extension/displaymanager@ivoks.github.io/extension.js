// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Ante Karamatic
//
// DisplayManager Edge Switch
//
// Wayland doesn't let ordinary applications see the pointer position, so
// this small extension puts pressure barriers (like GNOME's hot corner) on
// the outer left and right edges of the monitor DisplayManager controls.
// Pushing the pointer against one runs `displaymanager cross <edge>`, which
// decides from the monitor's current layout whether that edge borders the
// other computer and, if so, hands it the keyboard and mouse.
//
// Settings come from DisplayManager's config file:
//   ~/.config/displaymanager/config.json  {"edge_switch": true, "connector": "DP-1"}

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Layout from 'resource:///org/gnome/shell/ui/layout.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const PRESSURE_THRESHOLD = 100;     // px pushed into the edge…
const PRESSURE_TIMEOUT = 1000;      // …within this many ms
const COOLDOWN_MS = 2000;           // ignore further pushes while switching

export default class EdgeSwitchExtension extends Extension {
    enable() {
        this._barriers = [];
        this._pressure = [];
        this._lastSwitch = 0;
        this._configFile = Gio.File.new_for_path(GLib.build_filenamev([
            GLib.get_user_config_dir(), 'displaymanager', 'config.json']));

        // The app replaces config.json atomically, so watch the directory.
        const dir = this._configFile.get_parent();
        try {
            dir.make_directory_with_parents(null);
        } catch (e) {
            if (!e.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.EXISTS))
                logError(e, 'DisplayManager: cannot create config directory');
        }
        this._dirMonitor = dir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
        this._dirMonitorId = this._dirMonitor.connect('changed', (_m, file, other) => {
            const names = [file?.get_basename(), other?.get_basename()];
            if (names.includes('config.json'))
                this._rebuild();
        });
        this._monitorsChangedId = Main.layoutManager.connect(
            'monitors-changed', () => this._rebuild());

        this._rebuild();
    }

    disable() {
        this._clear();
        if (this._dirMonitor) {
            this._dirMonitor.disconnect(this._dirMonitorId);
            this._dirMonitor.cancel();
            this._dirMonitor = null;
        }
        if (this._monitorsChangedId) {
            Main.layoutManager.disconnect(this._monitorsChangedId);
            this._monitorsChangedId = 0;
        }
        this._configFile = null;
    }

    _readConfig() {
        try {
            const [, bytes] = this._configFile.load_contents(null);
            return JSON.parse(new TextDecoder().decode(bytes));
        } catch (e) {
            return {};
        }
    }

    _clear() {
        for (const p of this._pressure)
            p.destroy();
        for (const b of this._barriers)
            b.destroy();
        this._pressure = [];
        this._barriers = [];
    }

    _rebuild() {
        this._clear();
        const cfg = this._readConfig();
        if (!cfg.edge_switch || !cfg.connector)
            return;

        const index = global.backend.get_monitor_manager()
            .get_monitor_for_connector(cfg.connector);
        const mon = Main.layoutManager.monitors[index];
        if (index < 0 || !mon)
            return;

        // Only outer edges: a barrier between two of this computer's own
        // monitors would get in the way of moving the pointer across.
        const edges = [
            ['left', Meta.DisplayDirection.LEFT, mon.x, Meta.BarrierDirection.POSITIVE_X],
            ['right', Meta.DisplayDirection.RIGHT, mon.x + mon.width, Meta.BarrierDirection.NEGATIVE_X],
        ];
        for (const [edge, direction, x, allowed] of edges) {
            if (global.display.get_monitor_neighbor_index(index, direction) !== -1)
                continue;
            const barrier = new Meta.Barrier({
                backend: global.backend,
                x1: x, x2: x, y1: mon.y, y2: mon.y + mon.height,
                directions: allowed,
            });
            const pressure = new Layout.PressureBarrier(
                PRESSURE_THRESHOLD, PRESSURE_TIMEOUT, Shell.ActionMode.NORMAL);
            pressure.addBarrier(barrier);
            pressure.connect('trigger', () => this._cross(edge));
            this._barriers.push(barrier);
            this._pressure.push(pressure);
        }
    }

    _cross(edge) {
        const now = GLib.get_monotonic_time() / 1000;
        if (now - this._lastSwitch < COOLDOWN_MS)
            return;
        this._lastSwitch = now;

        const exe = GLib.find_program_in_path('displaymanager') ??
            GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'displaymanager']);
        try {
            const proc = Gio.Subprocess.new([exe, '-q', 'cross', edge],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
            proc.wait_async(null, null);
        } catch (e) {
            logError(e, 'DisplayManager: cannot run displaymanager');
        }
    }
}
