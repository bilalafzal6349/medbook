#!/usr/bin/env bash
# Rebuild full model weight files from their .partN pieces and verify the checksum.
# Optional: models/predict_xlmr.py and the backend already read the fp16 parts directly.
# Usage: scripts/reassemble_weights.sh [model_dir ...]   (default: every results/*/model)
set -euo pipefail
cd "$(dirname "$0")/.."
dirs=("$@"); [ ${#dirs[@]} -eq 0 ] && dirs=(results/*/model)
for d in "${dirs[@]}"; do
  ( cd "$d"
    for first in *.part0; do
      [ -e "$first" ] || continue
      base="${first%.part0}"
      cat $(ls -v "$base".part*) > "$base"
      [ -f "$base.sha256" ] && sha256sum -c "$base.sha256"
      echo "rebuilt $d/$base"
    done )
done
