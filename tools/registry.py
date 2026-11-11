"""
tools/registry.py
=================
Registre des outils que Jarvis peut utiliser.

Un outil = une fonction Python + une description. Le modèle (LLM) lit
les descriptions et décide lui-même quel outil appeler, avec quels
arguments ("tool calling" d'Ollama). Ajouter une capacité à Jarvis,
c'est donc simplement déclarer un nouvel outil :

    registry = ToolRegistry()

    @registry.tool()
    def convertir_euros(montant: float, devise: str = "USD") -> str:
        \"\"\"
        Convertit un montant en euros vers une autre devise.

        Args:
            montant : Montant en euros
            devise  : Code de la devise cible (USD, CAD...)
        \"\"\"
        ...

Le nom, la description et le schéma des paramètres (JSON Schema) sont
déduits de la signature et de la docstring.
"""

import inspect
import json
import logging
import re
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Type Python → type JSON Schema
_JSON_TYPES = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

# Fonction qui demande à l'utilisateur d'autoriser une action.
# Reçoit une description de l'action, retourne True si autorisée.
ConfirmCallback = Callable[[str], bool]


@dataclass
class Tool:
    """Un outil utilisable par le modèle."""
    name: str
    description: str
    func: Callable[..., Any]
    parameters: dict = field(default_factory=lambda: {
        "type": "object", "properties": {}, "required": [],
    })
    # True : l'utilisateur doit confirmer avant chaque exécution
    # (écriture de fichier, commande système...)
    confirm: bool = False

    def schema(self) -> dict:
        """Description au format attendu par Ollama (format OpenAI)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Ensemble des outils disponibles."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    # ─────────────────────────────────────────
    # Enregistrement
    # ─────────────────────────────────────────

    def register(self, tool: Tool) -> Tool:
        """Ajoute (ou remplace) un outil."""
        if not re.fullmatch(r"[a-zA-Z0-9_\-]{1,64}", tool.name):
            raise ValueError(f"Nom d'outil invalide : {tool.name!r}")
        self._tools[tool.name] = tool
        return tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[dict] = None,
        confirm: bool = False,
    ) -> Callable:
        """Décorateur : enregistre une fonction comme outil."""
        def decorator(func: Callable) -> Callable:
            self.register(tool_from_function(
                func, name=name, description=description,
                parameters=parameters, confirm=confirm,
            ))
            return func
        return decorator

    # ─────────────────────────────────────────
    # Consultation
    # ─────────────────────────────────────────

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def schemas(self) -> list[dict]:
        return [self._tools[n].schema() for n in self.names()]

    def describe(self) -> str:
        """Liste lisible des outils (pour l'aide et le prompt)."""
        lines = []
        for name in self.names():
            text = " ".join(self._tools[name].description.split())
            first_sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
            lines.append(f"- {name} : {first_sentence}")
        return "\n".join(lines)

    # ─────────────────────────────────────────
    # Exécution
    # ─────────────────────────────────────────

    def execute(
        self,
        name: str,
        arguments: Optional[dict] = None,
        confirm: Optional[ConfirmCallback] = None,
    ) -> str:
        """
        Exécute un outil et retourne son résultat sous forme de texte.

        Ne lève jamais d'exception : une erreur est retournée sous forme
        de texte pour que le modèle puisse la lire et réagir (réessayer,
        expliquer à l'utilisateur...).
        """
        tool = self._tools.get(name)
        if tool is None:
            return (
                f"Erreur : l'outil '{name}' n'existe pas. "
                f"Outils disponibles : {', '.join(self.names())}"
            )

        arguments = dict(arguments or {})
        error = _check_arguments(tool, arguments)
        if error:
            return f"Erreur : {error}"

        if tool.confirm:
            summary = f"{name}({_format_args(arguments)})"
            if confirm is None or not confirm(summary):
                return "Action refusée par l'utilisateur."

        try:
            result = tool.func(**arguments)
        except Exception as e:
            logger.warning(f"[Outil] {name} a échoué : {e}")
            return f"Erreur pendant '{name}' : {e}"

        if result is None:
            return "OK"
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(result)


# ─────────────────────────────────────────────
# Construction d'un outil depuis une fonction
# ─────────────────────────────────────────────

def tool_from_function(
    func: Callable,
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[dict] = None,
    confirm: bool = False,
) -> Tool:
    """Déduit nom, description et schéma depuis la signature et la docstring."""
    doc = inspect.getdoc(func) or ""
    summary, arg_docs = _parse_docstring(doc)
    return Tool(
        name=name or func.__name__,
        description=description or summary or func.__name__,
        func=func,
        parameters=parameters or _schema_from_signature(func, arg_docs),
        confirm=confirm,
    )


def _parse_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """
    Sépare le résumé et la section Args d'une docstring.

    Accepte "nom : description" et "nom (type): description".
    """
    summary_lines, arg_docs = [], {}
    in_args = False
    current = None
    for line in doc.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"(Args|Arguments|Paramètres|Parameters)\s*:", stripped):
            in_args = True
            continue
        if re.fullmatch(r"(Returns?|Raises|Retourne|Exemples?)\s*:", stripped):
            in_args = False
            continue
        if in_args:
            match = re.match(r"(\w+)\s*(?:\([^)]*\))?\s*:\s*(.*)", stripped)
            if match:
                current = match.group(1)
                arg_docs[current] = match.group(2).strip()
            elif stripped and current:
                arg_docs[current] += " " + stripped
        elif not arg_docs:
            summary_lines.append(line.rstrip())
    summary = "\n".join(summary_lines).strip()
    return summary, arg_docs


def _schema_from_signature(func: Callable, arg_docs: dict[str, str]) -> dict:
    try:
        hints = typing.get_type_hints(func)
    except Exception:
        hints = {}
    properties, required = {}, []
    for param in inspect.signature(func).parameters.values():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        hint = hints.get(param.name, str)
        origin = typing.get_origin(hint)
        if origin is typing.Union:  # Optional[X]
            args = [a for a in typing.get_args(hint) if a is not type(None)]
            hint = args[0] if args else str
            origin = typing.get_origin(hint)
        prop = {"type": _JSON_TYPES.get(origin or hint, "string")}
        if param.name in arg_docs:
            prop["description"] = arg_docs[param.name]
        properties[param.name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(param.name)
    return {"type": "object", "properties": properties, "required": required}


def _check_arguments(tool: Tool, arguments: dict) -> Optional[str]:
    """Vérifie les arguments obligatoires et retire les inconnus."""
    props = tool.parameters.get("properties", {})
    missing = [r for r in tool.parameters.get("required", []) if r not in arguments]
    if missing:
        return f"argument(s) manquant(s) pour '{tool.name}' : {', '.join(missing)}"
    # Les petits modèles inventent parfois des arguments : on les ignore
    # plutôt que de faire échouer l'appel.
    if props:
        for key in list(arguments):
            if key not in props:
                arguments.pop(key)
    # Conversion douce des types simples ("3" → 3)
    for key, value in arguments.items():
        expected = props.get(key, {}).get("type")
        try:
            if expected == "integer" and isinstance(value, str):
                arguments[key] = int(value)
            elif expected == "number" and isinstance(value, str):
                arguments[key] = float(value.replace(",", "."))
            elif expected == "boolean" and isinstance(value, str):
                arguments[key] = value.lower() in ("true", "oui", "yes", "1")
            elif expected == "string" and not isinstance(value, str):
                arguments[key] = str(value)
        except ValueError:
            return f"l'argument '{key}' doit être de type {expected}"
    return None


def _format_args(arguments: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in arguments.items())
