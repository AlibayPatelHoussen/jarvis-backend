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

## Étape 3 — Tâches quotidiennes

| Amélioration | Détail |
|---|---|
| Liste de tâches | Ajouter, lister, terminer, supprimer ; échéance et priorité optionnelles (SQLite). |
| Rappels | « Rappelle-moi d'appeler maman dans 20 minutes » : notification dans le terminal (et à voix haute) à l'heure dite. |
| Notes | Prendre une note, chercher dans ses notes. |
| Minuteur | Cas particulier du rappel. |

## Étape 4 — Comprendre son environnement local

| Amélioration | Détail |
|---|---|
| Découverte au démarrage | Système d'exploitation, dossier de travail, outils disponibles : résumé injecté dans le prompt. |
| Fichiers | Lister un dossier, lire, chercher, écrire (avec confirmation) — limités à un dossier de travail autorisé. |
| Commandes | Exécuter une commande du terminal avec confirmation et délai maximal. |
| Web | Lire une page web et la résumer ; recherche web sans clé API. |

## Étape 5 — S'adapter à n'importe quel environnement

| Amélioration | Détail |
|---|---|
| Plugins | Tout fichier Python dans `plugins/` qui déclare des `@tool` est chargé automatiquement. |
| Client MCP | Jarvis se connecte aux serveurs MCP (standard ouvert) listés dans `config/mcp.json` et récupère seul leurs outils. |
| Import OpenAPI | À partir de la description OpenAPI d'une application, Jarvis génère les outils correspondants. |

## Étape 6 — Intégration (Nexus ou autre)

| Amélioration | Détail |
|---|---|
| API HTTP | `POST /chat` (avec streaming), `GET /tools`, sessions séparées, clé d'API. |
| Outils fournis par l'hôte | L'application hôte enregistre ses propres actions via l'API (`POST /tools`) : Jarvis peut alors les utiliser. |
| Serveur MCP | Jarvis lui-même exposé en MCP pour les hôtes compatibles. |

## Étape 7 — Finitions

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
