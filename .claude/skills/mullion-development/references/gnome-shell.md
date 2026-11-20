# The GNOME Shell extension

`extension/mullion@ivoks.github.io/` does what an application can't on
Wayland: see the pointer (edge barriers + pop-up), draw GNOME's OSD, and add
a Quick Settings tile. It reads `~/.config/mullion/config.json` (watching the
directory, since the app replaces the file atomically) and runs `mullion`.

## Check APIs against the real GNOME Shell

Targets are GNOME 48–50; the user runs 50. Don't trust memory for Shell
internals — they change between releases. The Shell's own JavaScript is in
a GResource on this machine:

```sh
L=$(ls /usr/lib/gnome-shell/libshell-*.so | head -1)
gresource list $L | grep ui/layout.js
gresource extract $L /org/gnome/shell/ui/layout.js > /tmp/layout.js
```

Useful files: `ui/layout.js` (PressureBarrier, Meta.Barrier usage, chrome),
`ui/quickSettings.js`, `ui/popupMenu.js`, `ui/osdWindow.js`,
`ui/shellDBus.js`, `extensions/sharedInternals.js` (gettext setup). For
Mutter/Clutter enums, introspect the typelibs:
`GI_TYPELIB_PATH=/usr/lib/x86_64-linux-gnu/mutter-18 python3 -c "import gi; gi.require_version('Meta','18'); …"`.

Facts already established for GNOME 50:
- `new Meta.Barrier({backend: global.backend, x1, x2, y1, y2, directions})`,
  `new Layout.PressureBarrier(threshold, timeoutMs, Shell.ActionMode.NORMAL)`
  with `addBarrier()` and a `'trigger'` signal (hot corner: 100 px / 1 s).
- `global.backend.get_monitor_manager().get_monitor_for_connector('DP-1')`
  → monitor index; `global.display.get_monitor_neighbor_index()` tells
  outer edges; `Main.layoutManager.panelBox.height`, `.primaryIndex`.
- `global.get_pointer()` → `[x, y, mods]`; `Clutter.ModifierType.BUTTON1_MASK…`.
- Input hotplug: `global.stage.context.get_backend().get_default_seat()`
  `'device-added'`.
- `Main.osdWindowManager.showOne(index, gicon, label, level, maxLevel)`;
  level `null` hides the bar. `org.gnome.Shell.ShowOSD` itself rejects
  non-GNOME callers, hence our own `io.github.ivoks.Mullion.ShowOSD` at
  `/io/github/ivoks/Mullion` on the Shell's connection.
- Quick Settings: `QuickMenuToggle`, `SystemIndicator.quickSettingsItems`,
  `Main.panel.statusArea.quickSettings.addExternalIndicator()`,
  `menu.setHeader()`, `PopupMenu.Ornament.CHECK/NO_DOT`.
- Overlays: `Main.layoutManager.addTopChrome(actor)` / `removeChrome()`.
- `stylesheet.css` in the extension directory is loaded automatically;
  `metadata.json` `"gettext-domain": "mullion"` shares the app's
  translations (only from `/usr/share/locale`, so source installs show
  English in the extension).

## Rules for the code

- **Nothing Shell-specific at module load.** No `GObject.registerClass`
  of Shell classes and no `Clutter.*` lookups at top level — register
  classes lazily (see `quickmenu.js`) and read enums inside functions.
  This keeps re-enabling safe and lets `tests/check-extension.sh` load the
  modules under plain gjs with `tests/extension/stubs.js`.
- Undo everything in `disable()` (barriers, signal handlers, D-Bus export,
  chrome actors, timeouts).
- Put decisions that need the monitor in the CLI (`mullion cross --check`,
  `mullion state`) so they're unit-tested in Python; keep the extension to
  pointer/UI plumbing.
- Log user-visible decisions with `console.log('Mullion: …')` — that's how
  the user can answer "why did it switch?" later.
- Keep defaults that the extension and app share equal (the config stores
  only non-defaults); test it in `tests/test_release.py`.

## Testing

- `sh tests/check-extension.sh` (part of `make check` and CI): loads all
  modules with stubs, then runs `tests/extension/check.js`, which drives
  the real logic with a fake `mullion` on `PATH` that records its
  arguments (`FAKE_CHECK=name|no` controls `cross --check`). Extend the
  stubs when you use new Shell APIs, and add a check for each behaviour.
- The live Shell only loads new extension code at login, and you can't see
  it from SSH. Tell the user to install the .deb, log out and in, and how
  to check: `gnome-extensions info mullion@ivoks.github.io`,
  `journalctl --user -b | grep -i mullion`.
- Enable/disable over D-Bus (`mullion/extension.py`); `GetExtensionInfo`
  returns `{}` for an extension the Shell hasn't discovered yet (installed
  after login).
