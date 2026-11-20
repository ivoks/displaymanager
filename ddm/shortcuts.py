# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""Manage GNOME custom keyboard shortcuts (Settings → Keyboard → Custom)."""

from __future__ import annotations

import os
import re
import shutil
import sys

from gi.repository import Gio

from .controller import LAYOUTS
from .i18n import N_, _

SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CHILD = SCHEMA + ".custom-keybinding"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
PREFIX = "displaymanager-"

# id -> (title msgid, CLI sub-command, default accelerator)
ACTIONS = {
    "switch": (N_("Switch computer"), "switch", "<Super><Control>k"),
    "usb": (N_("Move keyboard & mouse"), "usb toggle", "<Super><Control>u"),
    "pbp": (N_("Toggle side-by-side"), "pbp toggle", "<Super><Control>p"),
    "swap": (N_("Swap left/right"), "swap", "<Super><Control>s"),
    "layout": (N_("Next layout"), "layout next", "<Super><Control>l"),
}

# One shortcut per layout, in the order shown in the app.  Super+Ctrl+digit
# is taken by GNOME Shell ("open new window of dock app N") and
# Super+Alt+8 by the magnifier, so the last layout uses Super+Alt+9.
_LAYOUT_KEYS = ["1", "2", "3", "4", "5", "6", "7", "9"]
LAYOUT_ACTIONS = {
    f"layout-{lay.key}": (lay.name, f"layout {lay.key}", f"<Super><Alt>{key}")
    for lay, key in zip(LAYOUTS, _LAYOUT_KEYS)
}
ACTIONS.update(LAYOUT_ACTIONS)


def title(action: str) -> str:
    """Translated short title, e.g. for a row in the app."""
    return _(ACTIONS[action][0])


def gnome_name(action: str) -> str:
    """Name shown in GNOME Settings → Keyboard → Custom Shortcuts."""
    if action in LAYOUT_ACTIONS:
        return _("Monitor: {layout} layout").format(layout=title(action))
    return _("Monitor: {action}").format(action=title(action))


def _available() -> bool:
    src = Gio.SettingsSchemaSource.get_default()
    return bool(src and src.lookup(SCHEMA, True) and src.lookup(CHILD, True))


def launcher() -> str:
    exe = shutil.which("displaymanager")
    if exe:
        return exe
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return f"{sys.executable} {os.path.join(here, 'displaymanager')}"


_MOD_ALIASES = {"control": "ctrl", "ctl": "ctrl", "ctrl": "ctrl",
                "primary": "ctrl", "alt": "alt", "mod1": "alt",
                "super": "super", "mod4": "super", "shift": "shift",
                "meta": "meta", "hyper": "hyper"}


def normalize(accel: str) -> tuple[frozenset, str] | None:
    """'<Alt><Super>8' and '<Super><Alt>8' -> same key, no GTK needed."""
    mods = re.findall(r"<([^>]+)>", accel or "")
    key = re.sub(r"<[^>]+>", "", accel or "").strip().lower()
    if not key:
        return None
    return frozenset(_MOD_ALIASES.get(m.lower(), m.lower()) for m in mods), key


def label(accel: str) -> str:
    """Human-readable 'Super+Alt+9' without needing GTK."""
    n = normalize(accel)
    if not n:
        return accel
    order = ["super", "ctrl", "alt", "shift", "meta", "hyper"]
    mods = [m.capitalize() for m in order if m in n[0]]
    key = n[1].upper() if len(n[1]) == 1 else n[1].capitalize()
    return "+".join(mods + [key])


def conflicts(accel: str, action: str | None = None) -> list[str]:
    """What else in GNOME already uses this key combination."""
    want = normalize(accel)
    if want is None:
        return []
    src = Gio.SettingsSchemaSource.get_default()
    found = []
    if src:
        for sid in src.list_schemas(True)[0]:
            if not re.search(r"keybinding|media-keys|dash-to-dock|\.wm\.", sid):
                continue
            schema = src.lookup(sid, True)
            if schema is None or schema.get_path() is None:
                continue
            settings = Gio.Settings.new(sid)
            for k in schema.list_keys():
                value = settings.get_value(k)
                t = value.get_type_string()
                vals = [value.unpack()] if t == "s" else \
                    value.unpack() if t == "as" else []
                if any(normalize(v) == want for v in vals if "<" in v):
                    found.append(schema.get_key(k).get_summary() or k)
    if _available():
        own = {BASE + PREFIX + action + sfx + "/" for sfx in ("", KEYPAD_SUFFIX)} \
            if action else set()
        for path in Gio.Settings.new(SCHEMA).get_strv("custom-keybindings"):
            if path in own:
                continue
            c = _child(path)
            if normalize(c.get_string("binding")) == want:
                found.append(c.get_string("name") or path)
    return found


KEYPAD_SUFFIX = "-keypad"


def keypad_twin(accel: str | None) -> str | None:
    """'<Super><Alt>2' -> '<Super><Alt>KP_2'.  Number-pad keys send their
    own keysyms, and a GNOME custom shortcut holds only one binding, so
    digit shortcuts get a companion entry for the number pad."""
    if not accel:
        return None
    m = re.fullmatch(r"((?:<[^>]+>)*)([0-9])", accel)
    return f"{m.group(1)}KP_{m.group(2)}" if m else None


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
        raise RuntimeError(_("GNOME keyboard shortcut settings are not available"))
    if accel:
        for a in filter(None, (accel, keypad_twin(accel))):
            taken = conflicts(a, action)
            if taken:
                raise ValueError(_("{keys} is already used by: {users}").format(
                    keys=label(a), users=", ".join(taken)))
    root = Gio.Settings.new(SCHEMA)
    paths = list(root.get_strv("custom-keybindings"))
    name, cmd = gnome_name(action), ACTIONS[action][1]
    entries = [(BASE + PREFIX + action + "/", accel, name),
               (BASE + PREFIX + action + KEYPAD_SUFFIX + "/",
                keypad_twin(accel),
                _("{name} (number pad)").format(name=name))]
    for path, binding, title in entries:
        if binding:
            c = _child(path)
            c.set_string("name", title)
            c.set_string("command", f"{launcher()} {cmd}")
            c.set_string("binding", binding)
            if path not in paths:
                paths.append(path)
        elif path in paths:
            paths.remove(path)
            c = _child(path)
            for k in ("name", "command", "binding"):
                c.reset(k)
    root.set_strv("custom-keybindings", paths)
    Gio.Settings.sync()
