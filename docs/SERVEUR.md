# Jarvis sur ton serveur

Jarvis tourne sur le serveur comme un **service sans interface** (une API), à
côté d'Ollama (le modèle IA, gratuit et local). Les interfaces sont des projets
séparés qui parlent à cette API :

```
 Nexus (page Jarvis) ─┐
 App web Jarvis ──────┼──► API Jarvis (127.0.0.1:8765) ──► Ollama (127.0.0.1:11434)
 Autres logiciels ────┘          │
                                 └─► outils : état du serveur, Docker, fichiers,
                                     tâches, rappels, notes, web…
```

- Jarvis n'écoute **qu'en local** par défaut.
- Chaque interface a **sa clé d'accès** (révocable).
- Toute action sensible (commande, écriture de fichier, redémarrage d'un
  conteneur) demande une autorisation, que l'interface affiche.
- Tu peux aussi lui parler **dans le terminal** du serveur.

## 1. Installer

Sur le serveur (Ubuntu) :

```bash
sudo git clone https://github.com/AlibayPatelHoussen/jarvis-backend.git /opt/jarvis
cd /opt/jarvis
sudo bash scripts/install-server.sh
```

Le script :

1. installe Python et **Ollama** s'ils manquent ;
2. télécharge le modèle : `qwen2.5:7b` (≥ 8 Go de RAM) ou `qwen2.5:3b` (moins de RAM) ;
3. crée l'utilisateur système `jarvis` (sans droits root) ;
4. crée l'environnement Python et `/opt/jarvis/.env` avec une **clé d'accès principale** ;
5. installe et démarre le service `jarvis`, puis vérifie qu'il répond.

Options (avant `sudo bash …`, ex. `sudo MODEL=qwen2.5:3b bash scripts/install-server.sh`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `MODEL` | selon la RAM | Modèle Ollama |
| `WORKSPACE` | `/media` | Dossier où Jarvis peut lire et écrire des fichiers |
| `PORT` | `8765` | Port local |
| `DOCKER_ACCESS` | `yes` | Laisse Jarvis lister les conteneurs, lire leurs logs, les redémarrer (avec ton accord) |
| `JARVIS_USER_NAME` | ton login | Prénom utilisé par Jarvis |
| `FULL_ACCESS` | `no` | `yes` : **accès complet** — Jarvis tourne en root, dossier de travail `/` (voir ci-dessous) |

### Accès complet à tout le serveur

```bash
cd /opt/jarvis && sudo FULL_ACCESS=yes bash scripts/install-server.sh
```

Jarvis tourne alors en **root**, sans restriction systemd, avec `/` comme dossier
de travail : il peut lire, chercher, écrire et lancer des commandes partout
(configurations, journaux, services, paquets…). Les garde-fous restent : chaque
commande, écriture de fichier ou redémarrage demande ton autorisation (bouton
« Autoriser » dans Nexus). Les recherches de fichiers ignorent `/proc`, `/sys`,
`/dev`, `/run` et s'arrêtent au bout de 20 s. Les commandes de gestion se lancent
alors avec `sudo` (et non `sudo -u jarvis`).

Le script peut être relancé : il garde le `.env` et la clé existants.

## 2. Brancher une interface

Crée **une clé par interface** :

```bash
cd /opt/jarvis
# Nexus : parle au nom de chacun de ses utilisateurs (rôles admin / user)
sudo -u jarvis .venv/bin/python start.py cles ajouter nexus --role admin --confiance
# Une app web dédiée à Jarvis, ou un logiciel au format standard « OpenAI »
sudo -u jarvis .venv/bin/python start.py cles ajouter app-jarvis
sudo -u jarvis .venv/bin/python start.py cles liste
```

- **Nexus** (même serveur) : son backend appelle `http://127.0.0.1:8765` avec la
  clé `nexus` ; rien à exposer sur internet.
- **App web séparée** : soit elle passe par son propre backend (comme Nexus), soit
  le navigateur appelle Jarvis directement — expose alors Jarvis en HTTPS (tunnel
  Cloudflare, ci-dessous) et autorise l'adresse de l'app dans `.env` :
  `JARVIS_CORS_ORIGINS=https://jarvis-app.mondomaine.com`.
- **Logiciel au format standard « OpenAI »** : adresse `…/v1`, clé `jv_…`, modèle
  `jarvis`. Aucun compte OpenAI n'est utilisé : c'est seulement le format des
  messages, ton Jarvis répond.

La référence complète est dans [API.md](API.md) : chat en direct, autorisations,
rappels, notifications push, voix (côté interface).

### Exposer Jarvis sur internet (seulement si nécessaire)

Uniquement pour une interface hébergée ailleurs qui appelle Jarvis directement.
Dans la configuration du tunnel Cloudflare, **avant** la règle finale `http_status:404` :

```yaml
  - hostname: jarvis.houssen-serveur.com
    service: http://localhost:8765
```

```bash
cloudflared tunnel route dns <nom-du-tunnel> jarvis.houssen-serveur.com
sudo systemctl restart cloudflared
```

## 3. Parler à Jarvis dans le terminal du serveur

```bash
cd /opt/jarvis && sudo -u jarvis .venv/bin/python start.py
```

## 4. Mettre à jour

```bash
cd /opt/jarvis && sudo bash scripts/update-server.sh
```

Récupère `main`, met à jour les dépendances, redémarre et vérifie que Jarvis répond.

## 5. Configuration

Tout est dans `/opt/jarvis/.env` (puis `sudo systemctl restart jarvis`) :

| Variable | Rôle |
|---|---|
| `OLLAMA_MODEL` | Modèle utilisé (`ollama list` pour voir ceux installés) |
| `JARVIS_API_KEY` | Clé principale. Pour la changer : `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `JARVIS_WORKSPACE` | Dossier des fichiers accessibles à Jarvis |
| `JARVIS_ALLOW_COMMANDS` | `off` pour interdire toute commande, même confirmée |
| `JARVIS_CORS_ORIGINS` | Interfaces web autorisées à appeler l'API depuis le navigateur |
| `JARVIS_PUSH_CONTACT` | E-mail transmis aux services de notifications push (`mailto:…`) |
| `JARVIS_DATA_DIR` | Mémoire, tâches, rappels, notes, clés (`/var/lib/jarvis`) |

## 6. Sécurité

- Le service tourne sous l'utilisateur `jarvis`, **sans sudo** : une commande ne
  peut pas modifier le système (`ProtectSystem=full`, `NoNewPrivileges`).
- Les fichiers sont limités à `JARVIS_WORKSPACE` (les `..` et liens symboliques
  vers l'extérieur sont bloqués). Pour écrire, l'utilisateur `jarvis` doit avoir
  les droits sur le dossier (ex. `sudo setfacl -R -m u:jarvis:rwX /media/notes`).
- Le groupe `docker` donne beaucoup de pouvoir : mets `DOCKER_ACCESS=no` si tu
  préfères que Jarvis ne touche pas aux conteneurs.
- Une clé par interface : en cas de doute, `start.py cles supprimer <nom>`.

## 7. Dépannage

| Symptôme | Solution |
|---|---|
| `/health` indique « Ollama n'est pas accessible » | `systemctl status ollama` puis `sudo systemctl restart ollama` |
| `/health` indique « Le modèle … n'est pas installé » | `ollama pull <modèle>` |
| L'interface reçoit `401` | Vérifier sa clé (`start.py cles liste`) |
| Réponses lentes | Modèle plus petit (`qwen2.5:3b`) ou `OLLAMA_NUM_CTX=2048` |
| Journal | `journalctl -u jarvis -n 100` |

```bash
curl http://127.0.0.1:8765/health
```
