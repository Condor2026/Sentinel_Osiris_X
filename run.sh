#!/usr/bin/env bash
# ============================================================
# SENTINELA OSIRIS — arranque
# Uso: ./run.sh [args para SentinelOsirisMar.py]
# Ej.:  ./run.sh --demo --no-browser
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    . .venv/bin/activate
fi

if [ ! -f SentinelOsirisMar.py ]; then
    echo "ERROR: SentinelOsirisMar.py no encontrado en $(pwd)" >&2
    exit 1
fi

echo "◈ SENTINELA OSIRIS arrancando…"
exec python SentinelOsirisMar.py "$@"
