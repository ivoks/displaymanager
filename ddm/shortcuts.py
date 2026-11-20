# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""Manage GNOME custom keyboard shortcuts (Settings → Keyboard → Custom)."""

from __future__ import annotations

import shutil
import sys
import os

from gi.repository import Gio

from .controller import LAYOUTS

SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CHILD = SCHEMA + ".custom-keybinding"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
PREFIX = "displaymanager-"

# id -> (human name, CLI sub-command, default accelerator)
ACTIONS = {
    "switch": ("Monitor: switch computer", "switch", "<Super><Control>k"),
    "usb": ("Monitor: move keyboard & mouse", "usb toggle", "<Super><Control>u"),
    "pbp": ("Monitor: toggle side-by-side", "pbp toggle", "<Super><Control>p"),
    "swap": ("Monitor: swap left/right", "swap", "<Super><Control>s"),
    "layout": ("Monitor: next layout", "layout next", "<Super><Control>l"),
}

# One shortcut per layout: Super+Alt+1 … 8, in the order shown in the app.
# (Super+Ctrl+digit is taken by GNOME Shell's "open new window of dock app".)
LAYOUT_ACTIONS = {
    f"layout-{lay.key}": (f"Monitor: {lay.title} layout", f"layout {lay.key}",
                          f"<Super><Alt>{i}")
    for i, lay in enumerate(LAYOUTS, start=1)
}
ACTIONS.update(LAYOUT_ACTIONS)


def _available() -> bool:
    src = Gio.SettingsSchemaSource.get_default()
    return bool(src and src.lookup(SCHEMA, True) and src.lookup(CHILD, True))


def launcher() -> str:
    exe = shutil.which("displaymanager")
    if exe:
        return exe
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return f"{sys.executable} {os.path.join(here, 'displaymanager')}"


def _child(path: str) -> Gio.Settings:
    return Gio.Settings.new_with_path(CHILD, path)


def get(action: str) -> str | None:
    """Return the accelerator if the shortcut is installed, else None."""
    if not _available():
        return None
    path = BASE + PREFIX + action + "/"
    if path not in Gio.Settings.new(SCHEMA).get_strv("custom-keybindings"):
        return None
    return _child(path).get_string("binding") or None


def set(action: str, accel: str | None) -> None:
    if not _available():
        raise RuntimeError("GNOME media-keys schema not available")
    root = Gio.Settings.new(SCHEMA)
    paths = list(root.get_strv("custom-keybindings"))
    path = BASE + PREFIX + action + "/"
    if accel:
        name, cmd, _ = ACTIONS[action]
        c = _child(path)
        c.set_string("name", name)
        c.set_string("command", f"{launcher()} {cmd}")
        c.set_string("binding", accel)
        if path not in paths:
            paths.append(path)
    else:
        if path in paths:
            paths.remove(path)
            c = _child(path)
            for k in ("name", "command", "binding"):
                c.reset(k)
    root.set_strv("custom-keybindings", paths)
    Gio.Settings.sync()
