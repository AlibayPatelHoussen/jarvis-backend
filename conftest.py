"""
conftest.py
===========
Configuration globale de pytest.

Ce fichier est automatiquement chargé par pytest
avant tous les tests.

Il ajoute la racine du projet au sys.path pour que
tous les tests puissent importer les modules sans
avoir besoin de sys.path.insert() dans chaque fichier.
"""

import sys
from pathlib import Path

# Ajouter la racine du projet au path Python
sys.path.insert(0, str(Path(__file__).parent))
