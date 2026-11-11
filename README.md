# Jarvis Backend

Assistant IA personnel — Backend Python

## Stack technique
- Python 3.11
- Ollama (LLM local)
- SQLite (mémoire)
- FastAPI (API REST - phase 8)

## Installation

```bash
git clone https://github.com/AlibayPatelHoussen/jarvis-backend.git
cd jarvis-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python start.py
```

## Parler avec Jarvis dans le terminal

1. Installer [Ollama](https://ollama.com) (gratuit) puis un modèle :
   ```bash
   ollama pull qwen2.5:7b      # conseillé : bon en français et avec les outils
   ```
2. Dans `.env` : `OLLAMA_MODEL=qwen2.5:7b` (et `JARVIS_USER_NAME=Votre prénom`)
3. Lancer : `python start.py`

Jarvis choisit seul ses outils (calcul, date, météo, actualités, mémoire) :
« J'ai 3 réunions de 45 minutes, ça fait combien d'heures ? » déclenche l'outil
de calcul. `/outils` liste ce qu'il sait faire. Il faut pour cela un modèle
compatible avec les outils (qwen2.5, llama3.1, mistral v0.3).

Pour ajouter une capacité, il suffit de déclarer une fonction Python :

```python
@registry.tool()
def convertir_euros(montant: float, devise: str = "USD") -> str:
    """
    Convertit un montant en euros vers une autre devise.

    Args:
        montant : Montant en euros
        devise  : Code de la devise cible
    """
```

Les réponses s'affichent en direct. Commandes utiles : `/aide`, `/modele`,
`/voix on|off`, `/effacer`, `quit`. Sans Ollama, les commandes directes
(calcul, météo, actualités, mémoire) fonctionnent quand même.

La suite du projet est décrite dans [docs/ROADMAP.md](docs/ROADMAP.md).

## Structure
core/       → Cerveau (logique centrale)
llm/        → Connexion aux modèles IA
tools/      → Fonctionnalités (météo, email...)
interface/  → CLI et voix
api/        → API REST (phase 8)
config/     → Configuration
tests/      → Tests unitaires

## Branches
- main     → Production stable
- develop  → Intégration
- feature/ → Développement
