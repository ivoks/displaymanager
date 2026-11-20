#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open Mullion's window headlessly against the real monitor and report it.

    gui-smoke.py <repo> [--tab display|shortcuts|advanced]
                        [--screenshot out.png] [--config-dir DIR] [--lang hr]

Starts its own gtk4-broadwayd, uses a throwaway config (unless --config-dir)
and in-memory GSettings, and blocks D-Bus calls to GNOME Shell so nothing on
the user's desktop changes. It only *reads* the monitor (the window's first
refresh). Prints the main widget state; --screenshot saves the window as a
PNG you can look at with the Read tool.
"""

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("repo")
    p.add_argument("--tab", default="display")
    p.add_argument("--screenshot")
    p.add_argument("--config-dir")
    p.add_argument("--lang")
    return p.parse_args()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def parent(args) -> int:
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    display = next(d for d in range(40, 99)
                   if not os.path.exists(f"{runtime}/broadway{d + 1}.socket"))
    broadway = subprocess.Popen(
        ["gtk4-broadwayd", f":{display}", "-p", str(free_port())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        sock = f"{runtime}/broadway{display + 1}.socket"
        for _ in range(50):
            if os.path.exists(sock):
                break
            time.sleep(0.1)
        env = dict(os.environ,
                   MULLION_SMOKE_CHILD="1",
                   GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{display}",
                   # No portal or accessibility bus in an SSH session: without
                   # these, GTK/libadwaita startup hangs.
                   ADW_DISABLE_PORTAL="1", GDK_DEBUG="no-portals",
                   GTK_A11Y="none", GSETTINGS_BACKEND="memory",
                   XDG_CONFIG_HOME=args.config_dir or tempfile.mkdtemp(
                       prefix="mullion-smoke-"))
        if args.lang:
            env["LANGUAGE"] = args.lang
        return subprocess.run([sys.executable, "-u", __file__, *sys.argv[1:]],
                              env=env, timeout=60).returncode
    finally:
        broadway.terminate()


def child(args) -> int:
    sys.path.insert(0, os.path.abspath(args.repo))
    import mullion.extension
    mullion.extension._call = lambda *a, **k: None   # never touch the Shell
    import mullion.gui as g
    from gi.repository import Adw, Gio, GLib, Graphene, Gtk

    app = g.App()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)

    def walk(widget):
        yield widget
        child = widget.get_first_child()
        while child:
            yield from walk(child)
            child = child.get_next_sibling()

    def report():
        w = app.get_active_window()
        print("monitor:  ", w.mon_row.get_title(), "|", w.mon_row.get_subtitle())
        active = [hex(c) for c, b in w.layout_btns.items() if b.get_active()]
        print("layout:   ", active, "shown:",
              sorted(hex(c) for c in w.layout_codes))
        print("switch:   ", w.switch_btn.get_label(),
              "| move button visible:", w.usb_btn.get_visible())
        print("levels:   ", {n: int(s.get_value())
                             for n, s in w.level_scales.items()})
        for name, row in (("this", w.this_row), ("other", w.other_row)):
            i = row.get_selected()
            label = w.input_model.get_string(i) if i < len(w.inputs) else None
            print(f"{name + ':':10}", label, "|", repr(row.get_subtitle()))
        print("edge:     ", "on" if w.edge_row.get_active() else "off",
              "| mode row sensitive:", w.edge_mode_row.get_sensitive(),
              "| strength row sensitive:", w.pressure_row.get_sensitive())
        stack = next(x for x in walk(w) if isinstance(x, Adw.ViewStack))
        stack.set_visible_child_name(args.tab)
        GLib.timeout_add(1200, shoot)
        return False

    def shoot():
        if args.screenshot:
            w = app.get_active_window()
            tgt = w.get_content()
            width, height = tgt.get_width(), tgt.get_height()
            snap = Gtk.Snapshot()
            Gtk.WidgetPaintable(widget=tgt).snapshot(snap, width, height)
            node = snap.to_node()
            if node is None:
                print("screenshot: nothing rendered yet")
            else:
                w.get_renderer().render_texture(
                    node, Graphene.Rect().init(0, 0, width, height)
                ).save_to_png(args.screenshot)
                print("screenshot:", args.screenshot)
        app.quit()
        return False

    GLib.timeout_add(4500, report)   # first refresh reads the monitor
    return app.run([])


if __name__ == "__main__":
    a = parse()
    sys.exit(child(a) if os.environ.get("MULLION_SMOKE_CHILD") else parent(a))
