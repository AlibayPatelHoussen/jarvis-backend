"""
core/toolset.py
===============
Construction de la boîte à outils de Jarvis selon le rôle de
l'utilisateur.

Mêmes règles que Nexus : le terminal, les fichiers, Docker et les
services sont réservés aux administrateurs. Un utilisateur simple
garde la conversation, la mémoire, les tâches, le web et l'état
général du serveur.
"""

from core.environment import Environment
from tools.builtin import register_builtin_tools
from tools.files import Workspace, register_file_tools
from tools.registry import ToolRegistry
from tools.system import register_system_tools
from tools.tasks import register_task_tools
from tools.web import register_web_tools

ROLES = ("admin", "user")

# Outils système accessibles à un utilisateur non administrateur
USER_SYSTEM_TOOLS = {"infos_systeme", "espace_disque"}


def build_tools(
    long_term,
    tasks,
    environment: Environment,
    role: str = "admin",
    command_timeout: int = 30,
    allow_commands: bool = True,
) -> ToolRegistry:
    """Outils autorisés pour ce rôle."""
    tools = register_builtin_tools(ToolRegistry(), long_term)
    register_task_tools(tools, tasks)
    register_web_tools(tools)

    system = register_system_tools(
        ToolRegistry(), environment,
        command_timeout=command_timeout,
        allow_commands=allow_commands and role == "admin",
    )
    for name in system.names():
        if role == "admin" or name in USER_SYSTEM_TOOLS:
            tools.register(system.get(name))

    if role == "admin":
        register_file_tools(tools, Workspace(environment.workspace))
    return tools
