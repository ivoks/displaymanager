# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""GTK4 / libadwaita front end."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import ddc, extension, shortcuts  # noqa: E402
from .controller import LAYOUTS, LEVELS, Controller, Layout  # noqa: E402
from .i18n import _  # noqa: E402

APP_ID = "io.github.ivoks.Mullion"

# What happens when the pointer reaches the edge next to the other computer.
EDGE_MODES = [("button", _("Show a button")), ("push", _("Switch when pushed"))]
# Screen-edge push strengths: px pushed into the edge within a second.
PRESSURES = [(150, _("Light")), (300, _("Medium")), (500, _("Firm"))]


class Window(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="Mullion",
                         default_width=520, default_height=760)
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
                             tooltip_text=_("Refresh monitor state"))
        refresh.connect("clicked", lambda *a: self.refresh(full=True))
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
        stack.add_titled_with_icon(page, "display", _("Display"),
                                   "video-display-symbolic")
        stack.add_titled_with_icon(sc_page, "shortcuts", _("Shortcuts"),
                                   "input-keyboard-symbolic")
        stack.add_titled_with_icon(adv_page, "advanced", _("Advanced"),
                                   "applications-engineering-symbolic")
        view.set_content(stack)
        switcher = Adw.ViewSwitcher(stack=stack,
                                    policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)
        # On narrow windows move the tabs to a bar at the bottom.
        bottom = Adw.ViewSwitcherBar(stack=stack)
        view.add_bottom_bar(bottom)
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 420sp"))
        bp.add_setter(header, "title-widget", Adw.WindowTitle(title="Mullion"))
        bp.add_setter(bottom, "reveal", True)
        self.add_breakpoint(bp)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        # --- monitor ------------------------------------------------------
        g = Adw.PreferencesGroup()
        self.mon_row = Adw.ActionRow(title=_("Looking for monitor…"))
        self.mon_row.add_prefix(Gtk.Image(icon_name=APP_ID + "-symbolic",
                                          pixel_size=32))
        g.add(self.mon_row)
        page.add(g)

        # --- quick switch ---------------------------------------------------
        g = Adw.PreferencesGroup(title=_("Switch"))
        self.switch_btn = Gtk.Button(label=_("Switch Computer"),
                                     css_classes=["pill", "suggested-action"],
                                     halign=Gtk.Align.CENTER)
        self.switch_btn.connect("clicked", self.on_switch)
        g.add(self.switch_btn)
        page.add(g)
        g = Adw.PreferencesGroup()
        self.usb_row = Adw.ActionRow(
            title=GLib.markup_escape_text(_("Keyboard & Mouse")),
            subtitle=_("Hand the monitor’s USB hub to the other computer"))
        self.usb_btn = Gtk.Button(label=_("Move"), valign=Gtk.Align.CENTER)
        self.usb_btn.connect("clicked", self.on_usb)
        self.usb_row.add_suffix(self.usb_btn)
        g.add(self.usb_row)
        self.edge_row = Adw.SwitchRow(
            title=_("Switch at Screen Edge"),
            subtitle=_("Side by side: hand the keyboard and mouse to the "
                       "other computer from the edge next to its picture"),
            active=bool(self.ctl.cfg.get("edge_switch")))
        self.edge_row.connect("notify::active", self.on_edge_switch)
        g.add(self.edge_row)
        self.edge_mode_row = Adw.ComboRow(
            title=_("When the Pointer Reaches the Edge"),
            model=Gtk.StringList.new([title for _m, title in EDGE_MODES]))
        modes = [m for m, _title in EDGE_MODES]
        mode = self.ctl.cfg.get("edge_mode")
        self.edge_mode_row.set_selected(modes.index(mode) if mode in modes else 0)
        self.edge_mode_row.connect("notify::selected", self.on_edge_mode)
        g.add(self.edge_mode_row)
        self.pressure_row = Adw.ComboRow(
            title=_("Push Strength"),
            subtitle=_("How firmly to push into the edge"),
            model=Gtk.StringList.new([title for _p, title in PRESSURES]))
        values = [p for p, _title in PRESSURES]
        current = self.ctl.cfg.get("edge_pressure")
        self.pressure_row.set_selected(values.index(current)
                                       if current in values else 1)
        self.pressure_row.connect("notify::selected", self.on_pressure)
        g.add(self.pressure_row)
        self._sync_edge_rows()
        page.add(g)

        # --- layout ---------------------------------------------------------
        g = Adw.PreferencesGroup(title=_("Layout"),
                                 description=_("How the screen is shared "
                                               "between the two inputs"))
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
        r = Adw.ActionRow(title=_("Swap Inputs"))
        b = Gtk.Button(icon_name="object-flip-horizontal-symbolic",
                       valign=Gtk.Align.CENTER, tooltip_text=_("Swap"))
        b.connect("clicked", lambda *a: self.run(self.ctl.swap,
                                                 _("Swapped the inputs")))
        r.add_suffix(b)
        r.set_activatable_widget(b)
        g.add(r)
        self.second_row = Adw.ComboRow(title=_("Second Input"),
                                       subtitle=_("Right side, or the inset"),
                                       model=self.input_model)
        self.second_row.connect("notify::selected", self.on_second_input)
        g.add(self.second_row)
        page.add(g)

        # --- picture & sound ----------------------------------------------
        g = Adw.PreferencesGroup(
            title=GLib.markup_escape_text(_("Picture & Sound")))
        self.level_scales: dict[str, Gtk.Scale] = {}
        self._level_pending: dict[str, int] = {}
        icons = {"brightness": "display-brightness-symbolic",
                 "contrast": "color-select-symbolic",
                 "volume": "audio-volume-high-symbolic"}
        for name, title in LEVELS.items():
            row = Adw.ActionRow(title=_(title))
            row.add_prefix(Gtk.Image(icon_name=icons[name]))
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,
                                             0, 100, 1)
            scale.set_draw_value(True)
            scale.set_value_pos(Gtk.PositionType.RIGHT)
            scale.set_digits(0)
            scale.set_hexpand(True)
            scale.set_valign(Gtk.Align.CENTER)
            scale.set_size_request(220, -1)
            scale.connect("value-changed", self.on_level_changed, name)
            row.add_suffix(scale)
            self.level_scales[name] = scale
            g.add(row)
        page.add(g)

        # --- inputs ---------------------------------------------------------
        g = Adw.PreferencesGroup(title=_("Computers"),
                                 description=_("Which monitor input each "
                                               "computer is plugged into"))
        self.this_row = Adw.ComboRow(title=_("This Computer"),
                                     model=self.input_model)
        self.other_row = Adw.ComboRow(title=_("Other Computer"),
                                      model=self.input_model)
        self.full_row = Adw.ComboRow(title=_("Show Full Screen"),
                                     subtitle=_("Select the active input "
                                                "directly"),
                                     model=self.input_model)
        self.this_row.connect("notify::selected", self.on_role, "this_input")
        self.other_row.connect("notify::selected", self.on_role, "other_input")
        self.full_row.connect("notify::selected", self.on_full_input)
        detect = Gtk.Button(label=_("Detect"), valign=Gtk.Align.CENTER,
                            tooltip_text=_("Work out which input this "
                                           "computer is plugged into"))
        detect.connect("clicked", self.on_detect_this)
        self.this_row.add_suffix(detect)
        self.other_name = Adw.EntryRow(title=_("Other Computer Name"),
                                       show_apply_button=True)
        self.other_name.connect("apply", self.on_rename)
        for w in (self.this_row, self.other_row, self.other_name, self.full_row):
            g.add(w)
        page.add(g)

        # --- shortcuts tab ---------------------------------------------------
        g = Adw.PreferencesGroup(
            title=_("General"),
            description=_("System-wide GNOME shortcuts. Change the keys in "
                          "Settings → Keyboard → Custom Shortcuts."))
        self.sc_rows = {}
        self.osd_row = Adw.SwitchRow(
            title=_("Show On-Screen Pop-Up"),
            subtitle=_("When a shortcut or the screen edge changes something; "
                       "otherwise a notification is shown"),
            active=bool(self.ctl.cfg.get("osd", True)))
        self.osd_row.connect("notify::active", self.on_osd_switch)
        g.add(self.osd_row)
        self.qs_row = Adw.SwitchRow(
            title=_("Show in Quick Settings"),
            subtitle=_("A Monitor tile in GNOME’s Quick Settings to pick a "
                       "layout, move the keyboard and mouse or swap inputs"),
            active=bool(self.ctl.cfg.get("quick_settings", True)))
        self.qs_row.connect("notify::active", self.on_qs_switch)
        g.add(self.qs_row)
        for key, (_title, _cmd, default) in shortcuts.ACTIONS.items():
            if key in shortcuts.LAYOUT_ACTIONS:
                continue
            g.add(self._shortcut_row(key, shortcuts.title(key), default))
        sc_page.add(g)

        g = Adw.PreferencesGroup(title=_("Layouts"),
                                 description=_("Jump straight to a screen "
                                               "layout"))
        all_btn = Gtk.Button(label=_("Enable All"), css_classes=["flat"],
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
            title=_("Raw VCP Access"),
            description=_("Read or write any DDC/CI feature, e.g. to probe "
                          "manufacturer-specific codes. Writing the wrong "
                          "value can change monitor settings."))
        self.code_entry = Adw.EntryRow(title=_("Feature code (hex, e.g. E7)"))
        self.val_entry = Adw.EntryRow(title=_("Value (hex, for Set)"))
        self.raw_row = Adw.ActionRow(title=_("Result"), subtitle="—",
                                     subtitle_selectable=True)
        box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        for label, cb in ((_("Get"), self.on_raw_get), (_("Set"), self.on_raw_set)):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", cb)
            box.append(btn)
        self.raw_row.add_suffix(box)
        for w in (self.code_entry, self.val_entry, self.raw_row):
            g.add(w)
        adv_page.add(g)

        self.refresh(full=True)
        self.bg(self._sync_extension)

    # ---------------------------------------------------------------- layouts
    @staticmethod
    def _layout_subtitle(lay: Layout) -> str:
        if lay.kind == "pbp":
            a = round(lay.left * 100)
            return f"{a} : {100 - a}"
        return {"single": _("Full screen"),
                "pip": _("Picture in picture")}[lay.kind]

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
            self.toast(res if isinstance(res, str) else ok_msg or _("Done"))
            if then_refresh:
                GLib.timeout_add(2500, lambda: (self.refresh(), False)[1])
        self.bg(fn, done)

    def on_error(self, exc: Exception) -> None:
        msg = str(exc)
        if isinstance(exc, ddc.DDCAccessError):
            self.banner.set_title(_("No access to the monitor’s I2C bus. Run "
                                    "“sudo usermod -aG i2c $USER”, then log "
                                    "out and back in."))
            self.banner.set_revealed(True)
        self.toast(msg)

    # ---------------------------------------------------------------- refresh
    def refresh(self, full: bool = False) -> None:
        def work():
            if full or self.ctl.monitor is None:
                self.ctl.connect()
                self.ctl.autoconfigure()
            inputs = self.ctl.supported_inputs(refresh=False)
            layouts = {lay.code for lay in self.ctl.supported_layouts()}
            return inputs, layouts, self.ctl.status()
        self.bg(work, self._apply_state, self._connect_failed)

    def _connect_failed(self, exc: Exception) -> None:
        self.mon_row.set_title(_("Monitor not reachable"))
        self.mon_row.set_subtitle(GLib.markup_escape_text(str(exc)))
        self.on_error(exc)

    def _apply_state(self, res) -> None:
        inputs, self.layout_codes, st = res
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
                # A combo row always shows some entry, so say when the
                # setting is really empty instead of implying the first one.
                v = cfg.get(key)
                row.set_selected(inputs.index(v) if v in inputs
                                 else Gtk.INVALID_LIST_POSITION)
                row.set_subtitle("" if v in inputs else _("Not set"))
            if st.input in inputs:
                self.full_row.set_selected(inputs.index(st.input))
            for code, btn in self.layout_btns.items():
                btn.set_visible(code in self.layout_codes)
                btn.get_parent().set_visible(code in self.layout_codes)
                if code == st.layout:
                    btn.set_active(True)
            self.layout_box.set_sensitive(st.layout is not None)
            self.second_row.set_sensitive(bool(st.multi))
            for name, scale in self.level_scales.items():
                level = st.levels.get(name)
                scale.get_ancestor(Adw.ActionRow).set_sensitive(level is not None)
                if level and name not in self._level_pending:
                    cur, top = level
                    scale.set_range(0, top)
                    scale.set_value(cur)
            if st.second_input in inputs:
                self.second_row.set_selected(inputs.index(st.second_input))
            other = cfg.get("other_input")
            if other is not None:
                lbl = cfg["input_labels"].get(f"0x{other:02x}", "")
                if self.other_name.get_text() != lbl:
                    self.other_name.set_text(lbl)
        finally:
            self._updating = False

        parts = [_("Serial {serial}").format(serial=mon.serial),
                 f"i2c-{mon.bus}"]
        if st.input is not None:
            parts.append(_("Showing {input}").format(
                input=self.ctl.input_label(st.input)))
        lay = next((x for x in LAYOUTS if x.code == st.layout), None)
        if lay and lay.kind != "single":
            parts.append(lay.title)
            if st.second_input is not None:
                parts.append(_("second: {input}").format(
                    input=self.ctl.input_label(st.second_input)))
        self.mon_row.set_title(mon.model)
        self.mon_row.set_subtitle(GLib.markup_escape_text(" · ".join(parts)))
        self.usb_row.set_subtitle({
            True: _("Connected to this computer"),
            False: _("Connected to the other computer"),
            None: _("Hand the monitor’s USB hub to the other computer"),
        }[st.usb_here])
        self.switch_btn.set_label(_("Move Keyboard & Mouse") if st.multi
                                  else _("Switch Computer"))
        # With two inputs on screen the big button already moves the
        # keyboard and mouse, so the row only shows where they are.
        self.usb_btn.set_visible(not st.multi)
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
                return _("Toggled keyboard and mouse")
            return self.ctl.set_usb(not here)
        self.run(work)

    def on_level_changed(self, scale, name: str):
        """Coalesce slider drags: write at most every 150 ms per setting."""
        if self._updating:
            return
        first = name not in self._level_pending
        self._level_pending[name] = int(scale.get_value())
        if first:
            GLib.timeout_add(150, self._flush_level, name)

    def _flush_level(self, name: str) -> bool:
        value = self._level_pending.get(name)

        def done(_res):
            # A newer value arrived while writing: write that one too.
            if self._level_pending.get(name) != value:
                GLib.timeout_add(150, self._flush_level, name)
            else:
                self._level_pending.pop(name, None)

        def failed(exc):
            self._level_pending.pop(name, None)
            self.on_error(exc)
        self.bg(lambda: self.ctl.set_level(name, value), done, failed)
        return False

    def on_edge_switch(self, row, _p):
        if self._updating:
            return
        on = row.get_active()
        self.ctl.update(edge_switch=on)     # the extension watches this file
        self._sync_edge_rows()

        def done(res):
            if res is None and on:
                self.toast(_("Log out and back in once to finish setting up "
                             "edge switching"))
            elif res is False:
                self.toast(_("GNOME Shell couldn’t enable the edge-switch "
                             "extension"))
        self.bg(lambda: extension.set_enabled(self._extension_wanted()), done)

    def _sync_edge_rows(self):
        on = self.edge_row.get_active()
        self.edge_mode_row.set_sensitive(on)
        push = EDGE_MODES[self.edge_mode_row.get_selected()][0] == "push"
        self.pressure_row.set_sensitive(on and push)

    def on_edge_mode(self, row, _p):
        i = row.get_selected()
        if i < len(EDGE_MODES):
            self.ctl.update(edge_mode=EDGE_MODES[i][0])
        self._sync_edge_rows()

    def on_pressure(self, row, _p):
        i = row.get_selected()
        if i < len(PRESSURES):
            self.ctl.update(edge_pressure=PRESSURES[i][0])

    def _extension_wanted(self) -> bool:
        cfg = self.ctl.cfg
        return bool(cfg.get("edge_switch") or cfg.get("osd", True)
                    or cfg.get("quick_settings", True))

    def on_osd_switch(self, row, _p):
        self.ctl.update(osd=row.get_active())
        self.bg(lambda: extension.set_enabled(self._extension_wanted()))

    def on_qs_switch(self, row, _p):
        self.ctl.update(quick_settings=row.get_active())
        self.bg(lambda: extension.set_enabled(self._extension_wanted()))

    def _sync_extension(self):
        """Keep the extension enabled while a feature needs it."""
        if self._extension_wanted() and extension.info() and \
                not extension.active():
            extension.set_enabled(True)

    def on_layout(self, btn, lay: Layout):
        if self._updating or not btn.get_active():
            return
        self.run(lambda: self.ctl.set_layout(lay.code),
                 _("Layout: {layout}").format(layout=lay.title))

    def on_role(self, row, _p, key):
        if self._updating:
            return
        i = row.get_selected()
        if i == Gtk.INVALID_LIST_POSITION or i >= len(self.inputs):
            return
        self.ctl.update(**{key: self.inputs[i]})
        row.set_subtitle("")

    def on_full_input(self, row, _p):
        if self._updating:
            return
        i = row.get_selected()
        if i < len(self.inputs):
            code = self.inputs[i]
            self.run(lambda: self.ctl.set_input(code),
                     _("Switching to {input}").format(
                         input=self.ctl.input_label(code)))

    def on_second_input(self, row, _p):
        if self._updating:
            return
        i = row.get_selected()
        if i < len(self.inputs):
            code = self.inputs[i]
            self.run(lambda: self.ctl.set_second_input(code),
                     _("Second input: {input}").format(
                         input=self.ctl.input_label(code)))

    def on_detect_this(self, _b):
        def done(res):
            code, why = res
            if code is None:
                self.toast(_("Couldn’t tell which input this is ({reason}); "
                             "choose it from the list").format(reason=why))
                return
            if code not in self.inputs:
                self.toast(_("Detected input {code} is not in the list")
                           .format(code=f"0x{code:02X}"))
                return
            self.ctl.update(this_input=code)
            self._updating = True
            self.this_row.set_selected(self.inputs.index(code))
            self.this_row.set_subtitle("")
            self._updating = False
            self.toast(_("This computer: {input}").format(
                input=self.ctl.input_label(code)))
        self.bg(self.ctl.detect_this_input, done)

    def on_rename(self, entry):
        other = self.ctl.cfg.get("other_input")
        if other is None:
            self.toast(_("Pick the other computer’s input first"))
            return
        name = entry.get_text().strip()
        labels = dict(self.ctl.cfg["input_labels"])
        if name:
            labels[f"0x{other:02x}"] = name
        else:
            labels.pop(f"0x{other:02x}", None)
        self.ctl.update(input_labels=labels)
        self.inputs = []          # force relabel
        self.refresh()

    def _shortcut_row(self, key: str, title: str, default: str) -> Adw.SwitchRow:
        cur = shortcuts.current(key)
        row = Adw.SwitchRow(title=GLib.markup_escape_text(title),
                            active=cur is not None)
        self._update_shortcut_subtitle(row, key, cur or default)
        row.connect("notify::active", self.on_shortcut, key)
        self.sc_rows[key] = row
        return row

    def _update_shortcut_subtitle(self, row, key: str, accel: str) -> None:
        text = shortcuts.label(accel)
        if shortcuts.keypad_twin(accel):
            text += " " + _("(also on the number pad)")
        taken = shortcuts.conflicts(accel, key)
        if taken:
            text += " · " + _("already used by {users}").format(
                users=", ".join(taken))
        row.set_subtitle(GLib.markup_escape_text(text))

    def on_enable_layout_shortcuts(self, _btn):
        failed = []
        for key in shortcuts.LAYOUT_ACTIONS:
            row = self.sc_rows.get(key)
            if row and not row.get_active():
                row.set_active(True)        # triggers on_shortcut
                if not row.get_active():
                    failed.append(row.get_title())
        self.toast(_("Couldn’t enable: {shortcuts}").format(
            shortcuts=", ".join(failed)) if failed
            else _("Layout shortcuts enabled"))

    def on_shortcut(self, row, _p, key):
        if self._updating:
            return
        default = shortcuts.ACTIONS[key][2]
        try:
            shortcuts.assign(key, default if row.get_active() else None)
        except Exception as e:  # noqa: BLE001
            self.toast(str(e))
            self._updating = True
            row.set_active(False)
            self._updating = False
        self._update_shortcut_subtitle(row, key, default)

    def _raw_code(self):
        try:
            return int(self.code_entry.get_text().strip(), 16)
        except ValueError:
            self.toast(_("Enter a feature code in hex"))
            return None

    def on_raw_get(self, _b):
        code = self._raw_code()
        if code is None:
            return

        def done(v):
            self.raw_row.set_subtitle(
                _("VCP {code}: value {value}, raw {raw}").format(
                    code=f"{code:02X}", value=f"0x{v.value:04X}",
                    raw=" ".join(f"{b:02X}" for b in v.raw)))
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
            self.toast(_("Enter a value in hex"))
            return
        self.run(lambda: ddc.setvcp(self.ctl.bus, code, val),
                 _("Wrote {value} to VCP {code}").format(
                     value=f"0x{val:X}", code=f"{code:02X}"))


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
