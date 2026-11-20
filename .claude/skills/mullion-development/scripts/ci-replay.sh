#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Run the steps of .github/workflows/ci.yml in a fresh ubuntu:26.04 container,
# like GitHub Actions does, then remove the container's root-owned files.
#
#   ci-replay.sh <repo>        log: <repo>/build/ci.log
#
# Works in <repo>/build/ci because the docker daemon can't see /tmp/claude-*.
set -e
repo=$(cd "${1:?usage: ci-replay.sh <repo>}" && pwd)
ci="$repo/build/ci"
log="$repo/build/ci.log"
rm -rf "$ci" && mkdir -p "$ci/mullion"
(cd "$repo" && git ls-files -co --exclude-standard -z | grep -zv '^build/' |
    xargs -0 cp --parents -t "$ci/mullion/")
python3 - "$repo/.github/workflows/ci.yml" "$ci/run.sh" <<'PY'
import sys, yaml
wf = yaml.safe_load(open(sys.argv[1]))
lines = ["set -ex", "export DEBIAN_FRONTEND=noninteractive", "cd /work"]
for step in next(iter(wf["jobs"].values()))["steps"]:
    if "run" not in step:
        continue
    wd = step.get("working-directory")
    lines.append(f"echo '=== {step['name']}'")
    lines.append(f"(cd {wd} && {{\n{step['run']}\n}})" if wd else f"(\n{step['run']}\n)")
open(sys.argv[2], "w").write("\n".join(lines) + "\n")
PY
status=0
docker run --rm -v "$ci:/work" ubuntu:26.04 bash /work/run.sh > "$log" 2>&1 || status=$?
grep -E "^=== |^Ran [0-9]+|^OK$|FAILED|checks passed|building package" "$log" | grep -v '^+ ' || true
docker run --rm -v "$ci:/work" ubuntu:26.04 sh -c 'rm -rf /work/* /work/.[!.]*'
rm -rf "$ci"
if [ $status -ne 0 ]; then echo "CI replay FAILED (exit $status), see $log" >&2; exit $status; fi
echo "CI replay passed (log: $log)"
