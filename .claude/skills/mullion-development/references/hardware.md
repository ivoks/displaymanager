# Dell U4025QW over DDC/CI — what is known

Everything here was verified on the user's monitor unless marked otherwise.

## Talking to it

- DDC/CI runs over the DP AUX channel of the connector: `/sys/class/drm/card1-DP-1`
  → `/dev/i2c-13` (the connector's `ddc` link, `/dev/i2c-4`, is a fallback).
  `ddc.find_monitors()` finds this from sysfs/EDID without I2C traffic.
- Access: ddcutil's udev rule gives the local desktop user an ACL; over SSH
  the user needs the `i2c` group (`DDCAccessError` → GUI banner).
- The monitor answers for almost every code (245 of 256), including ones it
  doesn't advertise — "readable" doesn't mean "meaningful".
- Dell's vendor codes often reply with a DDC NULL response to writes even
  though they worked, so `setvcp` always uses `--noverify` and tolerates it.

## Verified codes (config keys under `"vcp"` in parentheses)

| Code | Meaning | Notes |
|---|---|---|
| `60` (`input`) | main input (left, or full screen) | `0F` DisplayPort, `11` HDMI, `19` Thunderbolt |
| `E8` (`second_input`) | second input (right side or inset) | same codes; reads e.g. `xff xff x00 x0f` |
| `E9` (`layout`) | layout | `00` single, `24` 50:50, `2A` 75:25, `28` 80:20, `29` 25:75, `27` 20:80, `21` small inset, `22` large inset; `01`/`02` are not layouts |
| `E5` (`swap`) | swap the two inputs | write `F001`; **any** `F0xx` value swaps |
| `E7` (`usb`) | move the USB hub (KVM) | write `FF00` toggles; **read-back never reflects the state** |
| `10` / `12` / `62` | brightness / contrast / volume | continuous, max 100 |

Layout splits were measured, not documented: with this computer on the
right, the resolution it receives tells the right side's width (panel 5120
px: 1280, 1024, 3840, 4096). That trick (`/sys/class/drm/card1-DP-1/modes`,
first line) is also how `detect_this_input()` tells sides apart in uneven
splits.

## Things that don't work

- **PIP/PBP → Audio → Main/Sub can't be read or set over DDC.** Two full
  256-code snapshots before/after changing it in the OSD were identical,
  and `E5 F0xx` writes only swap. Don't promise "audio follows keyboard".
- **E7 can't tell you where the KVM is.** Mullion infers it from USB: the
  switched sub-hubs carry Realtek HID functions `0bda:1100` / `0bda:1101`
  (`kvm_marker_usb`). Present on this machine ⇒ keyboard and mouse here.
- The monitor doesn't say which input a DDC command arrived on;
  `detect_this_input()` narrows it down (connector type, Thunderbolt/USB-C
  presence, inputs on screen, resolution) and says "can't tell" otherwise.

## Cabling (the KVM only works if this is right)

- This computer must reach the monitor's **USB-C upstream** port. The
  Thunderbolt *downstream* (daisy-chain) port instead links the computer
  into the Mac's Thunderbolt domain (kernel log: `thunderbolt … new host
  found … Apple Inc.`) and the monitor's hub never appears.
- With the hub attached, `lsusb -t` shows Realtek hubs `0bda:5483`/`0483`
  with the keyboard/mouse on sub-hub `3-1.1` and the webcam/YubiKey on
  `3-1.2`. On each arrival the hub briefly attaches, detaches and attaches
  again (~3 s) — harmless, not caused by Ubuntu.
- `journalctl -k | grep "usb 3-1.1"` gives exact times the KVM left/arrived;
  `journalctl --user -b | grep 'Mullion:'` shows the extension's edge events.

## Discovering an undocumented setting

When the user wants something only the monitor's OSD can do:

1. Snapshot every code: `for i in $(seq 0 255); do c=$(printf %02X $i);
   echo "$c $(ddcutil --bus 13 getvcp 0x$c --terse 2>/dev/null | grep ^VCP)"; done > before.txt`
   (~70 s; the advertised list from `ddcutil --bus 13 capabilities` is a
   quicker first pass).
2. Ask the user to change the setting in the OSD and say "done".
3. Snapshot again and `diff`. Ask them to change it back and repeat — two
   diffs in opposite directions rule out noise.
4. No diff ⇒ the setting may still be writable (like E7). Only then try
   writes, with the user's consent, a short list of candidates, one at a
   time ~10 s apart, a desktop notification announcing each, and
   automatic undo of side effects (e.g. swap back if the inputs flipped).
   For audio, play a tone to the monitor's sink:
   `pw-play --target alsa_output.pci-0000_c6_00.1.hdmi-stereo tone.wav`.
