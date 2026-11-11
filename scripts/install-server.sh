#!/usr/bin/env bash
# =====================================================================
# Jarvis — installation sur un serveur Ubuntu / Debian
# =====================================================================
#
#   sudo git clone https://github.com/AlibayPatelHoussen/jarvis-backend.git /opt/jarvis
#   cd /opt/jarvis && sudo bash scripts/install-server.sh
#
# Ce que fait le script (il peut être relancé sans risque) :
#   1. installe Python (venv) et Ollama s'ils manquent
#   2. télécharge le modèle (qwen2.5:7b, ou qwen2.5:3b si moins de 8 Go de RAM)
#   3. crée l'utilisateur système « jarvis » (sans droits root)
#   4. crée l'environnement Python et le fichier .env (clé d'accès générée)
#   5. installe et démarre le service systemd « jarvis »
#
# Options (variables d'environnement) :
#   MODEL=qwen2.5:7b          modèle Ollama à utiliser
#   WORKSPACE=/media          dossier où Jarvis peut lire / écrire des fichiers
#   PORT=8765                 port local du serveur
#   DOCKER_ACCESS=yes         autoriser Jarvis à lister / redémarrer les conteneurs
#   JARVIS_USER_NAME=Prénom   prénom utilisé par Jarvis (défaut : votre login)
# =====================================================================

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE_USER="jarvis"
DATA_DIR="/var/lib/jarvis"
PORT="${PORT:-8765}"
DOCKER_ACCESS="${DOCKER_ACCESS:-yes}"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }
fail() { printf '\n\033[31m✘ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Lancez ce script avec sudo : sudo bash scripts/install-server.sh"
command -v apt-get >/dev/null || fail "Ce script est prévu pour Ubuntu / Debian (apt)."
[ -f "$APP_DIR/start.py" ] || fail "Lancez ce script depuis le dépôt Jarvis (start.py introuvable)."

# ─── Choix du modèle selon la mémoire ───────────────────────────────
RAM_GB=$(awk '/MemTotal/ {printf "%d", $2 / 1024 / 1024}' /proc/meminfo)
if [ -z "${MODEL:-}" ]; then
  if [ "$RAM_GB" -ge 8 ]; then MODEL="qwen2.5:7b"; else MODEL="qwen2.5:3b"; fi
fi
if [ -z "${WORKSPACE:-}" ]; then
  if [ -d /media ]; then WORKSPACE="/media"; else WORKSPACE="/srv"; fi
fi

echo "Jarvis sera installé avec :"
echo "  code      : $APP_DIR"
echo "  données   : $DATA_DIR"
echo "  modèle    : $MODEL (RAM détectée : ${RAM_GB} Go)"
echo "  fichiers  : $WORKSPACE"
echo "  adresse   : http://127.0.0.1:$PORT (local, à exposer via Cloudflare Tunnel)"

# ─── 1. Paquets système ─────────────────────────────────────────────
step "Paquets système"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip curl ca-certificates >/dev/null
ok "Python $(python3 --version | cut -d' ' -f2)"

# ─── 2. Ollama + modèle ─────────────────────────────────────────────
step "Ollama (modèle IA local, gratuit)"
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
systemctl enable --now ollama >/dev/null 2>&1 || true
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null || fail "Ollama ne répond pas (systemctl status ollama)."
ok "Ollama $(ollama --version 2>/dev/null | awk '{print $NF}')"
if ollama list | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
  ok "Modèle $MODEL déjà présent"
else
  echo "    Téléchargement de $MODEL (plusieurs Go, patience)…"
  ollama pull "$MODEL"
  ok "Modèle $MODEL téléchargé"
fi

# ─── 3. Utilisateur système ─────────────────────────────────────────
step "Utilisateur système « $SERVICE_USER »"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
  ok "Utilisateur créé"
else
  ok "Utilisateur déjà présent"
fi
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 750 "$DATA_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 750 "$APP_DIR/logs"
if [ "$DOCKER_ACCESS" = "yes" ] && getent group docker >/dev/null; then
  usermod -aG docker "$SERVICE_USER"
  ok "Accès à Docker (le redémarrage d'un conteneur reste soumis à votre accord)"
fi

# ─── 4. Environnement Python + configuration ───────────────────────
step "Environnement Python"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements-server.txt"
ok "Dépendances installées"

step "Configuration (.env)"
ENV_FILE="$APP_DIR/.env"
NEW_KEY=""
if [ ! -f "$ENV_FILE" ]; then
  NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  cat > "$ENV_FILE" <<EOF
# Généré par scripts/install-server.sh — modifiez puis : sudo systemctl restart jarvis
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=$MODEL
OLLAMA_NUM_CTX=4096

JARVIS_USER_NAME=${JARVIS_USER_NAME:-${SUDO_USER:-Utilisateur}}
JARVIS_LANGUAGE=fr
JARVIS_VOICE=off

JARVIS_API_KEY=$NEW_KEY
JARVIS_HOST=127.0.0.1
JARVIS_PORT=$PORT

JARVIS_DATA_DIR=$DATA_DIR
JARVIS_WORKSPACE=$WORKSPACE
JARVIS_ALLOW_COMMANDS=on
JARVIS_COMMAND_TIMEOUT=30
EOF
  ok "Fichier .env créé avec une nouvelle clé d'accès"
else
  ok "Fichier .env existant conservé"
fi
chown root:"$SERVICE_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

# ─── 5. Service systemd ─────────────────────────────────────────────
step "Service systemd « jarvis »"
cat > /etc/systemd/system/jarvis.service <<EOF
[Unit]
Description=Jarvis — assistant IA personnel
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python start.py --server
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
# Durcissement : pas d'élévation de droits, système en lecture seule
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable jarvis >/dev/null 2>&1
systemctl restart jarvis

for _ in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  sleep 1
done
HEALTH=$(curl -fsS "http://127.0.0.1:$PORT/health" 2>/dev/null) \
  || fail "Jarvis ne répond pas. Journal : journalctl -u jarvis -n 50"
ok "Jarvis répond : $HEALTH"

# ─── Résumé ─────────────────────────────────────────────────────────
printf '\n\033[1;32m✅ Jarvis est installé et démarré.\033[0m\n\n'
if [ -n "$NEW_KEY" ]; then
  echo "Clé d'accès (à garder secrète, demandée par la page web) :"
  printf '\n    \033[1m%s\033[0m\n\n' "$NEW_KEY"
  echo "Elle est aussi dans $ENV_FILE (JARVIS_API_KEY)."
else
  echo "Clé d'accès : JARVIS_API_KEY dans $ENV_FILE"
fi
cat <<EOF

Pour l'utiliser partout, exposez-le avec votre tunnel Cloudflare
(voir docs/SERVEUR.md) : ajoutez dans la configuration du tunnel

    - hostname: jarvis.votre-domaine.com
      service: http://localhost:$PORT

puis : cloudflared tunnel route dns <nom-du-tunnel> jarvis.votre-domaine.com
       sudo systemctl restart cloudflared

Commandes utiles :
    systemctl status jarvis           état du service
    journalctl -u jarvis -f           journal en direct
    sudo bash scripts/update-server.sh  mettre à jour Jarvis
EOF
