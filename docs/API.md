# API de Jarvis

Référence de l'API HTTP du serveur (`python start.py --server`). Elle sert à la
page web intégrée et servira à brancher Jarvis dans d'autres applications
(Nexus…).

Adresse par défaut : `http://127.0.0.1:8765` (voir [SERVEUR.md](SERVEUR.md)).

## Authentification

Toutes les routes `/api/*` et `/v1/*` exigent une clé :

```
Authorization: Bearer <clé>
```

Deux sortes de clés :

| Clé | Pour | Droits |
|---|---|---|
| `JARVIS_API_KEY` (dans `.env`) | Toi (la page web) | Propriétaire, admin, peut parler au nom d'autres utilisateurs |
| **Clé d'application** (`jv_…`) | Nexus, ton téléphone, un autre logiciel | Selon la clé : rôle maximal, utilisateur, « confiance » |

**Une clé par application** : tu peux en retirer une sans toucher aux autres.

```bash
cd /opt/jarvis
sudo -u jarvis .venv/bin/python start.py cles ajouter telephone
sudo -u jarvis .venv/bin/python start.py cles ajouter nexus --role admin --confiance
sudo -u jarvis .venv/bin/python start.py cles ajouter domotique --role user
sudo -u jarvis .venv/bin/python start.py cles liste
sudo -u jarvis .venv/bin/python start.py cles supprimer telephone
```

| Option | Défaut | Sens |
|---|---|---|
| `--role` | `admin` | Rôle maximal (`user` : sans commandes, fichiers, Docker, services) |
| `--utilisateur` | `owner` | À qui appartiennent conversation, mémoire, tâches |
| `--confiance` | non | L'application peut parler au nom de **ses** utilisateurs (`X-Jarvis-User`) |

La clé n'est affichée qu'une fois (seule son empreinte est stockée). Prise en
compte immédiate, sans redémarrer. Réponse `401` si la clé est absente, fausse
ou supprimée.

## Identité et rôles

Sans en-tête particulier, la requête est faite au nom du **propriétaire**
(utilisateur `owner`, rôle `admin`).

Une clé d'application parle au nom de son utilisateur (`--utilisateur`, par
défaut le propriétaire) avec son rôle (`--role`).

Une application **de confiance** (`JARVIS_API_KEY` ou clé `--confiance`) peut
parler **au nom de ses utilisateurs** — sinon `403` :

| En-tête | Exemple | Rôle |
|---|---|---|
| `X-Jarvis-User` | `42` | Identifiant stable (lettres, chiffres, `_`, `-`, 64 max) |
| `X-Jarvis-Name` | `Alice` | Prénom utilisé dans la conversation |
| `X-Jarvis-Role` | `user` | `admin` ou `user` (défaut : `user`) |

Chaque utilisateur a sa propre conversation, mémoire, tâches, rappels et notes
(`<JARVIS_DATA_DIR>/users/<id>/memory.db`).

| Rôle | Outils |
|---|---|
| `admin` | Tous : état du serveur, processus, Docker, services, commandes, fichiers, web, tâches… |
| `user` | Conversation, calcul, météo, actualités, mémoire, tâches / rappels / notes, web, état général du serveur (`infos_systeme`, `espace_disque`). **Pas** de commandes, fichiers, Docker, services ni processus. |

Mêmes règles que Nexus (terminal, fichiers et services réservés aux admins).
L'application hôte est responsable de transmettre le bon rôle ; le rôle demandé
ne dépasse **jamais** le rôle de sa clé (une clé `user` ne peut pas obtenir `admin`).

## API au format standard (OpenAI) — brancher n'importe quel logiciel

> **Aucun compte OpenAI n'est utilisé.** « Format OpenAI » désigne seulement la
> façon d'écrire les messages, devenue un standard que beaucoup d'applications
> savent parler. Les messages vont à **ton** serveur et c'est **ton** Jarvis
> (modèle local Ollama) qui répond : rien n'est envoyé à OpenAI ni à Anthropic,
> rien n'est payant.

Beaucoup d'applications (sur téléphone, ordinateur, domotique, éditeurs…) savent
parler à un serveur « au format OpenAI » en acceptant une adresse personnalisée.
Elles peuvent parler à Jarvis sans aucun code :

| Réglage dans l'application | Valeur |
|---|---|
| Adresse / Base URL | `https://jarvis.<ton-domaine>/v1` |
| Clé API | une clé d'application (`jv_…`) |
| Modèle | `jarvis` |

Routes : `GET /v1/models` et `POST /v1/chat/completions` (avec ou sans
`"stream": true`, fin de flux `data: [DONE]`).

- C'est **le même Jarvis** : mêmes outils, même mémoire, mêmes tâches que la page web.
- L'historique envoyé par l'application est utilisé (20 derniers messages) ; la
  conversation de la page web n'est pas modifiée.
- Les messages `system` de l'application sont ignorés : Jarvis garde sa
  personnalité et ses règles de sécurité.
- **Actions sensibles** (commande, redémarrage, écriture) : comme l'application
  n'a pas de bouton Autoriser, elles sont **mises en attente**. Jarvis répond
  qu'il attend ton accord ; tu autorises depuis la page web (ou `/api/approvals`),
  puis le résultat arrive en notification.

Exemple avec la bibliothèque Python `openai` (elle sait parler ce format ; ici
elle parle **uniquement** à ton serveur Jarvis) :

```python
from openai import OpenAI
jarvis = OpenAI(base_url="https://jarvis.houssen-serveur.com/v1", api_key="jv_…")
r = jarvis.chat.completions.create(model="jarvis",
        messages=[{"role": "user", "content": "Comment va le serveur ?"}])
print(r.choices[0].message.content)
```

## Routes

### `GET /health` (sans clé)

```json
{"status": "ok", "version": "1.0.0", "model": "qwen2.5:7b",
 "llm_ready": true, "warning": null}
```

`warning` explique quoi faire si Ollama ou le modèle manquent.

### `GET /api/me`

```json
{"user": "owner", "role": "admin", "name": "Houssen"}
```

### `GET /api/tools`

Outils disponibles pour cet utilisateur :

```json
{"tools": [{"name": "creer_rappel", "description": "Programme un rappel…", "confirm": false}]}
```

### `POST /api/chat`

```json
{"message": "Rappelle-moi d'appeler maman dans 20 minutes"}
```

Réponse en flux **Server-Sent Events** (`text/event-stream`) :

| Événement | Données | Sens |
|---|---|---|
| `token` | `{"text": "…"}` | Morceau de la réponse (à concaténer) |
| `tool` | `{"name": "creer_rappel", "arguments": {…}}` | Jarvis utilise un outil |
| `confirm` | `{"id": "…", "action": "executer_commande(commande='…')"}` | Autorisation demandée → `POST /api/chat/confirm` |
| `done` | `{"response": "…"}` | Fin, réponse complète |
| `error` | `{"message": "…"}` | Erreur interne (le flux se termine) |

Exemple :

```
event: tool
data: {"name": "creer_rappel", "arguments": {"message": "Appeler maman", "quand": "dans 20 minutes"}}

event: token
data: {"text": "C'est noté, "}

event: token
data: {"text": "je vous le rappellerai à 14 h 35."}

event: done
data: {"response": "C'est noté, je vous le rappellerai à 14 h 35."}
```

Codes : `409` si Jarvis répond déjà à un message de cet utilisateur, `422` si le
message est vide.

```bash
curl -N -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"message": "Comment va le serveur ?"}' http://127.0.0.1:8765/api/chat
```

### `POST /api/chat/confirm`

Répond à un événement `confirm` (pendant que le flux de `/api/chat` est ouvert) :

```json
{"id": "<id reçu>", "approved": true}
```

Sans réponse sous `JARVIS_CONFIRM_TIMEOUT` secondes (120 par défaut), l'action
est refusée. `404` si l'id est inconnu ou appartient à un autre utilisateur.

### `GET /api/approvals`

Actions sensibles demandées depuis une application sans écran de confirmation :

```json
{"approvals": [{"id": 1, "action": "redemarrer_conteneur(nom='jellyfin')",
                "source": "telephone", "created": "2026-11-12T14:35:02"}]}
```

Une demande expire au bout d'une heure.

### `POST /api/approvals/{id}`

```json
{"approved": true}
```

Exécute (ou refuse) l'action et renvoie `{"approved": true, "result": "…"}`.
`404` si la demande est inconnue, expirée ou appartient à un autre utilisateur.

### Notifications push

| Route | Corps | Rôle |
|---|---|---|
| `GET /api/push/key` | — | Clé publique VAPID (`{"publicKey": "…"}`) pour `pushManager.subscribe` |
| `POST /api/push/subscribe` | `PushSubscription.toJSON()` du navigateur | Abonne cet appareil (services de push d'Apple, Google, Mozilla, Microsoft uniquement) |
| `POST /api/push/unsubscribe` | `{"endpoint": "…"}` | Désabonne cet appareil |
| `POST /api/push/test` | — | Envoie une notification de test (`{"sent": <nb d'appareils>}`) |

Les notifications (`/api/notifications`) sont aussi envoyées en push à tous les
appareils abonnés de l'utilisateur. Le service worker est servi sur `/sw.js`.

### `GET /api/history`

Conversation en cours : `{"messages": [{"role": "user", "content": "…"}, …]}`

### `POST /api/conversation/clear`

Commence une nouvelle conversation (la mémoire, les tâches et les notes restent).

### `GET /api/notifications`

Rappels arrivés à échéance (`kind: "reminder"`) et informations (`kind: "info"` :
demande d'autorisation, résultat d'une action autorisée) depuis le dernier appel
(chacune n'est rendue qu'une fois) :

```json
{"notifications": [{"id": 3, "kind": "reminder", "message": "Appeler maman",
                    "due_at": "2026-11-12T14:35:00"}]}
```

La page web interroge cette route toutes les 20 secondes.

## Intégration dans une application (ex. Nexus)

Schéma conseillé : le **backend** de l'application appelle Jarvis, jamais le
navigateur directement (la clé reste côté serveur).

0. Créer la clé de l'application :
   `python start.py cles ajouter nexus --role admin --confiance`.
1. Le navigateur appelle l'application (`POST /api/jarvis/chat`), authentifié
   comme d'habitude.
2. Le backend relaie vers Jarvis avec la clé et l'identité de l'utilisateur
   (`X-Jarvis-User`, `X-Jarvis-Name`, `X-Jarvis-Role`), et retransmet le flux SSE
   tel quel.
3. Il relaie aussi `/api/chat/confirm`, `/api/notifications`, `/api/history`,
   `/api/conversation/clear` avec les mêmes en-têtes.
