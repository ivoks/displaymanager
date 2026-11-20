# DisplayManager for GNOME

A small GTK4/libadwaita app (plus CLI) that does what Dell Display and
Peripheral Manager does on macOS for a Dell U4025QW: switch inputs, toggle
Picture-by-Picture, swap sides and hand the monitor's USB hub (keyboard and
mouse) to the other computer.

It talks to the monitor over **DDC/CI** (VESA MCCS) using `ddcutil`.

## Install

```sh
sudo apt install ddcutil python3-gi gir1.2-adw-1 gettext make
sudo usermod -aG i2c $USER        # then log out and back in
./install.sh                      # ~/.local/bin + app grid entry
```

## Use

Launch **DisplayManager** from the app grid, or use the CLI:

```
displaymanager status
displaymanager detect          # which input is this computer plugged into
displaymanager switch          # PBP: move KVM; single view: flip input
displaymanager layout list|next|<name>   # see layouts below
displaymanager pbp on|off|toggle    # last used layout / single
displaymanager swap            # swap left/right in PBP
displaymanager input 0x19      # full-screen / left input
displaymanager right 0x0f      # PBP right-side input
displaymanager usb here|away|toggle   # keyboard & mouse (KVM)
```

The app can install system-wide GNOME shortcuts that call these commands
(all off by default; change the keys in Settings → Keyboard → Custom
Shortcuts):

| Keys | Action |
|------|--------|
| Super+Ctrl+K | Switch computer |
| Super+Ctrl+U | Move keyboard & mouse |
| Super+Ctrl+P | Toggle side-by-side |
| Super+Ctrl+S | Swap left/right |
| Super+Ctrl+L | Next layout |
| Super+Alt+1 … 7, 9 | Single, Even Split, Wide Left, Wider Left, Wide Right, Wider Right, Small Inset, Large Inset |

The layout keys work on both the number row and the number pad (the app
installs a second GNOME shortcut for the number pad). Super+Ctrl+digit is
taken by GNOME Shell and Super+Alt+8 by the magnifier, so Large Inset uses
Super+Alt+9. The app refuses to enable a shortcut whose keys are already
used elsewhere in GNOME.

## Layouts

| Name | Layout | Left : Right | `E9` |
|------|--------|--------------|------|
| `single` | Single input, full screen | — | `00` |
| `50-50` | Even Split | 50 : 50 | `24` |
| `75-25` | Wide Left | 75 : 25 | `2A` |
| `80-20` | Wider Left | 80 : 20 | `28` |
| `25-75` | Wide Right | 25 : 75 | `29` |
| `20-80` | Wider Right | 20 : 80 | `27` |
| `pip-small` | Small inset (picture in picture) | — | `21` |
| `pip-large` | Large inset (picture in picture) | — | `22` |

The left side (or the full picture) is the input selected with `60`; the
right side (or the inset) is the second input, `E8`. The splits were
measured from the resolution the monitor gives the right-hand source
(1280, 1024, 3840, 4096 of 5120 pixels). Only layouts the monitor lists in
its capabilities are shown.

## VCP codes on the U4025QW

| Code | Meaning | Values | Verified |
|------|---------|--------|----------|
| `60` | Input (left side in PBP) | `0F` DP, `11` HDMI, `19` Thunderbolt | yes |
| `E9` | Layout (PxP mode) | see Layouts | yes |
| `E8` | PBP right-side input | same codes as `60` | read yes |
| `E5` | Swap PBP video | write `F001` | yes |
| `E7` | USB upstream (KVM) | write `FF00` = toggle; read-back does not change | yes |

All codes live in `~/.config/displaymanager/config.json` under `"vcp"`,
so they can be adjusted without touching code. The *Advanced → Raw VCP
Access* panel reads/writes any feature for experimenting.

## How KVM state is detected

The monitor doesn't report which computer owns the USB hub over DDC, so the
app looks at USB instead: the U4025QW's switched sub-hubs carry Realtek HID
functions (`0bda:1100`, `0bda:1101`). If they're present, the keyboard and
mouse are on this computer. Change `kvm_marker_usb` in the config for other
models.

## KVM requirements

The monitor can only give Ubuntu the keyboard and mouse if Ubuntu is
connected to its **USB-C upstream** port (not the Thunderbolt
downstream/daisy-chain port: that one only links you to the Mac's
Thunderbolt domain) and the keyboard/mouse are plugged into the monitor's
downstream ports. Assign the upstream to the matching video input in the
monitor's OSD (USB settings / PBP USB switch).

## Translations

Translations use GNU gettext. The template is `po/displaymanager.pot`, each
language is `po/<lang>.po`, and `po/LINGUAS` lists the languages that are
built. `make` compiles them into `build/locale` (used when running from the
source folder) and merges the desktop file's translations; `make install`
puts them in `<prefix>/share/locale`.

Add a language:

```sh
msginit -i po/displaymanager.pot -l de_DE.UTF-8 -o po/de.po
echo de >> po/LINGUAS
# translate po/de.po, keeping {placeholders} unchanged
make && LANGUAGE=de ./displaymanager
```

After changing strings in the code, `make update-po` regenerates the
template and merges it into every `po/*.po`. `msgfmt --check` (run by
`make`) verifies that placeholders match.

Available: Croatian (`hr`).

## License

GPL-3.0-or-later. See [LICENSE](LICENSE). The application icons in
`data/icons/` are original artwork under the same license; no Dell
trademarks or artwork are used. "Dell" is mentioned only to name the
hardware this works with.
