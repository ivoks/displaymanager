// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Ante Karamatic
//
// "Monitor" tile in GNOME's Quick Settings: the tile toggles side by side,
// its menu lists the layouts and offers moving the keyboard and mouse and
// swapping the inputs.  All monitor access goes through the `displaymanager`
// command; `displaymanager state --json` supplies the current state with
// layout names already translated.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';

import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as QuickSettings from 'resource:///org/gnome/shell/ui/quickSettings.js';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

const APP_ID = 'io.github.DisplayManager';

export function displaymanagerPath() {
    return GLib.find_program_in_path('displaymanager') ??
        GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'displaymanager']);
}

function monitorIcon() {
    return new Gio.ThemedIcon({names: [`${APP_ID}-symbolic`, 'video-display-symbolic']});
}

// GObject classes are registered on first use, so that loading this module
// needs nothing from GNOME Shell (and a re-enable doesn't register twice).
let MonitorToggle = null;
let MonitorIndicator = null;

function registerClasses() {
    if (MonitorIndicator)
        return;

    MonitorToggle = GObject.registerClass(
    class MonitorToggle extends QuickSettings.QuickMenuToggle {
        _init() {
            super._init({
                title: _('Monitor'),
                gicon: monitorIcon(),
                toggleMode: false,
            });
            this._busy = false;
            this._state = null;

            this.menu.setHeader(monitorIcon(), _('Monitor'), '');
            this._layoutSection = new PopupMenu.PopupMenuSection();
            this.menu.addMenuItem(this._layoutSection);
            this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

            this._usbItem = this.menu.addAction('', () => this._run(['usb', 'toggle']));
            this.menu.addAction(_('Swap Inputs'), () => this._run(['swap']));
            this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            this.menu.addAction(_('Open DisplayManager'), () => this._openApp());

            this.connect('clicked', () => this._run(['pbp', 'toggle']));
            this._sync();
        }

        refresh() {
            if (this._busy)
                return;
            this._busy = true;
            this._spawn(['state', '--json'], true, stdout => {
                this._busy = false;
                try {
                    this._state = JSON.parse(stdout);
                } catch (e) {
                    this._state = {error: String(e)};
                }
                this._sync();
            });
        }

        _sync() {
            const st = this._state;
            const ok = st && !st.error;
            this.checked = Boolean(ok && st.multi);
            this.subtitle = ok ? st.layout_title ?? '' : '';
            this.menu.setHeader(monitorIcon(), ok ? st.model : _('Monitor'),
                ok ? st.layout_title ?? '' : st?.error ?? '');

            this._layoutSection.removeAll();
            for (const lay of ok ? st.layouts : []) {
                const item = this._layoutSection.addAction(lay.title,
                    () => this._run(['layout', lay.key]));
                item.setOrnament(lay.key === st.layout
                    ? PopupMenu.Ornament.CHECK : PopupMenu.Ornament.NO_DOT);
            }

            this._usbItem.label.text = ok && st.usb_here === false
                ? _('Bring Keyboard & Mouse Here')
                : _('Move Keyboard & Mouse to Other Computer');
            this._usbItem.visible = Boolean(ok);
        }

        _run(args) {
            this._spawn(['-q', ...args], false, () => this.refresh());
        }

        _spawn(args, capture, done) {
            const flags = capture
                ? Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE
                : Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE;
            try {
                const proc = Gio.Subprocess.new([displaymanagerPath(), ...args], flags);
                proc.communicate_utf8_async(null, null, (p, res) => {
                    let stdout = '';
                    try {
                        [, stdout] = p.communicate_utf8_finish(res);
                    } catch (e) {
                        logError(e, 'DisplayManager');
                    }
                    done(stdout ?? '');
                });
            } catch (e) {
                logError(e, 'DisplayManager: cannot run displaymanager');
                done(JSON.stringify({error: e.message}));
            }
        }

        _openApp() {
            const app = Shell.AppSystem.get_default().lookup_app(`${APP_ID}.desktop`);
            if (app)
                app.activate();
            else
                this._spawn([], false, () => {});
        }
    });

    MonitorIndicator = GObject.registerClass(
    class MonitorIndicator extends QuickSettings.SystemIndicator {
        _init() {
            super._init();
            this.toggle = new MonitorToggle();
            this.quickSettingsItems.push(this.toggle);
        }

        destroy() {
            this.quickSettingsItems.forEach(item => item.destroy());
            super.destroy();
        }
    });
}

export function createIndicator() {
    registerClasses();
    return new MonitorIndicator();
}
