# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""Command line interface (used by the GNOME keyboard shortcuts)."""

from __future__ import annotations

import argparse
import sys

from . import ddc, osd
from .controller import LAYOUT_BY_CODE, LEVELS, Controller, find_layout
from .i18n import _


def _table(rows: list[tuple[str, str]]) -> None:
    """Print 'Label:  value' rows aligned to the longest (translated) label."""
    width = max(len(label) for label, _value in rows) + 2
    for label, value in rows:
        print(f"{label:{width}}{value}")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="displaymanager",
        description=_("Control a monitor's inputs, screen layout and KVM over "
                      "DDC/CI. Run without arguments for the graphical "
                      "application."))
    p.add_argument("-q", "--quiet", action="store_true",
                   help=_("don't show a desktop notification"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help=_("show the monitor's state"))
    sub.add_parser("switch", help=_("with two inputs on screen move the "
                                    "keyboard and mouse, otherwise switch "
                                    "the full-screen input"))
    s = sub.add_parser("usb", help=_("keyboard and mouse: here, away or "
                                     "toggle"))
    s.add_argument("where", nargs="?", default="toggle",
                   choices=["here", "away", "toggle"])
    sub.add_parser("swap", help=_("swap the two inputs"))
    s = sub.add_parser("pbp", help=_("side by side: on (last used layout), "
                                     "off or toggle"))
    s.add_argument("state", choices=["on", "off", "toggle"])
    s = sub.add_parser("layout", help=_(
        "screen layout: list, next, or a name (single, 50-50, 75-25, 80-20, "
        "25-75, 20-80, pip-small, pip-large)"))
    s.add_argument("name", nargs="?", default="list")
    s = sub.add_parser("input", help=_("select the main input by hex code, "
                                       "e.g. 0x0f"))
    s.add_argument("code")
    s = sub.add_parser("right", help=_("select the second input (right side "
                                       "or inset) by hex code, e.g. 0x19"))
    s.add_argument("code")
    for name, help_text in (
            ("brightness", _("show or set brightness: 0–100, +N or -N")),
            ("contrast", _("show or set contrast: 0–100, +N or -N")),
            ("volume", _("show or set the speaker volume: 0–100, +N or "
                         "-N"))):
        s = sub.add_parser(name, help=help_text)
        s.add_argument("value", nargs="?")
    sub.add_parser("inputs", help=_("list the inputs the monitor reports"))
    s = sub.add_parser("cross", help=_("the pointer reached this screen "
                                       "edge: move the keyboard and mouse "
                                       "if the other computer is on that "
                                       "side (used by the GNOME extension)"))
    s.add_argument("edge", choices=["left", "right"])
    sub.add_parser("detect", help=_("work out which input this computer "
                                    "is plugged into"))
    a = p.parse_args(argv)

    ctl = Controller()
    try:
        mon = ctl.connect()
        msg = None
        icon, level = osd.ICON_DISPLAY, None
        if a.cmd == "status":
            st = ctl.status()
            rows = [(_("Monitor:"), f"{mon.model}  {mon.serial}  "
                                    f"{mon.connector}  /dev/i2c-{mon.bus}")]
            rows.append((_("Input:"),
                         f"{ctl.input_label(st.input)} (0x{st.input:02X})"
                         if st.input is not None else f"? {st.error}"))
            lay = LAYOUT_BY_CODE.get(st.pxp_raw)
            rows.append((_("Layout:"),
                         f"{lay.title if lay else _('unknown')} "
                         f"(E9=0x{st.pxp_raw:02X})"
                         if st.pxp_raw is not None else _("unknown")))
            if st.right_input is not None:
                rows.append((_("Second input:"),
                             f"{ctl.input_label(st.right_input)} "
                             f"(0x{st.right_input:02X})"))
            for name, title in LEVELS.items():
                if name in st.levels:
                    cur, top = st.levels[name]
                    rows.append((_(title) + ":", f"{cur} / {top}"))
            rows.append((_("Keyboard & mouse:"), {
                True: _("this computer"), False: _("other computer"),
                None: _("unknown")}[st.usb_here]))
            for key, label in (("this_input", _("This computer:")),
                               ("other_input", _("Other computer:"))):
                v = ctl.cfg.get(key)
                rows.append((label, ctl.input_label(v) if v is not None
                             else _("not set")))
            _table(rows)
            return 0
        if a.cmd == "detect":
            code, why = ctl.detect_this_input()
            if code is None:
                print(_("Could not tell: {reason}").format(reason=why))
                return 1
            print(_("This computer: {input} ({code}) [{reason}]").format(
                input=ctl.input_label(code), code=f"0x{code:02X}", reason=why))
            return 0
        if a.cmd == "inputs":
            for c in ctl.supported_inputs(refresh=True):
                print(f"0x{c:02X}  {ctl.input_label(c)}")
            return 0
        if a.cmd in LEVELS:
            title = _(LEVELS[a.cmd])
            if a.value is None:
                cur, top = ctl.get_level(a.cmd)
                print(f"{title}: {cur} / {top}")
                return 0
            try:
                value = ctl.adjust_level(a.cmd, a.value)
            except ValueError:
                print(_("error: “{value}” is not a number, +N or -N").format(
                    value=a.value), file=sys.stderr)
                return 2
            msg = f"{title}: {value}"
            _cur, top = ctl.get_level(a.cmd)
            icon, level = osd.ICON_LEVELS[a.cmd], value / (top or 100)
        elif a.cmd == "cross":
            msg = ctl.cross(a.edge)
            if msg is None:
                return 0
            icon = osd.ICON_KEYBOARD
        elif a.cmd == "switch":
            msg = ctl.switch()
        elif a.cmd == "usb":
            icon = osd.ICON_KEYBOARD
            if a.where == "toggle":
                here = ctl.usb_here()
                if here is None:
                    ctl.toggle_usb()
                    msg = _("Toggled keyboard and mouse")
                else:
                    msg = ctl.set_usb(not here)
            else:
                msg = ctl.set_usb(a.where == "here")
        elif a.cmd == "swap":
            ctl.swap_video()
            msg = _("Swapped the inputs")
        elif a.cmd == "pbp":
            on = (not ctl.is_pbp()) if a.state == "toggle" else a.state == "on"
            ctl.set_pbp(on)
            msg = _("Side by side on") if on else _("Side by side off")
        elif a.cmd == "layout":
            if a.name == "list":
                cur = ctl.get_layout()
                layouts = ctl.supported_layouts()
                width = max(len(lay.title) for lay in layouts) + 2
                for lay in layouts:
                    mark = "*" if lay.code == cur else " "
                    print(f"{mark} {lay.key:10} {lay.title:{width}}"
                          f"0x{lay.code:02X}")
                return 0
            if a.name == "next":
                lay = ctl.next_layout()
            else:
                lay = find_layout(a.name)
                if lay is None:
                    print(_("error: unknown layout “{name}”; try “layout "
                            "list”").format(name=a.name), file=sys.stderr)
                    return 2
                ctl.set_layout(lay.code)
            msg = _("Layout: {layout}").format(layout=lay.title)
        elif a.cmd == "input":
            code = int(a.code, 16)
            ctl.set_input(code)
            msg = _("Switched to {input}").format(input=ctl.input_label(code))
        elif a.cmd == "right":
            code = int(a.code, 16)
            ctl.set_right_input(code)
            msg = _("Second input: {input}").format(
                input=ctl.input_label(code))
        if a.cmd == "switch" and ctl.is_pbp():
            icon = osd.ICON_KEYBOARD
        print(msg)
        if not a.quiet:
            osd.feedback(msg, icon, level, ctl.cfg.get("osd", True))
        return 0
    except ddc.DDCError as e:
        print(_("error: {message}").format(message=e), file=sys.stderr)
        if not a.quiet:
            osd.notify(_("Error: {message}").format(message=e))
        return 1
