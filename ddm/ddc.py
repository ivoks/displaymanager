# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""Thin, synchronous wrapper around the `ddcutil` command line tool.

DDC/CI (VESA MCCS) is the standard protocol monitors speak over the I2C
lines of the video cable.  Standard VCP feature 0x60 selects the input;
Dell exposes PBP and KVM through manufacturer-specific codes (0xE0-0xFF).
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field

from .i18n import _

DDCUTIL = shutil.which("ddcutil") or "/usr/bin/ddcutil"

# A single lock: the monitor's DDC/CI interface cannot handle concurrent
# transactions, even from separate processes, so we serialise ours.
_lock = threading.Lock()


class DDCError(RuntimeError):
    pass


class DDCAccessError(DDCError):
    """The monitor's I2C device exists but we may not open it."""


@dataclass
class Monitor:
    connector: str          # e.g. "card1-DP-1"
    model: str              # e.g. "DELL U4025QW"
    serial: str
    buses: list[int] = field(default_factory=list)  # candidate /dev/i2c-N
    bus: int | None = None  # bus confirmed to answer DDC/CI

    @property
    def label(self) -> str:
        return f"{self.model} ({self.connector.split('-', 1)[-1]})"


@dataclass
class VCPValue:
    code: int
    raw: list[int]          # bytes as reported: [mh, ml, sh, sl] or [cur] ...

    @property
    def value(self) -> int:
        """Current value (SH<<8 | SL for non-continuous features)."""
        if len(self.raw) == 4:
            return (self.raw[2] << 8) | self.raw[3]
        return self.raw[0]

    @property
    def low(self) -> int:
        return self.value & 0xFF


# --------------------------------------------------------------------------
# Discovery via sysfs: fast (no I2C traffic), gives us bus candidates.
# --------------------------------------------------------------------------

def _edid_descriptors(edid: bytes) -> dict[int, str]:
    out = {}
    for off in range(54, 126, 18):
        blk = edid[off:off + 18]
        if len(blk) == 18 and blk[:3] == b"\0\0\0" and blk[3] in (0xFC, 0xFF):
            out[blk[3]] = blk[5:].split(b"\n")[0].decode("ascii", "ignore").strip()
    return out


def find_monitors() -> list[Monitor]:
    mons = []
    for conn in sorted(glob.glob("/sys/class/drm/card*-*")):
        try:
            if open(os.path.join(conn, "status")).read().strip() != "connected":
                continue
            edid = open(os.path.join(conn, "edid"), "rb").read()
        except OSError:
            continue
        if len(edid) < 128:
            continue
        desc = _edid_descriptors(edid)
        buses = []
        # DP AUX channel bus first (what ddcutil prefers for DP), then the
        # connector's dedicated DDC adapter (HDMI / some DP implementations).
        for d in glob.glob(os.path.join(conn, "i2c-*")):
            buses.append(int(d.rsplit("-", 1)[1]))
        ddc = os.path.join(conn, "ddc")
        if os.path.exists(ddc):
            buses.append(int(os.path.realpath(ddc).rsplit("-", 1)[1]))
        mons.append(Monitor(os.path.basename(conn), desc.get(0xFC, "Unknown"),
                            desc.get(0xFF, ""), buses))
    return mons


def bus_accessible(bus: int) -> bool:
    return os.access(f"/dev/i2c-{bus}", os.R_OK | os.W_OK)


# --------------------------------------------------------------------------
# ddcutil invocation
# --------------------------------------------------------------------------

def _run(args: list[str], timeout: float = 15) -> str:
    if not os.path.exists(DDCUTIL):
        raise DDCError(_("ddcutil is not installed (sudo apt install ddcutil)"))
    with _lock:
        try:
            p = subprocess.run([DDCUTIL, *args], capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise DDCError(f"ddcutil {' '.join(args)} timed out")
    if p.returncode != 0:
        msg = (p.stdout + p.stderr).strip().splitlines()
        raise DDCError(msg[-1] if msg else f"ddcutil exited {p.returncode}")
    return p.stdout


_TERSE = re.compile(r"^VCP\s+([0-9A-Fa-f]{2})\s+(\S+)\s*(.*)$", re.M)


def getvcp(bus: int, code: int) -> VCPValue:
    out = _run(["--bus", str(bus), "--terse", "getvcp", f"{code:02x}"])
    m = _TERSE.search(out)
    if not m:
        raise DDCError(f"Unexpected ddcutil output: {out.strip()}")
    kind, rest = m.group(2), m.group(3).split()
    if kind in ("ERR", "UNSUPPORTED", "INVALID"):
        raise DDCError(_("Feature {code} is not supported by the monitor")
                       .format(code=f"{code:02X}"))
    nums = [int(t.lstrip("x"), 16) if t.startswith("x") else int(t)
            for t in rest if re.fullmatch(r"x?[0-9A-Fa-f]+", t)]
    if kind == "C" and nums:          # continuous: current max
        return VCPValue(code, [nums[0]])
    if not nums:
        raise DDCError(f"Could not parse: {out.strip()}")
    return VCPValue(code, nums)


def setvcp(bus: int, code: int, value: int, verify: bool = False) -> None:
    """Write a feature.  Dell's vendor codes frequently answer with a DDC
    NULL response even though the command took effect, so by default we
    don't verify and we tolerate that particular error."""
    args = ["--bus", str(bus)]
    if not verify:
        args.append("--noverify")
    args += ["setvcp", f"{code:02x}", f"0x{value:x}"]
    try:
        _run(args)
    except DDCError as e:
        if "NULL_RESPONSE" in str(e) or "null response" in str(e).lower():
            return
        raise


def capabilities(bus: int) -> dict[int, dict[int, str]]:
    """Return {feature_code: {value: name}} parsed from `ddcutil capabilities`."""
    out = _run(["--bus", str(bus), "capabilities"], timeout=30)
    feats: dict[int, dict[int, str]] = {}
    cur = None
    in_values = False
    for line in out.splitlines():
        m = re.match(r"\s*Feature:\s*([0-9A-Fa-f]{2})\b", line)
        if m:
            cur = int(m.group(1), 16)
            feats[cur] = {}
            in_values = False
            continue
        if cur is None:
            continue
        if re.match(r"\s*Values:", line):
            in_values = True
            # values may be inline: "Values: 0f 11 1b (interpretation unavailable)"
            inline = line.split(":", 1)[1].split("(")[0].split()
            for t in inline:
                if re.fullmatch(r"[0-9A-Fa-f]{2}", t):
                    feats[cur][int(t, 16)] = ""
            continue
        if in_values:
            m = re.match(r"\s*([0-9A-Fa-f]{2}):\s*(.*)$", line)
            if m:
                feats[cur][int(m.group(1), 16)] = m.group(2).strip()
            else:
                in_values = False
    return feats


def probe_bus(mon: Monitor) -> int:
    """Find which candidate bus answers DDC/CI for this monitor."""
    errors = []
    denied = 0
    for bus in mon.buses:
        if not bus_accessible(bus):
            errors.append(f"/dev/i2c-{bus}: " + _("permission denied"))
            denied += 1
            continue
        try:
            getvcp(bus, 0x60)
            mon.bus = bus
            return bus
        except DDCError as e:
            errors.append(f"/dev/i2c-{bus}: {e}")
    if denied and denied == len(mon.buses):
        raise DDCAccessError("; ".join(errors))
    raise DDCError("; ".join(errors) or _("no I2C bus for this connector"))
