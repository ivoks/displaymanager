# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""Command line interface (used by the GNOME keyboard shortcuts)."""

from __future__ import annotations

import argparse
import sys

from . import ddc
from .controller import Controller


def _notify(msg: str) -> None:
    """Best-effort desktop notification so shortcut presses give feedback."""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        from gi.repository import GLib
        bus.call_sync("org.freedesktop.Notifications",
                      "/org/freedesktop/Notifications",
                      "org.freedesktop.Notifications", "Notify",
                      GLib.Variant("(susssasa{sv}i)",
                                   ("DisplayManager", 0,
                                    "video-display-symbolic", msg, "", [],
                                    {"transient": GLib.Variant("b", True)},
                                    2000)),
                      None, Gio.DBusCallFlags.NONE, 2000, None)
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="displaymanager",
                                description="Control a Dell monitor's inputs, "
                                            "PBP and KVM over DDC/CI. "
                                            "Run without arguments for the GUI.")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="no desktop notification")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show monitor state")
    sub.add_parser("switch", help="smart switch: move KVM in PBP, "
                                  "otherwise flip full-screen input")
    s = sub.add_parser("usb", help="keyboard & mouse: here, away or toggle")
    s.add_argument("where", nargs="?", default="toggle",
                   choices=["here", "away", "toggle"])
    sub.add_parser("swap", help="swap PBP left/right")
    s = sub.add_parser("pbp", help="picture-by-picture on/off/toggle")
    s.add_argument("state", choices=["on", "off", "toggle"])
    s = sub.add_parser("input", help="select input by hex code, e.g. 0x1b")
    s.add_argument("code")
    s = sub.add_parser("right", help="select PBP right-side input, e.g. 0x19")
    s.add_argument("code")
    sub.add_parser("inputs", help="list inputs reported by the monitor")
    a = p.parse_args(argv)

    ctl = Controller()
    try:
        mon = ctl.connect()
        msg = None
        if a.cmd == "status":
            st = ctl.status()
            print(f"Monitor:  {mon.model}  serial {mon.serial}  "
                  f"{mon.connector}  /dev/i2c-{mon.bus}")
            print(f"Input:    {ctl.input_label(st.input)} (0x{st.input:02X})"
                  if st.input is not None else f"Input:    ? {st.error}")
            print(f"PBP:      {'on' if st.pbp else 'off'} (E9=0x{st.pxp_raw:02X})"
                  if st.pxp_raw is not None else "PBP:      unknown")
            if st.right_input is not None:
                print(f"Right:    {ctl.input_label(st.right_input)} "
                      f"(0x{st.right_input:02X})")
            kvm = {True: "this computer", False: "other computer",
                   None: "unknown"}[st.usb_here]
            print(f"USB/KVM:  {kvm}")
            for k in ("this_input", "other_input"):
                v = ctl.cfg.get(k)
                print(f"{k.split('_')[0].capitalize() + ':':10}{ctl.input_label(v) if v is not None else 'not set'}")
            return 0
        if a.cmd == "inputs":
            for c in ctl.supported_inputs(refresh=True):
                print(f"0x{c:02X}  {ctl.input_label(c)}")
            return 0
        if a.cmd == "switch":
            msg = ctl.switch()
        elif a.cmd == "usb":
            if a.where == "toggle":
                here = ctl.usb_here()
                if here is None:
                    ctl.toggle_usb()
                    msg = "Toggled keyboard and mouse"
                else:
                    msg = ctl.set_usb(not here)
            else:
                msg = ctl.set_usb(a.where == "here")
        elif a.cmd == "swap":
            ctl.swap_video()
            msg = "Swapped left and right"
        elif a.cmd == "pbp":
            on = (not ctl.is_pbp()) if a.state == "toggle" else a.state == "on"
            ctl.set_pbp(on)
            msg = "Side by side " + ("on" if on else "off")
        elif a.cmd == "input":
            code = int(a.code, 16)
            ctl.set_input(code)
            msg = f"Switched to {ctl.input_label(code)}"
        elif a.cmd == "right":
            code = int(a.code, 16)
            ctl.set_right_input(code)
            msg = f"Right side: {ctl.input_label(code)}"
        print(msg)
        if not a.quiet:
            _notify(msg)
        return 0
    except ddc.DDCError as e:
        print(f"error: {e}", file=sys.stderr)
        if not a.quiet:
            _notify(f"Error: {e}")
        return 1
