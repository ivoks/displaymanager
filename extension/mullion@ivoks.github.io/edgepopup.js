// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Ante Karamatic
//
// A small pop-up at the screen edge with one button that hands the keyboard
// and mouse to the other computer, shown when the pointer reaches the edge
// next to it (edge_mode "button").

import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

const MARGIN = 12;              // px between the popup and the edge
const HIDE_MS = 3000;           // shown this long unless hovered
const HIDE_AFTER_LEAVE_MS = 1200;

export class EdgePopup {
    // onActivate: called when the button is clicked.
    constructor(onActivate) {
        this._onActivate = onActivate;
        this._actor = null;
        this._timeoutId = 0;
    }

    get visible() {
        return this._actor !== null;
    }

    // monitor: {x, y, width, height}; y: pointer position.
    show(edge, name, monitor, y) {
        this.hide();
        const arrowLeft = edge === 'left';
        const text = _('Switch to {name}').replace('{name}', name);
        const button = new St.Button({
            style_class: 'button mullion-edge-button',
            label: arrowLeft ? `←  ${text}` : `${text}  →`,
            can_focus: true,
        });
        button.connect('clicked', () => {
            this.hide();
            this._onActivate(edge);
        });

        const actor = new St.BoxLayout({
            style_class: 'mullion-edge-popup',
            reactive: true,
            track_hover: true,
        });
        actor.add_child(button);
        actor.connect('notify::hover', () =>
            this._scheduleHide(actor.hover ? 0 : HIDE_AFTER_LEAVE_MS));
        Main.layoutManager.addTopChrome(actor);
        this._actor = actor;

        const [, width] = actor.get_preferred_width(-1);
        const [, height] = actor.get_preferred_height(width);
        const x = arrowLeft ? monitor.x + MARGIN
            : monitor.x + monitor.width - width - MARGIN;
        const top = Math.max(monitor.y + MARGIN,
            Math.min(y - height / 2, monitor.y + monitor.height - height - MARGIN));
        actor.set_position(Math.round(x), Math.round(top));
        this._scheduleHide(HIDE_MS);
    }

    hide() {
        this._scheduleHide(0);
        if (this._actor) {
            Main.layoutManager.removeChrome(this._actor);
            this._actor.destroy();
            this._actor = null;
        }
    }

    // ms > 0: hide after ms; 0: just cancel a pending hide.
    _scheduleHide(ms) {
        if (this._timeoutId) {
            GLib.source_remove(this._timeoutId);
            this._timeoutId = 0;
        }
        if (ms > 0) {
            this._timeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => {
                this._timeoutId = 0;
                this.hide();
                return GLib.SOURCE_REMOVE;
            });
        }
    }
}
