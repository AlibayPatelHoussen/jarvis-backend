#!/usr/bin/env bash
# =====================================================================
# Jarvis — mise à jour sur le serveur
#
#   cd /opt/jarvis && sudo bash scripts/update-server.sh
#
# Récupère la dernière version de main, met à jour les dépendances,
# redémarre le service et vérifie qu'il répond.
# =====================================================================

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BRANCH="${BRANCH:-main}"

[ "$(id -u)" -eq 0 ] || { echo "Lancez avec sudo : sudo bash scripts/update-server.sh" >&2; exit 1; }
cd "$APP_DIR"

PORT=$(grep -E '^JARVIS_PORT=' .env 2>/dev/null | cut -d= -f2)
PORT="${PORT:-8765}"

BEFORE=$(git rev-parse --short HEAD)
git fetch --quiet origin "$BRANCH"
git checkout --quiet "$BRANCH"
git merge --quiet --ff-only "origin/$BRANCH"
AFTER=$(git rev-parse --short HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
  echo "Déjà à jour ($AFTER)."
else
  echo "Mise à jour $BEFORE → $AFTER"
  git log --oneline "$BEFORE..$AFTER" | sed 's/^/  /'
fi

.venv/bin/pip install -q -r requirements-server.txt
systemctl restart jarvis

for _ in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  sleep 1
done
if HEALTH=$(curl -fsS "http://127.0.0.1:$PORT/health" 2>/dev/null); then
  echo "✅ Jarvis $AFTER répond : $HEALTH"
else
  echo "✘ Jarvis ne répond pas. Journal : journalctl -u jarvis -n 50" >&2
  exit 1
fi
