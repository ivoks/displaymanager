# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""High level operations shared by the GUI and the command line."""

from __future__ import annotations

import glob
import json
import os
import time
from dataclasses import dataclass

from . import ddc

_XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
CONFIG_DIR = os.path.join(_XDG_CONFIG, "displaymanager")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LEGACY_CONFIG_DIR = os.path.join(_XDG_CONFIG, "dell-display-manager")


def _migrate_legacy_config() -> None:
    """Carry settings over from the pre-rename config directory."""
    if not os.path.exists(CONFIG_DIR) and os.path.isdir(LEGACY_CONFIG_DIR):
        try:
            os.rename(LEGACY_CONFIG_DIR, CONFIG_DIR)
        except OSError:
            pass

# MCCS standard input codes (VCP 0x60) plus the values Dell uses.
INPUT_NAMES = {
    0x01: "VGA", 0x03: "DVI-1", 0x04: "DVI-2",
    0x0F: "DisplayPort-1", 0x10: "DisplayPort-2",
    0x11: "HDMI-1", 0x12: "HDMI-2",
    0x19: "Thunderbolt", 0x1B: "USB-C", 0x1C: "USB-C 2",
}

DEFAULTS = {
    "monitor_serial": None,     # pick this monitor if several are attached
    "bus": None,                # cached bus once probed
    "this_input": None,         # VCP 60 value this computer is plugged into
    "other_input": None,        # VCP 60 value of the other computer (Mac)
    "input_labels": {},         # {"0x1b": "MacBook"}
    "inputs": None,             # cached list of supported input codes
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
    },
}


def load_config() -> dict:
    _migrate_legacy_config()
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
            raise ddc.DDCError("No monitor found on any display connector")
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
        base = INPUT_NAMES.get(code, f"Input 0x{code:02X}")
        return f"{custom} ({base})" if custom else base

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
        ddc.setvcp(self.bus, self.vcp["pxp_mode"],
                   self.vcp["pbp_on"] if on else self.vcp["pxp_off"])

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
            return ("Keyboard and mouse are already "
                    + ("here" if here else "on the other computer"))
        self.toggle_usb()
        if cur is not None and wait:
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                time.sleep(0.25)
                if self.usb_here() == here:
                    break
        return ("Keyboard and mouse moved "
                + ("here" if here else "to the other computer"))

    # ---- the one-button action --------------------------------------------
    def switch(self) -> str:
        """In PBP: move keyboard/mouse to the other computer.
        In single view: flip the full screen between this and the other input
        (the monitor's KVM moves USB along with the video)."""
        if self.is_pbp():
            here = self.usb_here()
            if here is None:
                self.toggle_usb()
                return "Toggled keyboard and mouse"
            return self.set_usb(not here)
        this, other = self.cfg.get("this_input"), self.cfg.get("other_input")
        if this is None or other is None:
            raise ddc.DDCError("Set 'This computer' and 'Other computer' "
                               "inputs in the app first")
        cur = self.get_input()
        target = other if cur == this else this
        self.set_input(target)
        return f"Switched to {self.input_label(target)}"

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
        return st
