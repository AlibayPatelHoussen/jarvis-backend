"""
tools/host.py
=============
Outils fournis par une application hôte (ex. Nexus).

L'hôte publie un manifeste (nom, description, paramètres JSON Schema,
confirmation, rôles) ; Jarvis le lit et propose ces outils à son modèle,
exactement comme ses outils intégrés. Chaque appel repart vers l'hôte,
au nom de l'utilisateur, avec un secret partagé :

    GET  <JARVIS_HOST_TOOLS_URL>/manifest           → {"name", "tools": [...]}
    POST <JARVIS_HOST_TOOLS_URL>/<nom de l'outil>   ← {"arguments", "user": {"id", "role"}}
                                                    → {"result": "texte"}

C'est ainsi que Jarvis apprend seul ce qu'une application sait faire :
ajouter une action dans l'hôte suffit, rien à changer dans Jarvis.
"""

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("jarvis.host")

NAME = re.compile(r"[a-zA-Z0-9_\-]{1,64}")


class HostTools:
    """Manifeste d'un hôte, relu régulièrement, et appel de ses outils."""

    def __init__(self, base_url: str, secret: str, refresh_seconds: float = 300,
                 call_timeout: float = 180):
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self.refresh_seconds = refresh_seconds
        self.call_timeout = call_timeout
        self.name = "hôte"
        self.description = ""
        self._tools: list[dict] = []
        self._fetched_at = 0.0
        self._version = ""
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.secret)

    def _request(self, url: str, payload: Optional[dict], timeout: float) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url, data=data, method="POST" if data is not None else "GET",
            headers={"X-Jarvis-Secret": self.secret, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def refresh(self, force: bool = False) -> bool:
        """Relit le manifeste s'il est périmé. Retourne True s'il a changé."""
        if not self.configured:
            return False
        with self._lock:
            if not force and time.time() - self._fetched_at < self.refresh_seconds:
                return False
            self._fetched_at = time.time()
            try:
                manifest = self._request(f"{self.base_url}/manifest", None, timeout=10)
            except Exception as e:  # hôte arrêté : on garde les outils connus
                logger.warning(f"[Hôte] Manifeste indisponible ({self.base_url}) : {e}")
                return False
            tools = [t for t in manifest.get("tools", [])
                     if isinstance(t, dict) and NAME.fullmatch(str(t.get("name", "")))]
            version = json.dumps(tools, sort_keys=True)
            changed = version != self._version
            self._tools, self._version = tools, version
            self.name = str(manifest.get("name") or "hôte")[:40]
            self.description = str(manifest.get("description") or "")[:400]
            return changed

    @property
    def version(self) -> str:
        return self._version

    def tool_names(self) -> list[str]:
        return [t["name"] for t in self._tools]

    def register_into(self, registry: ToolRegistry, user_id: str, role: str) -> list[str]:
        """Ajoute au registre les outils de l'hôte autorisés pour ce rôle."""
        added = []
        for spec in self._tools:
            roles = spec.get("roles") or ["admin", "user"]
            if role not in roles:
                continue
            name = spec["name"]
            params = spec.get("parameters") or {"type": "object", "properties": {}, "required": []}
            registry.register(Tool(
                name=name,
                description=str(spec.get("description") or name),
                func=self._caller(name, user_id, role),
                parameters=params,
                confirm=bool(spec.get("confirm")),
            ))
            added.append(name)
        return added

    def _caller(self, name: str, user_id: str, role: str):
        def call(**arguments) -> str:
            try:
                payload = {"arguments": arguments, "user": {"id": user_id, "role": role}}
                data = self._request(f"{self.base_url}/{name}", payload,
                                     timeout=self.call_timeout)
            except urllib.error.HTTPError as e:
                try:
                    detail = json.loads(e.read().decode("utf-8")).get("error", "")
                except Exception:
                    detail = ""
                return f"Erreur de {self.name} ({e.code}) : {detail or e.reason}"
            except Exception as e:
                return f"Erreur : {self.name} ne répond pas ({e})."
            return str(data.get("result", data))
        return call

    def prompt_section(self) -> str:
        """Ce que le modèle doit savoir de l'hôte (ajouté au prompt système)."""
        if not self._tools:
            return ""
        return (
            f"Application hôte « {self.name} » : {self.description}\n"
            f"- Ses outils commencent par « {self._tools[0]['name'].split('_')[0]}_ ». "
            "Utilise-les pour tout ce qui concerne cette application.\n"
            "- Pour télécharger : cherche d'abord (…_chercher_telechargement), regarde les "
            "saisons / chapitres si besoin (…_details_telechargement), puis télécharge "
            "(…_telecharger) avec l'id exact renvoyé. Ne devine jamais un id.\n"
            "- Après un renommage ou une suppression de fichiers de médias, relance "
            "l'analyse de la bibliothèque concernée."
        )


_default: Optional[HostTools] = None
_default_lock = threading.Lock()


def default_host() -> Optional[HostTools]:
    """Hôte configuré dans .env (JARVIS_HOST_TOOLS_URL + JARVIS_HOST_SECRET), partagé."""
    global _default
    from config import settings
    if not (settings.HOST_TOOLS_URL and settings.HOST_SECRET):
        return None
    with _default_lock:
        if _default is None:
            _default = HostTools(settings.HOST_TOOLS_URL, settings.HOST_SECRET)
        return _default


def sync_host_tools(registry: ToolRegistry, host: Optional[HostTools], user_id: str, role: str,
                    previous: Optional[list[str]] = None) -> list[str]:
    """
    Remplace dans `registry` les outils de l'hôte par ceux du manifeste actuel.
    Retourne la liste des outils ajoutés (à repasser en `previous` la fois suivante).
    """
    for name in previous or []:
        registry.unregister(name)
    if host is None or not host.configured:
        return []
    host.refresh()
    return host.register_into(registry, user_id, role)
