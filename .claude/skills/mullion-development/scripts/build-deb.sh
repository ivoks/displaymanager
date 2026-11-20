#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the Debian package from a clean copy of the repository's tracked and
# new (not ignored) files, then run lintian with warnings as errors.
#
#   build-deb.sh <repo> [outdir]      prints the path of the .deb
#
# Never build in the repository itself: dpkg-buildpackage leaves
# debian/mullion/, debian/files etc. behind.
set -e
repo=$(cd "${1:?usage: build-deb.sh <repo> [outdir]}" && pwd)
out=${2:-$(mktemp -d /tmp/mullion-deb-XXXXXX)}
rm -rf "$out/mullion" && mkdir -p "$out/mullion"
(cd "$repo" && git ls-files -co --exclude-standard -z | xargs -0 cp --parents -t "$out/mullion/")
(cd "$out/mullion" && dpkg-buildpackage -us -uc -b > "$out/build.log" 2>&1) || {
    tail -30 "$out/build.log"; echo "build failed, full log: $out/build.log" >&2; exit 1; }
deb=$(ls "$out"/mullion_*_all.deb)
lintian --fail-on error,warning --info "$deb"
echo "$deb"
