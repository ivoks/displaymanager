#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Load the GNOME Shell extension's modules with gjs, replacing the imports
# that only exist inside GNOME Shell with stubs. Catches syntax errors and
# mistakes at module load time; behaviour is tested inside GNOME Shell.
set -e
ext=${1:-extension/displaymanager@ivoks.github.io}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$ext/metadata.json"

stub() {
    sed -E \
        -e "s|^import ([A-Za-z]+) from 'gi://(Meta\|Shell\|St\|Clutter)';|const \1 = {};|" \
        -e "s|^import \* as ([A-Za-z]+) from 'resource://[^']*';|const \1 = {};|" \
        -e "s|^import \{Extension\} from 'resource://[^']*';|class Extension {}|" \
        -e "s|^import \{gettext as _\} from 'resource://[^']*';|const _ = s => s;|" \
        -e "s|^export default class|export class|" \
        "$1" > "$2"
}
for f in "$ext"/*.js; do
    stub "$f" "$tmp/$(basename "$f")"
done

cat > "$tmp/check.js" <<'JS'
import Gio from 'gi://Gio';
import {EdgeSwitchExtension} from './extension.js';
import {createIndicator, displaymanagerPath} from './quickmenu.js';
new EdgeSwitchExtension();
if (typeof createIndicator !== 'function' || !displaymanagerPath())
    throw new Error('quickmenu.js exports missing');
print('extension modules load OK');
JS
gjs -m "$tmp/check.js"
