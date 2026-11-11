"""
core/approvals.py
=================
Actions sensibles en attente d'autorisation.

Quand une application sans écran de confirmation (API au format
standard OpenAI, raccourci du téléphone...) demande une action sensible
(commande, redémarrage d'un conteneur, écriture de fichier), Jarvis ne
l'exécute pas : il la met en attente. Le propriétaire l'autorise ou la
refuse depuis une interface (Nexus, ou toute application branchée sur
/api/approvals), puis reçoit le résultat en notification.

Une demande expire au bout de JARVIS_APPROVAL_TTL secondes (1 h).
"""

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Approval:
    id: int
    user_id: str
    action: str
    source: str
    run: Callable[[], str] = field(repr=False)
    created: float = field(default_factory=time.time)


class ApprovalCenter:
    def __init__(self, notify: Optional[Callable[[str, str], None]] = None,
                 ttl: float = 3600.0):
        """
        Args:
            notify : notify(user_id, message) — prévient du résultat
            ttl    : durée de validité d'une demande (secondes)
        """
        self.notify = notify
        self.ttl = ttl
        self._items: dict[int, Approval] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def _purge(self) -> None:
        limit = time.time() - self.ttl
        for key in [k for k, a in self._items.items() if a.created < limit]:
            del self._items[key]

    def request(self, user_id: str, action: str, run: Callable[[], str],
                source: str = "") -> Approval:
        with self._lock:
            self._purge()
            approval = Approval(next(self._ids), user_id, action, source, run)
            self._items[approval.id] = approval
        if self.notify:
            self.notify(user_id, f"Autorisation demandée (#{approval.id}) : {action}")
        return approval

    def pending(self, user_id: str) -> list[Approval]:
        with self._lock:
            self._purge()
            return [a for a in self._items.values() if a.user_id == user_id]

    def decide(self, approval_id: int, user_id: str, approved: bool) -> Optional[str]:
        """
        Autorise (exécute) ou refuse une demande.

        Returns:
            Le résultat de l'action, "refusée", ou None si la demande
            n'existe pas (ou appartient à un autre utilisateur).
        """
        with self._lock:
            self._purge()
            approval = self._items.get(approval_id)
            if approval is None or approval.user_id != user_id:
                return None
            del self._items[approval_id]
        if not approved:
            result = "Action refusée."
        else:
            try:
                result = approval.run()
            except Exception as e:  # run() ne lève normalement pas
                result = f"Erreur : {e}"
        if self.notify:
            status = "exécutée" if approved else "refusée"
            self.notify(user_id, f"Action #{approval_id} {status} : {approval.action}\n{result}")
        return result

    def deferred_confirm(self, user_id: str, source: str = "") -> Callable[[str], str]:
        """
        Fonction de confirmation qui met l'action en attente au lieu de
        l'exécuter. Le texte retourné est lu par le modèle.
        """
        def confirm(request) -> str:
            run = getattr(request, "run", None)
            if run is None:
                return "Action refusée par l'utilisateur."
            approval = self.request(user_id, str(request), run, source)
            return (
                f"Action mise en attente d'autorisation (demande #{approval.id}). "
                "Elle sera exécutée quand l'utilisateur l'aura autorisée dans Jarvis. "
                "Dis-le-lui simplement."
            )
        return confirm
