# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""On-screen feedback: GNOME's pop-up (as for volume keys) via our extension.

GNOME Shell's own ShowOSD D-Bus method only accepts calls from GNOME
components, so the Mullion extension exports an equivalent method on
the Shell's bus connection.  If the extension isn't running, callers fall
back to a desktop notification.
"""

from __future__ import annotations

from gi.repository import Gio, GLib

ICON_KEYBOARD = "input-keyboard-symbolic"
ICON_DISPLAY = "video-display-symbolic"
ICON_LEVELS = {
    "brightness": "display-brightness-symbolic",
    "contrast": "color-select-symbolic",
    "volume": "audio-volume-high-symbolic",
}


def show(icon: str, label: str, level: float | None = None) -> bool:
    """Show the pop-up on the monitor's screen; level 0…1 adds a level bar.
    Returns False if the extension isn't available."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        bus.call_sync("org.gnome.Shell", "/io/github/ivoks/Mullion",
                      "io.github.ivoks.Mullion", "ShowOSD",
                      GLib.Variant("(ssd)", (icon, label,
                                             -1.0 if level is None
                                             else float(level))),
                      None, Gio.DBusCallFlags.NONE, 1000, None)
        return True
    except GLib.Error:
        return False


def notify(label: str) -> None:
    """Desktop notification, for when the pop-up isn't available."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        bus.call_sync("org.freedesktop.Notifications",
                      "/org/freedesktop/Notifications",
                      "org.freedesktop.Notifications", "Notify",
                      GLib.Variant("(susssasa{sv}i)",
                                   ("Mullion", 0, ICON_DISPLAY, label,
                                    "", [],
                                    {"transient": GLib.Variant("b", True)},
                                    2000)),
                      None, Gio.DBusCallFlags.NONE, 2000, None)
    except GLib.Error:
        pass


def feedback(label: str, icon: str = ICON_DISPLAY,
             level: float | None = None, use_osd: bool = True) -> None:
    if not (use_osd and show(icon, label, level)):
        notify(label)
