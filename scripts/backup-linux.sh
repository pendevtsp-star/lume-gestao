#!/bin/sh
set -eu

# Compatibilidade com documentacao antiga.
# Use scripts/backup-production.sh nos deploys novos.

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec sh "${SCRIPT_DIR}/backup-production.sh"
