"""
start.py
========
Point d'entrée unique de Jarvis.

C'est le seul fichier que l'utilisateur lance :
    python start.py

Il choisit l'interface selon les arguments
et démarre Jarvis.
"""

import sys
from interface.cli import run

if __name__ == "__main__":
    run()