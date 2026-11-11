# API de Jarvis

Référence de l'API HTTP du serveur (`python start.py --server`). Elle sert à la
page web intégrée et servira à brancher Jarvis dans d'autres applications
(Nexus…).

Adresse par défaut : `http://127.0.0.1:8765` (voir [SERVEUR.md](SERVEUR.md)).

## Authentification

Toutes les routes `/api/*` exigent la clé `JARVIS_API_KEY` :

```
Authorization: Bearer <JARVIS_API_KEY>
```

Réponse `401` si la clé est absente ou fausse.

## Identité et rôles

Sans en-tête particulier, la requête est faite au nom du **propriétaire**
(utilisateur `owner`, rôle `admin`).

Une application de confiance qui possède la clé peut parler **au nom de ses
utilisateurs** :

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
L'application hôte est responsable de transmettre le bon rôle.

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

### `GET /api/history`

Conversation en cours : `{"messages": [{"role": "user", "content": "…"}, …]}`

### `POST /api/conversation/clear`

Commence une nouvelle conversation (la mémoire, les tâches et les notes restent).

### `GET /api/notifications`

Rappels arrivés à échéance depuis le dernier appel (chaque rappel n'est rendu
qu'une fois) :

```json
{"notifications": [{"id": 3, "message": "Appeler maman", "due_at": "2026-11-12T14:35:00"}]}
```

La page web interroge cette route toutes les 20 secondes.

## Intégration dans une application (ex. Nexus)

Schéma conseillé : le **backend** de l'application appelle Jarvis, jamais le
navigateur directement (la clé reste côté serveur).

1. Le navigateur appelle l'application (`POST /api/jarvis/chat`), authentifié
   comme d'habitude.
2. Le backend relaie vers Jarvis avec la clé et l'identité de l'utilisateur
   (`X-Jarvis-User`, `X-Jarvis-Name`, `X-Jarvis-Role`), et retransmet le flux SSE
   tel quel.
3. Il relaie aussi `/api/chat/confirm`, `/api/notifications`, `/api/history`,
   `/api/conversation/clear` avec les mêmes en-têtes.
