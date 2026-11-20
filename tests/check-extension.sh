#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Run the GNOME Shell extension's modules under gjs with the Shell-only
# imports replaced by tests/extension/stubs.js, and check the screen-edge
# switching behaviour (tests/extension/check.js).
set -e
here=$(cd "$(dirname "$0")" && pwd)
ext=${1:-$here/../extension/mullion@ivoks.github.io}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$ext/metadata.json"

for f in "$ext"/*.js; do
    sed -E \
        -e "s#^import ([A-Za-z]+) from 'gi://(Meta|Shell|St|Clutter)';#import {\1} from './stubs.js';#" \
        -e "s#^import \* as ([A-Za-z]+) from 'resource://[^']*';#import {\1} from './stubs.js';#" \
        -e "s#^import \{Extension\} from 'resource://[^']*';#import {Extension} from './stubs.js';#" \
        -e "s#^import \{gettext as _\} from 'resource://[^']*';#import {_} from './stubs.js';#" \
        -e "s#^export default class#export class#" \
        "$f" > "$tmp/$(basename "$f")"
done
cp "$here/extension/stubs.js" "$here/extension/check.js" "$tmp/"

# A fake "mullion" that records how the extension called it.
mkdir "$tmp/bin" "$tmp/config"
cat > "$tmp/bin/mullion" <<FAKE
#!/bin/sh
echo "\$*" > "$tmp/config/calls.txt"
case "\$*" in
*--check) [ "\$FAKE_CHECK" = no ] && exit 1; echo "\$FAKE_CHECK" ;;
esac
FAKE
chmod +x "$tmp/bin/mullion"

PATH="$tmp/bin:$PATH" CHECK_DIR="$tmp/config" gjs -m "$tmp/check.js"
