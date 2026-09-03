#!/bin/sh
set -e

# A freshly created named volume is mounted root-owned by the Docker daemon
# regardless of the image's USER, so the non-root `app` user can't write to
# it until we fix ownership here — this container starts as root, chowns the
# scratch mount point, then drops privileges to `app` for the real command.
SCRATCH_DIR="${SCRATCH_DIR:-/scratch}"

if [ -d "$SCRATCH_DIR" ]; then
    chown app:app "$SCRATCH_DIR"
fi

exec gosu app "$@"
