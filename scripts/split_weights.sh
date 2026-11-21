#!/usr/bin/env bash
# Split a model weight file into <100 MB parts so it can be pushed to GitHub.
# Usage: scripts/split_weights.sh results/xlmr_v2/model/joint_xlmr.pt
#   -> joint_xlmr.pt.part0, part1, ... and joint_xlmr.pt.sha256 next to it
set -euo pipefail
cd "$(dirname "$1")"; f="$(basename "$1")"
rm -f "$f".part*
split -b 95000000 -d -a 1 "$f" "$f.part"
sha256sum "$f" > "$f.sha256"
ls -la "$f".part*
echo "Commit the .part files and $f.sha256 (the full file is gitignored)."
