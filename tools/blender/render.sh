#!/usr/bin/env bash
# Render STEAMWARD's voxel sprite atlases into assets/.
#
# Needs a Python with the `bpy` (headless Blender) and `pillow` modules:
#   python3.11 -m venv .bpyenv && .bpyenv/bin/pip install bpy pillow
# Point BPY_PYTHON at that interpreter, or install a `blender` on PATH.
#
#   tools/blender/render.sh          # units + props
#   tools/blender/render.sh units    # only the troop sheets
set -euo pipefail
cd "$(dirname "$0")/../.."

WHAT="${1:-all}"

if [ -n "${BPY_PYTHON:-}" ]; then
  exec "$BPY_PYTHON" tools/blender/build.py "$WHAT"
elif [ -x .bpyenv/bin/python ]; then
  exec .bpyenv/bin/python tools/blender/build.py "$WHAT"
elif command -v blender >/dev/null 2>&1; then
  exec blender --background --python tools/blender/build.py -- "$WHAT"
else
  echo "No Blender found. Set BPY_PYTHON to a python with 'bpy' installed," >&2
  echo "or create one with: python3.11 -m venv .bpyenv && .bpyenv/bin/pip install bpy pillow" >&2
  exit 1
fi
