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
