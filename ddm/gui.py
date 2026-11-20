# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""GTK4 / libadwaita front end."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import ddc, shortcuts  # noqa: E402
from .controller import LAYOUTS, Controller, Layout, save_config  # noqa: E402

APP_ID = "io.github.DisplayManager"


class Window(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="DisplayManager",
                         default_width=520, default_height=760)
        try:
            shortcuts.migrate_legacy()
        except Exception:  # noqa: BLE001
            pass
        self.ctl = Controller()
        self.inputs: list[int] = []
        self._updating = False
        self._busy = 0
        self.layout_codes = {lay.code for lay in LAYOUTS}

        self.input_model = Gtk.StringList()
        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.spinner = Adw.Spinner(visible=False)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic",
                             tooltip_text="Refresh monitor state")
        refresh.connect("clicked", lambda *_: self.refresh(full=True))
        header.pack_start(refresh)
        header.pack_end(self.spinner)
        view.add_top_bar(header)

        self.banner = Adw.Banner(revealed=False)
        view.add_top_bar(self.banner)

        # Tabs: everyday controls, shortcuts, and low-level tools.
        page = Adw.PreferencesPage()
        sc_page = Adw.PreferencesPage()
        adv_page = Adw.PreferencesPage()
        stack = Adw.ViewStack()
        stack.add_titled_with_icon(page, "display", "Display",
                                   "video-display-symbolic")
        stack.add_titled_with_icon(sc_page, "shortcuts", "Shortcuts",
                                   "input-keyboard-symbolic")
        stack.add_titled_with_icon(adv_page, "advanced", "Advanced",
                                   "applications-engineering-symbolic")
        view.set_content(stack)
        switcher = Adw.ViewSwitcher(stack=stack,
                                    policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)
        # On narrow windows move the tabs to a bar at the bottom.
        bottom = Adw.ViewSwitcherBar(stack=stack)
        view.add_bottom_bar(bottom)
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 420sp"))
        bp.add_setter(header, "title-widget", Adw.WindowTitle(title="DisplayManager"))
        bp.add_setter(bottom, "reveal", True)
        self.add_breakpoint(bp)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        # --- monitor ------------------------------------------------------
        g = Adw.PreferencesGroup()
        self.mon_row = Adw.ActionRow(title="Looking for monitor…")
        self.mon_row.add_prefix(Gtk.Image(icon_name=APP_ID + "-symbolic",
                                          pixel_size=32))
        g.add(self.mon_row)
        page.add(g)

        # --- quick switch ---------------------------------------------------
        g = Adw.PreferencesGroup(title="Switch")
        self.switch_btn = Gtk.Button(label="Switch Computer",
                                     css_classes=["pill", "suggested-action"],
                                     halign=Gtk.Align.CENTER)
        self.switch_btn.connect("clicked", self.on_switch)
        g.add(self.switch_btn)
        page.add(g)
        g = Adw.PreferencesGroup()
        self.usb_row = Adw.ActionRow(
            title="Keyboard &amp; Mouse",
            subtitle="Hand the monitor's USB hub to the other computer")
        self.usb_btn = Gtk.Button(label="Move", valign=Gtk.Align.CENTER)
        self.usb_btn.connect("clicked", self.on_usb)
        self.usb_row.add_suffix(self.usb_btn)
        g.add(self.usb_row)
        page.add(g)

        # --- layout ---------------------------------------------------------
        g = Adw.PreferencesGroup(title="Layout",
                                 description="How the screen is shared between "
                                             "the two inputs")
        self.layout_box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                      homogeneous=True, column_spacing=6,
                                      row_spacing=6, max_children_per_line=4,
                                      min_children_per_line=2)
        self.layout_btns: dict[int, Gtk.ToggleButton] = {}
        group_leader = None
        for lay in LAYOUTS:
            btn = self._layout_button(lay)
            if group_leader is None:
                group_leader = btn
            else:
                btn.set_group(group_leader)
            btn.connect("toggled", self.on_layout, lay)
            self.layout_btns[lay.code] = btn
            self.layout_box.append(btn)
        g.add(self.layout_box)
        page.add(g)
        g = Adw.PreferencesGroup()
        r = Adw.ActionRow(title="Swap Inputs")
        b = Gtk.Button(icon_name="object-flip-horizontal-symbolic",
                       valign=Gtk.Align.CENTER, tooltip_text="Swap")
        b.connect("clicked", lambda *_: self.run(self.ctl.swap_video,
                                                 "Swapped left and right"))
        r.add_suffix(b)
        r.set_activatable_widget(b)
        g.add(r)
        self.right_row = Adw.ComboRow(title="Second Input",
                                      subtitle="Right side, or the inset",
                                      model=self.input_model)
        self.right_row.connect("notify::selected", self.on_right_input)
        g.add(self.right_row)
        page.add(g)

        # --- inputs ---------------------------------------------------------
        g = Adw.PreferencesGroup(title="Computers",
                                 description="Which monitor input each computer "
                                             "is plugged into")
        self.this_row = Adw.ComboRow(title="This Computer",
                                     model=self.input_model)
        self.other_row = Adw.ComboRow(title="Other Computer",
                                      model=self.input_model)
        self.full_row = Adw.ComboRow(title="Show Full Screen",
                                     subtitle="Select the active input directly",
                                     model=self.input_model)
        self.this_row.connect("notify::selected", self.on_role, "this_input")
        self.other_row.connect("notify::selected", self.on_role, "other_input")
        self.full_row.connect("notify::selected", self.on_full_input)
        detect = Gtk.Button(label="Detect", valign=Gtk.Align.CENTER,
                            tooltip_text="Use the input currently shown")
        detect.connect("clicked", self.on_detect_this)
        self.this_row.add_suffix(detect)
        self.other_name = Adw.EntryRow(title="Other Computer Name",
                                       show_apply_button=True)
        self.other_name.connect("apply", self.on_rename)
        for w in (self.this_row, self.other_row, self.other_name, self.full_row):
            g.add(w)
        page.add(g)

        # --- shortcuts tab ---------------------------------------------------
        g = Adw.PreferencesGroup(
            title="General",
            description="System-wide GNOME shortcuts. Change the keys in "
                        "Settings → Keyboard → Custom Shortcuts.")
        self.sc_rows = {}
        for key, (name, _cmd, default) in shortcuts.ACTIONS.items():
            if key in shortcuts.LAYOUT_ACTIONS:
                continue
            g.add(self._shortcut_row(
                key, name.split(": ", 1)[1].capitalize(), default))
        sc_page.add(g)

        g = Adw.PreferencesGroup(title="Layouts",
                                 description="Jump straight to a screen layout")
        all_btn = Gtk.Button(label="Enable All", css_classes=["flat"],
                             valign=Gtk.Align.CENTER)
        all_btn.connect("clicked", self.on_enable_layout_shortcuts)
        g.set_header_suffix(all_btn)
        for lay in LAYOUTS:
            key = f"layout-{lay.key}"
            g.add(self._shortcut_row(
                key, f"{lay.title} ({self._layout_subtitle(lay)})",
                shortcuts.ACTIONS[key][2]))
        sc_page.add(g)

        # --- advanced tab ----------------------------------------------------
        g = Adw.PreferencesGroup(
            title="Raw VCP Access",
            description="Read or write any DDC/CI feature, e.g. to probe "
                        "manufacturer-specific codes. Writing the wrong value "
                        "can change monitor settings.")
        self.code_entry = Adw.EntryRow(title="Feature code (hex, e.g. E7)")
        self.val_entry = Adw.EntryRow(title="Value (hex, for Set)")
        self.raw_row = Adw.ActionRow(title="Result", subtitle="—",
                                     subtitle_selectable=True)
        box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        for label, cb in (("Get", self.on_raw_get), ("Set", self.on_raw_set)):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", cb)
            box.append(btn)
        self.raw_row.add_suffix(box)
        for w in (self.code_entry, self.val_entry, self.raw_row):
            g.add(w)
        adv_page.add(g)

        self.refresh(full=True)

    # ---------------------------------------------------------------- layouts
    @staticmethod
    def _layout_subtitle(lay: Layout) -> str:
        if lay.kind == "pbp":
            a = round(lay.left * 100)
            return f"{a} : {100 - a}"
        return {"single": "Full screen", "pip": "Picture in picture"}[lay.kind]

    def _layout_button(self, lay: Layout) -> Gtk.ToggleButton:
        area = Gtk.DrawingArea(content_width=96, content_height=44,
                               halign=Gtk.Align.CENTER)
        area.set_draw_func(self._draw_layout, lay)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                      margin_top=6, margin_bottom=6)
        box.append(area)
        box.append(Gtk.Label(label=lay.title))
        box.append(Gtk.Label(label=self._layout_subtitle(lay),
                             css_classes=["caption", "dim-label"]))
        btn = Gtk.ToggleButton(child=box, css_classes=["flat"],
                               tooltip_text=f"{lay.title} (VCP E9 = 0x{lay.code:02X})")
        return btn

    @staticmethod
    def _draw_layout(_area, cr, w, h, lay: Layout):
        def rect(x, y, rw, rh, rgb, r=3.0):
            cr.new_sub_path()
            cr.arc(x + rw - r, y + r, r, -1.5708, 0)
            cr.arc(x + rw - r, y + rh - r, r, 0, 1.5708)
            cr.arc(x + r, y + rh - r, r, 1.5708, 3.1416)
            cr.arc(x + r, y + r, r, 3.1416, 4.7124)
            cr.close_path()
            cr.set_source_rgb(*rgb)
            cr.fill()
        main, second = (0.21, 0.52, 0.89), (0.20, 0.82, 0.48)
        bezel = (0.24, 0.22, 0.27)
        rect(0, 0, w, h, bezel, 5)
        x0, y0, iw, ih, gap = 3, 3, w - 6, h - 6, 2
        if lay.kind == "single":
            rect(x0, y0, iw, ih, main)
        elif lay.kind == "pbp":
            lw = round((iw - gap) * lay.left)
            rect(x0, y0, lw, ih, main)
            rect(x0 + lw + gap, y0, iw - lw - gap, ih, second)
        else:
            rect(x0, y0, iw, ih, main)
            f = 0.30 if lay.key == "pip-small" else 0.45
            pw, ph = iw * f, ih * f
            cr.set_source_rgb(*bezel)
            rect(x0 + iw - pw - 4, y0 + ih - ph - 4, pw + 2, ph + 2, bezel, 2)
            rect(x0 + iw - pw - 3, y0 + ih - ph - 3, pw, ph, second, 2)

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _accel_text(accel: str) -> str:
        ok, key, mods = Gtk.accelerator_parse(accel)
        return Gtk.accelerator_get_label(key, mods) if ok else accel

    def toast(self, msg: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(msg),
                                        timeout=3))

    def _set_busy(self, delta: int) -> None:
        self._busy += delta
        self.spinner.set_visible(self._busy > 0)

    def bg(self, fn, done=None, error=None):
        """Run fn() in a worker thread, deliver result on the main loop."""
        self._set_busy(1)

        def work():
            try:
                res, exc = fn(), None
            except Exception as e:  # noqa: BLE001
                res, exc = None, e

            def finish():
                self._set_busy(-1)
                if exc is not None:
                    (error or self.on_error)(exc)
                elif done:
                    done(res)
                return False
            GLib.idle_add(finish)
        threading.Thread(target=work, daemon=True).start()

    def run(self, fn, ok_msg: str | None = None, then_refresh: bool = True):
        def done(res):
            self.toast(res if isinstance(res, str) else ok_msg or "Done")
            if then_refresh:
                GLib.timeout_add(2500, lambda: (self.refresh(), False)[1])
        self.bg(fn, done)

    def on_error(self, exc: Exception) -> None:
        msg = str(exc)
        if "permission denied" in msg.lower():
            self.banner.set_title("No access to the monitor's I2C bus. Run: "
                                  "sudo usermod -aG i2c $USER, then log out and in.")
            self.banner.set_revealed(True)
        self.toast(msg)

    # ---------------------------------------------------------------- refresh
    def refresh(self, full: bool = False) -> None:
        def work():
            if full or self.ctl.monitor is None:
                self.ctl.connect()
            inputs = self.ctl.supported_inputs(refresh=False)
            self.layout_codes = {lay.code for lay in self.ctl.supported_layouts()}
            return inputs, self.ctl.status()
        self.bg(work, self._apply_state, self._connect_failed)

    def _connect_failed(self, exc: Exception) -> None:
        self.mon_row.set_title("Monitor not reachable")
        self.mon_row.set_subtitle(GLib.markup_escape_text(str(exc)))
        self.on_error(exc)

    def _apply_state(self, res) -> None:
        inputs, st = res
        self.banner.set_revealed(False)
        mon = self.ctl.monitor
        self._updating = True
        try:
            if inputs != self.inputs:
                self.inputs = inputs
                self.input_model.splice(0, self.input_model.get_n_items(),
                                        [self.ctl.input_label(c) for c in inputs])
            cfg = self.ctl.cfg
            for row, key in ((self.this_row, "this_input"),
                             (self.other_row, "other_input")):
                v = cfg.get(key)
                row.set_selected(inputs.index(v) if v in inputs
                                 else Gtk.INVALID_LIST_POSITION)
            if st.input in inputs:
                self.full_row.set_selected(inputs.index(st.input))
            for code, btn in self.layout_btns.items():
                btn.set_visible(code in self.layout_codes)
                btn.get_parent().set_visible(code in self.layout_codes)
                if code == st.pxp_raw:
                    btn.set_active(True)
            self.layout_box.set_sensitive(st.pxp_raw is not None)
            self.right_row.set_sensitive(bool(st.pbp))
            if st.right_input in inputs:
                self.right_row.set_selected(inputs.index(st.right_input))
            other = cfg.get("other_input")
            if other is not None:
                lbl = cfg["input_labels"].get(f"0x{other:02x}", "")
                if self.other_name.get_text() != lbl:
                    self.other_name.set_text(lbl)
        finally:
            self._updating = False

        parts = [f"Serial {mon.serial}", f"i2c-{mon.bus}"]
        if st.input is not None:
            parts.append("Showing " + self.ctl.input_label(st.input))
        lay = next((x for x in LAYOUTS if x.code == st.pxp_raw), None)
        if lay and lay.kind != "single":
            parts.append(lay.title)
            if st.right_input is not None:
                parts.append("second: " + self.ctl.input_label(st.right_input))
        self.mon_row.set_title(mon.model)
        self.mon_row.set_subtitle(GLib.markup_escape_text(" · ".join(parts)))
        self.usb_row.set_subtitle({
            True: "Connected to this computer",
            False: "Connected to the other computer",
            None: "Hand the monitor's USB hub to the other computer",
        }[st.usb_here])
        self.switch_btn.set_label("Move Keyboard & Mouse" if st.pbp
                                  else "Switch Computer")
        # With two inputs on screen the big button already moves the
        # keyboard and mouse, so the row only shows where they are.
        self.usb_btn.set_visible(not st.pbp)
        if st.error:
            self.toast(st.error)

    # ---------------------------------------------------------------- handlers
    def on_switch(self, _btn):
        self.run(self.ctl.switch)

    def on_usb(self, _b):
        def work():
            here = self.ctl.usb_here()
            if here is None:
                self.ctl.toggle_usb()
                return "Toggled keyboard and mouse"
            return self.ctl.set_usb(not here)
        self.run(work)

    def on_layout(self, btn, lay: Layout):
        if self._updating or not btn.get_active():
            return
        self.run(lambda: self.ctl.set_layout(lay.code), f"Layout: {lay.title}")

    def on_role(self, row, _p, key):
        if self._updating:
            return
        i = row.get_selected()
        if i == Gtk.INVALID_LIST_POSITION or i >= len(self.inputs):
            return
        self.ctl.cfg[key] = self.inputs[i]
        save_config(self.ctl.cfg)

    def on_full_input(self, row, _p):
        if self._updating:
            return
        i = row.get_selected()
        if i < len(self.inputs):
            code = self.inputs[i]
            self.run(lambda: self.ctl.set_input(code),
                     f"Switching to {self.ctl.input_label(code)}")

    def on_right_input(self, row, _p):
        if self._updating:
            return
        i = row.get_selected()
        if i < len(self.inputs):
            code = self.inputs[i]
            self.run(lambda: self.ctl.set_right_input(code),
                     f"Right side: {self.ctl.input_label(code)}")

    def on_detect_this(self, _b):
        def done(code):
            if code not in self.inputs:
                self.toast(f"Current input 0x{code:02X} is not in the list")
                return
            self.ctl.cfg["this_input"] = code
            save_config(self.ctl.cfg)
            self._updating = True
            self.this_row.set_selected(self.inputs.index(code))
            self._updating = False
            self.toast(f"This computer: {self.ctl.input_label(code)}")
        self.bg(self.ctl.get_input, done)

    def on_rename(self, entry):
        other = self.ctl.cfg.get("other_input")
        if other is None:
            self.toast("Pick the other computer's input first")
            return
        name = entry.get_text().strip()
        labels = self.ctl.cfg["input_labels"]
        if name:
            labels[f"0x{other:02x}"] = name
        else:
            labels.pop(f"0x{other:02x}", None)
        save_config(self.ctl.cfg)
        self.inputs = []          # force relabel
        self.refresh()

    def _shortcut_row(self, key: str, title: str, default: str) -> Adw.SwitchRow:
        cur = shortcuts.get(key)
        row = Adw.SwitchRow(title=GLib.markup_escape_text(title),
                            subtitle=self._accel_text(cur or default),
                            active=cur is not None)
        row.connect("notify::active", self.on_shortcut, key)
        self.sc_rows[key] = row
        return row

    def on_enable_layout_shortcuts(self, _btn):
        for key in shortcuts.LAYOUT_ACTIONS:
            row = self.sc_rows.get(key)
            if row and not row.get_active():
                row.set_active(True)        # triggers on_shortcut
        self.toast("Layout shortcuts enabled")

    def on_shortcut(self, row, _p, key):
        accel = shortcuts.ACTIONS[key][2] if row.get_active() else None
        try:
            shortcuts.set(key, accel)
        except Exception as e:  # noqa: BLE001
            self.toast(str(e))

    def _raw_code(self):
        try:
            return int(self.code_entry.get_text().strip(), 16)
        except ValueError:
            self.toast("Enter a feature code in hex")
            return None

    def on_raw_get(self, _b):
        code = self._raw_code()
        if code is None:
            return

        def done(v):
            self.raw_row.set_subtitle(
                f"VCP {code:02X}: value 0x{v.value:04X}  raw "
                + " ".join(f"{b:02X}" for b in v.raw))
        self.bg(lambda: ddc.getvcp(self.ctl.bus, code), done,
                lambda e: self.raw_row.set_subtitle(
                    GLib.markup_escape_text(str(e))))

    def on_raw_set(self, _b):
        code = self._raw_code()
        if code is None:
            return
        try:
            val = int(self.val_entry.get_text().strip(), 16)
        except ValueError:
            self.toast("Enter a value in hex")
            return
        self.run(lambda: ddc.setvcp(self.ctl.bus, code, val),
                 f"Wrote 0x{val:X} to VCP {code:02X}")


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self):
        Adw.Application.do_startup(self)
        # When run from a source checkout, find the bundled icons too.
        from gi.repository import Gdk
        import os
        icons = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data", "icons")
        display = Gdk.Display.get_default()
        if display and os.path.isdir(icons):
            Gtk.IconTheme.get_for_display(display).add_search_path(icons)
        Gtk.Window.set_default_icon_name(APP_ID)

    def do_activate(self):
        win = self.get_active_window() or Window(self)
        win.present()


def main() -> int:
    return App().run([])
