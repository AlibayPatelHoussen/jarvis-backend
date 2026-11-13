# Feuille de route de Jarvis

Objectif : un assistant **100 % gratuit et local** (Ollama), avec qui on discute
dans le terminal, qui aide aux tâches quotidiennes et qui **découvre seul
l'environnement** où on l'installe (ordinateur, application hôte comme Nexus),
pour pouvoir y faire ce qu'on lui demande.

Principe clé : aujourd'hui Jarvis reconnaît des phrases avec des expressions
régulières. Demain, c'est **le modèle qui choisit les outils** (« tool calling »
d'Ollama) à partir de leur description. Ajouter une capacité = ajouter un outil
décrit ; brancher Jarvis dans un nouvel environnement = lui donner les outils de
cet environnement (plugins, MCP, API HTTP).

---

## Étape 1 — Conversation fluide dans le terminal ✅

| Amélioration | Détail |
|---|---|
| Réponses en direct | Le texte s'affiche au fur et à mesure (streaming Ollama) au lieu d'attendre la réponse complète. |
| Date et heure connues | Le prompt système contient la date et l'heure du jour : indispensable pour « demain », « dans 2 heures », etc. |
| Langue configurable | `JARVIS_LANGUAGE=fr` ou `en` est enfin utilisé. |
| Vérification au démarrage | Jarvis vérifie que le modèle est installé et affiche la commande `ollama pull …` sinon. |
| Historique du clavier | Flèches haut/bas pour rappeler les messages précédents (readline). |
| Commandes système | `/aide`, `/modele`, `/voix on|off`, `/effacer`, `/quitter`. |
| Moins de latence | Plus de requête « Ollama est-il là ? » avant chaque message. |

## Étape 2 — Cerveau agent + registre d'outils ✅

| Amélioration | Détail |
|---|---|
| Registre d'outils | Chaque outil déclare un nom, une description et ses paramètres (JSON Schema). Un décorateur `@tool` suffit pour en ajouter un. |
| Tool calling Ollama | Le modèle reçoit la liste des outils et décide lui-même lesquels appeler, avec quels arguments. |
| Boucle agent | Modèle → appels d'outils → résultats → modèle… jusqu'à la réponse finale (limite de tours pour éviter les boucles). |
| Outils existants convertis | Calcul, météo, actualités, mémoire (mémoriser / rappeler / oublier), date et heure. |
| Commandes directes conservées | Les commandes exactes (« météo à Paris », « calcule 2+2 »…) restent instantanées et marchent même sans Ollama. |
| Repli automatique | Si le modèle ne gère pas les outils, Jarvis le signale et discute sans outils. |
| Confirmation | Les outils sensibles demandent une confirmation (o/n) avant de s'exécuter. |

## Étape 3 — Tâches quotidiennes ✅

| Amélioration | Détail |
|---|---|
| Liste de tâches | Ajouter, lister, terminer, supprimer ; échéance et priorité optionnelles (SQLite). |
| Rappels | « Rappelle-moi d'appeler maman dans 20 minutes » : notification dans le terminal (et à voix haute) à l'heure dite. |
| Notes | Prendre une note, chercher dans ses notes. |
| Minuteur | Cas particulier du rappel. |

## Étape 4 — Comprendre son environnement local ✅

| Amélioration | Détail |
|---|---|
| Découverte au démarrage | Système, machine, shell, dossier de travail, logiciels présents (docker, systemctl, git, ffmpeg…) : résumé injecté dans le prompt (`/environnement`). Seuls les outils utilisables sur la machine sont proposés. |
| État du serveur | `infos_systeme` (CPU, mémoire, disques, charge, durée d'allumage), `espace_disque`, `processus`. |
| Docker / services | `conteneurs_docker`, `journaux_conteneur`, `redemarrer_conteneur` (confirmation), `etat_service` (systemd). |
| Fichiers | Lister, lire, chercher par nom ou par contenu, écrire (confirmation) — limités à `JARVIS_WORKSPACE`. |
| Commandes | `executer_commande` avec confirmation et délai maximal. |
| Web | `lire_page_web` (aussi en réseau local) et `recherche_web` (DuckDuckGo, sans clé). |
| Sécurité | Le contenu des fichiers, pages et sorties est traité comme une donnée, jamais comme un ordre. |

## Étape 5 — S'adapter à n'importe quel environnement (en cours)

| Amélioration | Détail |
|---|---|
| Outils fournis par l'hôte ✅ | Une application (Nexus) publie un manifeste de ses actions ; Jarvis les découvre seul et les utilise (téléchargements, bibliothèque, IPTV), selon les droits de l'utilisateur. |
| Fichiers ✅ | Renommer / déplacer, créer un dossier, supprimer (avec autorisation). |
| Plugins | Tout fichier Python dans `plugins/` qui déclare des `@tool` est chargé automatiquement. |
| Client MCP | Jarvis se connecte aux serveurs MCP (standard ouvert) listés dans `config/mcp.json` et récupère seul leurs outils. |
| Import OpenAPI | À partir de la description OpenAPI d'une application, Jarvis génère les outils correspondants. |

## Étape 6 — Jarvis sur ton serveur, utilisable partout ✅

| Amélioration | Détail |
|---|---|
| Mode serveur | `python start.py --server` : API HTTP (FastAPI), **sans interface**, en local sur le serveur. Les interfaces (Nexus, app web dédiée…) sont des projets séparés. |
| Sécurité | Clé d'accès obligatoire, écoute en local par défaut, CORS seulement pour les interfaces autorisées. |
| Multi-utilisateur | Une conversation, une mémoire et des tâches par utilisateur ; outils selon le rôle (`admin` / `user`), comme Nexus. |
| Installation | `scripts/install-server.sh` (Ollama, modèle, utilisateur système, service systemd) et `scripts/update-server.sh`. Voir [SERVEUR.md](SERVEUR.md). |
| API documentée | [API.md](API.md) : tout ce qu'une interface doit savoir. |

## Étape 7 — Se brancher partout ✅

| Amélioration | Détail |
|---|---|
| Clés par application | `python start.py cles ajouter|liste|supprimer` : une clé révocable par application, avec rôle maximal, utilisateur et option « confiance » (parler au nom de ses utilisateurs, ex. Nexus). |
| API au format standard (OpenAI) | `/v1/models`, `/v1/chat/completions` (streaming ou non) : tout logiciel qui accepte une adresse « OpenAI » personnalisée parle à Jarvis, sans code. Aucun compte OpenAI : c'est seulement le format des messages, tout reste sur ton serveur. |
| Autorisations à distance | Une action sensible demandée depuis une application sans bouton de confirmation est mise en attente ; tu l'autorises depuis ton interface (`/api/approvals`), le résultat arrive en notification. |

## Étape 8 — Notifications push ✅

| Amélioration | Détail |
|---|---|
| Notifications push | Rappels et demandes d'autorisation envoyés aux appareils abonnés (Web Push standard, chiffré, sans compte). L'interface fournit le service worker et s'abonne via `/api/push/*`. |
| Voix | Côté interface, avec les API du navigateur (reconnaissance et synthèse vocale) : décrit dans [API.md](API.md). |

## Étape 9 — Page Jarvis dans Nexus

Dans le dépôt Nexus : page « Jarvis » (section Serveur, au-dessus de Fichiers ;
onglet Aperçu sur iPhone). Le backend Nexus relaie ses utilisateurs vers l'API
Jarvis avec une clé `--confiance` ; la clé ne quitte jamais le serveur.

## Étape 10 — Finitions

| Amélioration | Détail |
|---|---|
| Journalisation | Fichiers de logs dans `logs/`. |
| Installation | `pyproject.toml`, commande `jarvis`, Dockerfile. |
| Mémoire sémantique | Retrouver les souvenirs pertinents par le sens (embeddings Ollama), pas seulement par mot-clé. |

---

### Modèle conseillé

Le tool calling demande un modèle compatible. Gratuits via Ollama :

- `qwen2.5:7b` — très bon en français et avec les outils (conseillé) ;
- `llama3.1:8b` ;
- `mistral` (v0.3, le modèle actuel par défaut).

```bash
ollama pull qwen2.5:7b
# puis dans .env : OLLAMA_MODEL=qwen2.5:7b
```
