# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""Enable or disable the Mullion GNOME Shell extension.

The extension (extension/mullion@ivoks.github.io) provides what an
application can't do on Wayland: switching the keyboard and mouse at the
screen edge, GNOME's on-screen pop-up (see osd.py) and the Monitor tile in
Quick Settings.  It reads its settings from our config file and runs the
`mullion` command; this module only turns it on or off.
"""

from __future__ import annotations

from gi.repository import Gio, GLib

UUID = "mullion@ivoks.github.io"
_STATE_ACTIVE = 1


def _call(method: str, *args) -> GLib.Variant | None:
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        sig = "(" + "s" * len(args) + ")"
        return bus.call_sync("org.gnome.Shell.Extensions",
                             "/org/gnome/Shell/Extensions",
                             "org.gnome.Shell.Extensions", method,
                             GLib.Variant(sig, args) if args else None,
                             None, Gio.DBusCallFlags.NONE, 3000, None)
    except GLib.Error:
        return None


def info() -> dict | None:
    """Extension info from GNOME Shell, or None if the Shell doesn't know
    it (not installed, or installed after this login on Wayland)."""
    res = _call("GetExtensionInfo", UUID)
    if res is None:
        return None
    data = res.unpack()[0]
    return data or None


def active() -> bool:
    data = info()
    return bool(data) and int(data.get("state", 0)) == _STATE_ACTIVE


def set_enabled(on: bool) -> bool | None:
    """Enable or disable the extension.  Returns None when GNOME Shell
    doesn't know the extension yet (log out and back in once)."""
    if info() is None:
        return None
    res = _call("EnableExtension" if on else "DisableExtension", UUID)
    return bool(res.unpack()[0]) if res is not None else False
