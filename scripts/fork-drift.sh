#!/bin/bash
# Compare the Dark-R copies of Omarchy widgets with the installed Omarchy.
#
#   scripts/fork-drift.sh          summary: lines that differ per file
#   scripts/fork-drift.sh --diff   the full diffs
#
# Each copy says which Omarchy release it is based on ("basedOn" in its
# manifest) and marks its own changes with "Dark-R". After an Omarchy update,
# take the new upstream file and apply the marked blocks again. Files listed
# as verbatim must match upstream exactly; the script exits 1 when one does not.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
OMARCHY_PATH=${OMARCHY_PATH:-/usr/share/omarchy}
UPSTREAM="$OMARCHY_PATH/shell/plugins"
SHOW_DIFF=0
[[ ${1:-} == "--diff" ]] && SHOW_DIFF=1

if [[ ! -d $UPSTREAM ]]; then
  echo "Omarchy shell plugins not found in $UPSTREAM" >&2
  exit 2
fi

# copy path, upstream path, kind (changed or verbatim)
FILES=(
  "dark-r.menu/BarWidget.qml|menu/BarWidget.qml|changed"
  "dark-r.workspaces/Workspaces.qml|bar/widgets/Workspaces.qml|changed"
  "dark-r.indicators/Indicators.qml|bar/widgets/Indicators.qml|changed"
  "dark-r.clock/BarWidget.qml|panels/clock/BarWidget.qml|changed"
  "dark-r.clock/Model.js|panels/clock/Model.js|verbatim"
  "dark-r.clock/WallClock.qml|panels/clock/WallClock.qml|verbatim"
)

installed=$(omarchy version 2>/dev/null || echo unknown)
echo "Installed Omarchy: $installed"
status=0

for entry in "${FILES[@]}"; do
  IFS='|' read -r copy upstream kind <<<"$entry"
  plugin=${copy%%/*}
  based=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("omarchy", {}).get("basedOn", "?"))' "$ROOT/plugins/$plugin/manifest.json")
  if [[ ! -f $UPSTREAM/$upstream ]]; then
    printf '%-36s upstream %s is gone\n' "$copy" "$upstream"
    status=1
    continue
  fi
  lines=$(diff "$UPSTREAM/$upstream" "$ROOT/plugins/$copy" | grep -c '^[<>]' || true)
  if [[ $kind == "verbatim" && $lines -gt 0 ]]; then
    printf '%-36s based on %-8s differs from upstream by %s lines (must match)\n' "$copy" "$based" "$lines"
    status=1
  else
    printf '%-36s based on %-8s %s lines differ\n' "$copy" "$based" "$lines"
  fi
  if (( SHOW_DIFF )); then
    diff -u --label "omarchy/$upstream" --label "dark-r/$copy" "$UPSTREAM/$upstream" "$ROOT/plugins/$copy" || true
  fi
done

exit $status
