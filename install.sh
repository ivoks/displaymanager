#!/bin/sh
# Per-user install: symlinks the launcher into ~/.local/bin and adds a menu entry.
set -e
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" \
         "$HOME/.local/share/icons/hicolor/scalable/apps" \
         "$HOME/.local/share/icons/hicolor/symbolic/apps"
cp "$here/data/icons/io.github.DisplayManager.svg" \
   "$HOME/.local/share/icons/hicolor/scalable/apps/"
cp "$here/data/icons/io.github.DisplayManager-symbolic.svg" \
   "$HOME/.local/share/icons/hicolor/symbolic/apps/"
ln -sf "$here/displaymanager" "$HOME/.local/bin/displaymanager"
sed "s|^Exec=.*|Exec=$HOME/.local/bin/displaymanager|" \
    "$here/data/io.github.DisplayManager.desktop" \
    > "$HOME/.local/share/applications/io.github.DisplayManager.desktop"
command -v ddcutil >/dev/null || echo "Install ddcutil:  sudo apt install ddcutil"
if ! id -nG | grep -qw i2c; then
    echo "Grant I2C access (then log out and back in):"
    echo "  sudo usermod -aG i2c $USER"
fi
echo "Installed. Launch 'DisplayManager' from the app grid."
