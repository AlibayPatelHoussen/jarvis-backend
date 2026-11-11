# Jarvis sur ton serveur

Jarvis tourne sur le serveur comme un service, à côté d'Ollama (le modèle IA,
gratuit et local). Tu lui parles depuis n'importe où avec ta page web
`https://jarvis.<ton-domaine>`, sur téléphone comme sur ordinateur.

```
 Téléphone / PC ──HTTPS──► Cloudflare Tunnel ──► Jarvis (127.0.0.1:8765) ──► Ollama (127.0.0.1:11434)
                                                     │
                                                     └─► outils : état du serveur, Docker, fichiers,
                                                         tâches, rappels, notes, web…
```

- Jarvis n'écoute **qu'en local** : rien n'est ouvert sur ta box, tout passe par le
  tunnel Cloudflare que tu utilises déjà pour Nexus.
- Une **clé d'accès** (générée à l'installation) protège la page web et l'API.
- Toute action sensible (commande, écriture de fichier, redémarrage d'un conteneur)
  affiche **Autoriser / Refuser** dans la page.

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
4. crée l'environnement Python et `/opt/jarvis/.env` avec une **clé d'accès** ;
5. installe et démarre le service `jarvis`, puis vérifie qu'il répond.

À la fin, il affiche la clé d'accès : garde-la, la page web te la demandera.

Options (avant `sudo bash …`, ex. `sudo MODEL=qwen2.5:3b bash scripts/install-server.sh`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `MODEL` | selon la RAM | Modèle Ollama |
| `WORKSPACE` | `/media` | Dossier où Jarvis peut lire et écrire des fichiers |
| `PORT` | `8765` | Port local |
| `DOCKER_ACCESS` | `yes` | Laisse Jarvis lister les conteneurs, lire leurs logs, les redémarrer (avec ton accord) |
| `JARVIS_USER_NAME` | ton login | Prénom utilisé par Jarvis |

Le script peut être relancé : il garde le `.env` et la clé existants.

## 2. Accéder à Jarvis depuis partout (Cloudflare Tunnel)

Ton tunnel expose déjà Nexus. Ajoute une entrée pour Jarvis dans la configuration
du tunnel (souvent `/etc/cloudflared/config.yml`), **avant** la règle finale
`http_status:404` :

```yaml
ingress:
  - hostname: nexus.houssen-serveur.com
    service: http://localhost:3001
  - hostname: jarvis.houssen-serveur.com     # ← nouveau
    service: http://localhost:8765
  - service: http_status:404
```

Puis :

```bash
cloudflared tunnel route dns <nom-du-tunnel> jarvis.houssen-serveur.com
sudo systemctl restart cloudflared
```

Ouvre `https://jarvis.houssen-serveur.com`, entre la clé : c'est prêt.
Sur iPhone : *Partager → Sur l'écran d'accueil* pour l'avoir comme une app.

> Les réponses arrivent en direct (Server-Sent Events) : Cloudflare les transmet
> sans configuration particulière.

## 3. Utiliser

- **Page web** : `https://jarvis.<ton-domaine>` — conversation en direct, outils
  affichés, boutons Autoriser / Refuser, rappels (notification du navigateur si
  la page est ouverte).
- **Terminal du serveur** (en SSH) :
  ```bash
  cd /opt/jarvis && sudo -u jarvis .venv/bin/python start.py
  ```
- **API** pour d'autres applications (Nexus plus tard) : voir [API.md](API.md).

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
| `JARVIS_API_KEY` | Clé d'accès. Pour la changer : `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `JARVIS_WORKSPACE` | Dossier des fichiers accessibles à Jarvis |
| `JARVIS_ALLOW_COMMANDS` | `off` pour interdire toute commande, même confirmée |
| `JARVIS_DATA_DIR` | Mémoire, tâches, rappels, notes (`/var/lib/jarvis`) |

## 6. Sécurité

- Le service tourne sous l'utilisateur `jarvis`, **sans sudo** : une commande ne
  peut pas modifier le système (`ProtectSystem=full`, `NoNewPrivileges`).
- Les fichiers sont limités à `JARVIS_WORKSPACE` (les `..` et liens symboliques
  vers l'extérieur sont bloqués). Pour écrire, l'utilisateur `jarvis` doit avoir
  les droits sur le dossier (ex. `sudo setfacl -R -m u:jarvis:rwX /media/notes`).
- Le groupe `docker` donne beaucoup de pouvoir : mets `DOCKER_ACCESS=no` si tu
  préfères que Jarvis ne touche pas aux conteneurs.
- Garde la clé secrète ; en cas de doute, change-la dans `.env` et redémarre.

## 7. Dépannage

| Symptôme | Solution |
|---|---|
| Bandeau « Ollama n'est pas accessible » | `systemctl status ollama` puis `sudo systemctl restart ollama` |
| Bandeau « Le modèle … n'est pas installé » | `ollama pull <modèle>` |
| Page inaccessible depuis l'extérieur | `curl http://127.0.0.1:8765/health` sur le serveur ; vérifier l'entrée du tunnel et `systemctl status cloudflared` |
| « Clé d'accès invalide » | Comparer avec `JARVIS_API_KEY` dans `/opt/jarvis/.env` |
| Réponses lentes | Modèle plus petit (`qwen2.5:3b`) ou `OLLAMA_NUM_CTX=2048` |
| Journal | `journalctl -u jarvis -n 100` |
