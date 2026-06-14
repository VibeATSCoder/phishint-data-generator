#!/bin/bash
set -e

DATA_DIR="${DATA_DIR:-/data}"

mkdir -p "$DATA_DIR/jobs"
chown -R phishgen:phishgen "$DATA_DIR" 2>/dev/null || true

chown -R phishgen:phishgen /home/phishgen/.cache 2>/dev/null || true

exec runuser -u phishgen -- "$@"
