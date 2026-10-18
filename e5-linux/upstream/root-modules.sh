#!/bin/sh
# Package all matching modules, indexes and the aliases used by board services.
# E5_UPSTREAM_OUT: another build's output (default upstream/out; the package's is upstream/out-release)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${E5_UPSTREAM_OUT:-$HERE/out}
exec python3 "$HERE/stage-root-modules.py" "$OUT"
