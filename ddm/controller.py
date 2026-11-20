# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""High level operations shared by the GUI and the command line."""

from __future__ import annotations

import glob
import json
import os
import re
import time
from dataclasses import dataclass

from . import ddc
from .i18n import N_, _

_XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
CONFIG_DIR = os.path.join(_XDG_CONFIG, "displaymanager")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# MCCS standard input codes (VCP 0x60) plus the values Dell uses.
INPUT_NAMES = {      # connector names; not translated
    0x01: "VGA", 0x03: "DVI-1", 0x04: "DVI-2",
    0x0F: "DisplayPort-1", 0x10: "DisplayPort-2",
    0x11: "HDMI-1", 0x12: "HDMI-2",
    0x19: "Thunderbolt", 0x1B: "USB-C", 0x1C: "USB-C 2",
}

@dataclass(frozen=True)
class Layout:
    code: int        # value of VCP E9 (PxP mode)
    key: str         # CLI name
    name: str        # English title (msgid); use .title for display
    kind: str        # "single" | "pbp" | "pip"
    left: float = 1.0  # share of the width given to the main (left) input

    @property
    def title(self) -> str:
        return _(self.name)


# Measured on a U4025QW by watching the resolution the right-hand source is
# given in each mode (panel is 5120x2160).
LAYOUTS = [
    Layout(0x00, "single", N_("Single"), "single"),
    Layout(0x24, "50-50", N_("Even Split"), "pbp", 0.50),
    Layout(0x2A, "75-25", N_("Wide Left"), "pbp", 0.75),
    Layout(0x28, "80-20", N_("Wider Left"), "pbp", 0.80),
    Layout(0x29, "25-75", N_("Wide Right"), "pbp", 0.25),
    Layout(0x27, "20-80", N_("Wider Right"), "pbp", 0.20),
    Layout(0x21, "pip-small", N_("Small Inset"), "pip"),
    Layout(0x22, "pip-large", N_("Large Inset"), "pip"),
]
LAYOUT_BY_CODE = {lay.code: lay for lay in LAYOUTS}

# Continuous settings with sliders: name -> translatable title.
LEVELS = {
    "brightness": N_("Brightness"),
    "contrast": N_("Contrast"),
    "volume": N_("Volume"),
}


def find_layout(name: str) -> Layout | None:
    name = name.strip().lower().replace("/", "-").replace(":", "-")
    for lay in LAYOUTS:
        if name in (lay.key, lay.name.lower(), lay.title.lower()):
            return lay
    try:
        return LAYOUT_BY_CODE.get(int(name, 16))
    except ValueError:
        return None


# Which VCP 60 input codes can feed which kind of DRM connector.
HDMI_INPUTS = {0x11, 0x12}
DP_INPUTS = {0x0F, 0x10}
USBC_INPUTS = {0x19, 0x1B, 0x1C}      # Thunderbolt / USB-C (DisplayPort inside)
DVI_INPUTS = {0x03, 0x04}
VGA_INPUTS = {0x01}


def _connector_inputs(connector: str) -> set[int] | None:
    """Input codes that could be on the other end of a DRM connector,
    e.g. "card1-DP-1" -> DisplayPort or USB-C/Thunderbolt inputs."""
    kind = re.sub(r"^card\d+-|-\d+$", "", connector).upper()
    if kind.startswith("HDMI"):
        return HDMI_INPUTS
    if kind in ("DP", "EDP"):
        return DP_INPUTS | USBC_INPUTS
    if kind.startswith("DVI"):
        return DVI_INPUTS | HDMI_INPUTS
    if kind == "VGA":
        return VGA_INPUTS
    return None


def _usb_c_video_possible() -> bool:
    """False when this machine has no Thunderbolt/USB4 device and no USB-C
    DisplayPort partner, i.e. its video cannot be reaching the monitor's
    USB-C / Thunderbolt input."""
    for d in glob.glob("/sys/bus/thunderbolt/devices/*"):
        if re.fullmatch(r"\d+-[1-9][0-9a-f]*", os.path.basename(d)):
            return True                  # a device beyond the host router
    if glob.glob("/sys/class/typec/port*-partner"):
        return True
    if not os.path.isdir("/sys/bus/thunderbolt") and \
            not os.path.isdir("/sys/class/typec"):
        return True                      # no information: don't rule it out
    return False


DEFAULTS = {
    "monitor_serial": None,     # pick this monitor if several are attached
    "bus": None,                # cached bus once probed
    "this_input": None,         # VCP 60 value this computer is plugged into
    "other_input": None,        # VCP 60 value of the other computer (Mac)
    "input_labels": {},         # {"0x1b": "MacBook"}
    "inputs": None,             # cached list of supported input codes
    "layouts": None,            # cached E9 values the monitor accepts
    "last_layout": 0x24,        # multi-view layout restored by "pbp on"
    "panel_width": 5120,        # native width, for telling PBP sides apart
    "edge_switch": False,       # move the KVM when the pointer hits the edge
    "connector": None,          # e.g. "DP-1"; read by the GNOME extension
    # USB devices that live behind the monitor's KVM-switched hub; if any is
    # present on this machine, the keyboard/mouse are here.  (U4025QW:
    # Realtek HID functions on the switched sub-hubs.)  The monitor does not
    # report KVM state over DDC, so we infer it from USB.
    "kvm_marker_usb": ["0bda:1100", "0bda:1101"],
    # Dell manufacturer specific VCP codes (overridable for other models)
    "vcp": {
        "input": 0x60,
        "pxp_mode": 0xE9, "pbp_on": 0x24, "pxp_off": 0x00,
        "pbp_right_input": 0xE8,
        "swap_video": 0xE5, "swap_video_value": 0xF001,
        "usb": 0xE7, "usb_toggle_value": 0xFF00,
        "brightness": 0x10, "contrast": 0x12, "volume": 0x62,
    },
}


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CONFIG_FILE) as f:
            user = json.load(f)
        vcp = user.pop("vcp", {})
        cfg.update(user)
        cfg["vcp"].update({k: int(v, 0) if isinstance(v, str) else v
                           for k, v in vcp.items()})
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    out = dict(cfg)
    out["vcp"] = {k: f"0x{v:02X}" for k, v in cfg["vcp"].items()}
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, CONFIG_FILE)


@dataclass
class Status:
    input: int | None = None
    pbp: bool | None = None
    pxp_raw: int | None = None
    right_input: int | None = None
    usb_raw: int | None = None
    usb_here: bool | None = None
    levels: dict = None             # {"brightness": (cur, max), ...}
    error: str | None = None


class Controller:
    def __init__(self):
        self.cfg = load_config()
        self.monitor: ddc.Monitor | None = None

    # ---- discovery -------------------------------------------------------
    def connect(self) -> ddc.Monitor:
        mons = ddc.find_monitors()
        dells = [m for m in mons if m.model.upper().startswith("DELL")]
        pool = dells or mons
        if not pool:
            raise ddc.DDCError(_("No monitor found on any display connector"))
        want = self.cfg.get("monitor_serial")
        mon = next((m for m in pool if want and m.serial == want), pool[0])
        cached = self.cfg.get("bus")
        if cached in mon.buses and ddc.bus_accessible(cached):
            mon.bus = cached
        else:
            ddc.probe_bus(mon)
            if mon.bus != cached:
                self.cfg["bus"] = mon.bus
                self.cfg["monitor_serial"] = mon.serial
                save_config(self.cfg)
        connector = mon.connector.split("-", 1)[1]
        if self.cfg.get("connector") != connector:
            self.cfg["connector"] = connector
            save_config(self.cfg)
        self.monitor = mon
        return mon

    @property
    def bus(self) -> int:
        if not self.monitor or self.monitor.bus is None:
            self.connect()
        return self.monitor.bus

    @property
    def vcp(self) -> dict:
        return self.cfg["vcp"]

    # ---- inputs ------------------------------------------------------------
    def supported_inputs(self, refresh: bool = False) -> list[int]:
        if self.cfg.get("inputs") and not refresh:
            return self.cfg["inputs"]
        try:
            caps = ddc.capabilities(self.bus)
            inputs = sorted(caps.get(self.vcp["input"], {}).keys())
        except ddc.DDCError:
            inputs = []
        if not inputs:
            inputs = [0x0F, 0x11, 0x19, 0x1B]
        self.cfg["inputs"] = inputs
        save_config(self.cfg)
        return inputs

    def input_label(self, code: int) -> str:
        custom = self.cfg["input_labels"].get(f"0x{code:02x}")
        base = INPUT_NAMES.get(code) or \
            _("Input {code}").format(code=f"0x{code:02X}")
        return f"{custom} ({base})" if custom else base

    def detect_this_input(self) -> tuple[int | None, str]:
        """Work out which monitor input this computer is plugged into.

        The monitor doesn't say which input a DDC command arrived on, so we
        narrow the candidates down using what this machine can see:
        connector type, whether USB-C/Thunderbolt video is even possible,
        which inputs are on screen, and (in uneven splits) our resolution.
        Returns (code or None, explanation)."""
        mon = self.monitor or self.connect()
        cands = list(self.supported_inputs())
        why = []
        allowed = _connector_inputs(mon.connector)
        if allowed is not None:
            cands = [c for c in cands if c in allowed]
            why.append(_("connected via {connector}").format(
                connector=mon.connector.split('-', 1)[1]))
        if len(cands) > 1 and not _usb_c_video_possible():
            narrowed = [c for c in cands if c not in USBC_INPUTS]
            if narrowed:
                cands = narrowed
                why.append(_("no Thunderbolt/USB-C video link"))
        if len(cands) > 1:
            shown = {self.get_input()}
            layout = self.get_pxp()
            if layout != self.vcp["pxp_off"]:
                shown.add(self.get_right_input())
            narrowed = [c for c in cands if c in shown]
            if narrowed:
                cands = narrowed
                why.append(_("on screen"))
            lay = LAYOUT_BY_CODE.get(layout)
            if len(cands) > 1 and lay and lay.kind == "pbp" and lay.left != 0.5:
                width = self._current_width()
                panel = self.cfg.get("panel_width") or 5120
                if width:
                    left_w, right_w = panel * lay.left, panel * (1 - lay.left)
                    side = self.get_input() if abs(width - left_w) < \
                        abs(width - right_w) else self.get_right_input()
                    if side in cands:
                        cands = [side]
                        why.append(_("{width} px wide in {layout}").format(
                            width=width, layout=lay.title))
        if len(cands) == 1:
            return cands[0], ", ".join(why)
        names = ", ".join(self.input_label(c) for c in cands) or _("none")
        return None, _("could be any of: {inputs}").format(inputs=names)

    def _current_width(self) -> int | None:
        try:
            first = open(f"/sys/class/drm/{self.monitor.connector}/modes") \
                .readline().strip()
            return int(first.split("x")[0])
        except (OSError, ValueError):
            return None

    def get_input(self) -> int:
        return ddc.getvcp(self.bus, self.vcp["input"]).low

    def set_input(self, code: int) -> None:
        ddc.setvcp(self.bus, self.vcp["input"], code, verify=False)

    # ---- PBP ---------------------------------------------------------------
    def get_pxp(self) -> int:
        return ddc.getvcp(self.bus, self.vcp["pxp_mode"]).low

    def is_pbp(self) -> bool:
        return self.get_pxp() != self.vcp["pxp_off"]

    def set_pbp(self, on: bool) -> None:
        if on:
            code = self.cfg.get("last_layout") or self.vcp["pbp_on"]
            if code == self.vcp["pxp_off"]:
                code = self.vcp["pbp_on"]
            self.set_layout(code)
        else:
            self.set_layout(self.vcp["pxp_off"])

    # ---- layouts -----------------------------------------------------------
    def supported_layouts(self, refresh: bool = False) -> list[Layout]:
        codes = self.cfg.get("layouts")
        if not codes or refresh:
            try:
                caps = ddc.capabilities(self.bus)
                codes = sorted(caps.get(self.vcp["pxp_mode"], {}).keys())
            except ddc.DDCError:
                codes = []
            if codes:
                self.cfg["layouts"] = codes
                save_config(self.cfg)
        if not codes:
            codes = [self.vcp["pxp_off"], self.vcp["pbp_on"]]
        return [lay for lay in LAYOUTS if lay.code in codes]

    def get_layout(self) -> int:
        return self.get_pxp()

    def set_layout(self, code: int) -> None:
        ddc.setvcp(self.bus, self.vcp["pxp_mode"], code)
        if code != self.vcp["pxp_off"] and self.cfg.get("last_layout") != code:
            self.cfg["last_layout"] = code
            save_config(self.cfg)

    def next_layout(self) -> Layout:
        """Cycle through the multi-view layouts the monitor supports."""
        multi = [lay for lay in self.supported_layouts() if lay.kind != "single"]
        cur = self.get_layout()
        codes = [lay.code for lay in multi]
        nxt = multi[(codes.index(cur) + 1) % len(multi)] if cur in codes \
            else multi[0]
        self.set_layout(nxt.code)
        return nxt

    def get_right_input(self) -> int:
        return ddc.getvcp(self.bus, self.vcp["pbp_right_input"]).low

    def set_right_input(self, code: int) -> None:
        ddc.setvcp(self.bus, self.vcp["pbp_right_input"], code)

    def swap_video(self) -> None:
        ddc.setvcp(self.bus, self.vcp["swap_video"], self.vcp["swap_video_value"])

    # ---- USB / KVM -----------------------------------------------------------
    def get_usb(self) -> int:
        return ddc.getvcp(self.bus, self.vcp["usb"]).value

    def toggle_usb(self) -> None:
        ddc.setvcp(self.bus, self.vcp["usb"], self.vcp["usb_toggle_value"])

    def usb_here(self) -> bool | None:
        """True if the monitor's KVM hub is attached to this computer,
        None if we can't tell (no marker configured)."""
        markers = {m.lower() for m in self.cfg.get("kvm_marker_usb") or []}
        if not markers:
            return None
        for d in glob.glob("/sys/bus/usb/devices/*"):
            try:
                vid = open(os.path.join(d, "idVendor")).read().strip()
                pid = open(os.path.join(d, "idProduct")).read().strip()
            except OSError:
                continue
            if f"{vid}:{pid}".lower() in markers:
                return True
        return False

    def set_usb(self, here: bool, wait: float = 6.0) -> str:
        """Move the KVM to this computer (here=True) or away; no-op if it
        is already there.  Waits for USB to settle when state is known."""
        cur = self.usb_here()
        if cur is not None and cur == here:
            return (_("Keyboard and mouse are already here") if here else
                    _("Keyboard and mouse are already on the other computer"))
        self.toggle_usb()
        if cur is not None and wait:
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                time.sleep(0.25)
                if self.usb_here() == here:
                    break
        return (_("Keyboard and mouse moved here") if here else
                _("Keyboard and mouse moved to the other computer"))

    # ---- brightness, contrast, volume -------------------------------------
    def get_level(self, name: str) -> tuple[int, int]:
        """(current, maximum) of "brightness", "contrast" or "volume"."""
        v = ddc.getvcp(self.bus, self.vcp[name])
        return v.value, v.maximum or 100

    def set_level(self, name: str, value: int) -> int:
        """Set a level, clamped to the monitor's range; returns it."""
        _cur, top = self.get_level(name)
        value = max(0, min(top, int(value)))
        ddc.setvcp(self.bus, self.vcp[name], value)
        return value

    def adjust_level(self, name: str, spec: str) -> int:
        """spec is "60", "+10" or "-10"."""
        spec = spec.strip()
        if spec[:1] in "+-":
            cur, _top = self.get_level(name)
            return self.set_level(name, cur + int(spec))
        return self.set_level(name, int(spec))

    # ---- the one-button action --------------------------------------------
    def cross(self, edge: str) -> str | None:
        """The pointer was pushed against this computer's `edge` ("left" or
        "right") of the monitor.  If, in the current side-by-side layout,
        the other computer's picture is on that side, hand it the keyboard
        and mouse.  Returns a message, or None when nothing was done."""
        lay = LAYOUT_BY_CODE.get(self.get_pxp())
        if not lay or lay.kind != "pbp":
            return None
        this = self.cfg.get("this_input")
        if this is None:
            this, _why = self.detect_this_input()
        left, right = self.get_input(), self.get_right_input()
        if not ((this == right and edge == "left") or
                (this == left and edge == "right")):
            return None
        if self.usb_here() is False:
            return None
        return self.set_usb(False, wait=0)

    def switch(self) -> str:
        """In PBP: move keyboard/mouse to the other computer.
        In single view: flip the full screen between this and the other input
        (the monitor's KVM moves USB along with the video)."""
        if self.is_pbp():
            here = self.usb_here()
            if here is None:
                self.toggle_usb()
                return _("Toggled keyboard and mouse")
            return self.set_usb(not here)
        this, other = self.cfg.get("this_input"), self.cfg.get("other_input")
        if this is None or other is None:
            raise ddc.DDCError(_("Set “This Computer” and “Other Computer” "
                                 "in the app first"))
        cur = self.get_input()
        target = other if cur == this else this
        self.set_input(target)
        return _("Switched to {input}").format(input=self.input_label(target))

    def status(self) -> Status:
        st = Status()
        try:
            st.input = self.get_input()
        except ddc.DDCError as e:
            st.error = str(e)
            return st
        try:
            st.pxp_raw = self.get_pxp()
            st.pbp = st.pxp_raw != self.vcp["pxp_off"]
        except ddc.DDCError:
            pass
        if st.pbp:
            try:
                st.right_input = self.get_right_input()
            except ddc.DDCError:
                pass
        try:
            st.usb_raw = self.get_usb()
        except ddc.DDCError:
            pass
        st.usb_here = self.usb_here()
        st.levels = {}
        for name in LEVELS:
            try:
                st.levels[name] = self.get_level(name)
            except ddc.DDCError:
                pass
        return st
