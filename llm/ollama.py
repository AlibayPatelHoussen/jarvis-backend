"""
llm/ollama.py
=============
Connexion au modèle IA local via Ollama.

Responsabilité unique : envoyer un message à Ollama
et retourner la réponse. Rien d'autre.

Pourquoi urllib et pas requests ?
- urllib est dans la stdlib Python (pas de dépendance externe)
- On ajoutera requests plus tard si nécessaire
"""

import json
import urllib.request
import urllib.error
from config import settings


class OllamaError(Exception):
    """Erreur spécifique à Ollama."""
    pass


class Ollama:
    """
    Client pour communiquer avec Ollama.

    Usage :
        ollama = Ollama()
        response = ollama.ask("Bonjour !")
        print(response)
    """

    def __init__(
        self,
        host: str = None,
        model: str = None
    ):
        """
        Initialise le client Ollama.

        Args:
            host  : URL d'Ollama (défaut : settings.OLLAMA_HOST)
            model : Nom du modèle (défaut : settings.OLLAMA_MODEL)
        """
        self.host = host or settings.OLLAMA_HOST
        self.model = model or settings.OLLAMA_MODEL

    def is_available(self) -> bool:
        """
        Vérifie si Ollama tourne et est accessible.

        Returns:
            True si Ollama répond, False sinon.
        """
        try:
            url = f"{self.host}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_models(self) -> list[str]:
        """
        Retourne la liste des modèles installés sur Ollama.

        Returns:
            Liste de noms de modèles ex: ["mistral:latest", "llama3.2"]
        """
        try:
            url = f"{self.host}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def ask(
        self,
        message: str,
        system_prompt: str = "",
        history: list[dict] = None,
        timeout: int = 120
    ) -> str:
        """
        Envoie un message à Ollama et retourne la réponse.

        Args:
            message       : Le message de l'utilisateur
            system_prompt : Instructions pour le comportement du modèle
            history       : Historique de la conversation
                            Format : [{"role": "user", "content": "..."},
                                      {"role": "assistant", "content": "..."}]
            timeout       : Secondes avant abandon (défaut : 120)

        Returns:
            La réponse du modèle en string

        Raises:
            OllamaError : Si Ollama n'est pas disponible ou renvoie une erreur
        """
        if not self.is_available():
            raise OllamaError(
                f"Ollama n'est pas accessible sur {self.host}. "
                "Vérifiez qu'Ollama est lancé."
            )

        # Construire la liste des messages
        messages = []

        # Ajouter le prompt système si fourni
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        # Ajouter l'historique si fourni
        if history:
            messages.extend(history)

        # Ajouter le message actuel
        messages.append({
            "role": "user",
            "content": message
        })

        # Construire la requête
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 1024,
                "num_ctx": 2048,
            }
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        url = f"{self.host}/api/chat"

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["message"]["content"]

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise OllamaError(
                f"Ollama a retourné une erreur {e.code} : {body}"
            )
        except urllib.error.URLError as e:
            raise OllamaError(f"Erreur de connexion à Ollama : {e}")
        except KeyError:
            raise OllamaError("Réponse inattendue d'Ollama.")
        except Exception as e:
            raise OllamaError(f"Erreur inattendue : {e}")
