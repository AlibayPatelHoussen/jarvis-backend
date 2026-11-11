"""
tests/test_approvals.py
=======================
Tests unitaires pour core/approvals.py et ConfirmRequest
"""

from core.approvals import ApprovalCenter
from tools.registry import ConfirmRequest, ToolRegistry


def make_registry(done):
    reg = ToolRegistry()

    @reg.tool(confirm=True)
    def redemarrer(nom: str) -> str:
        """Redémarre un service."""
        done.append(nom)
        return f"{nom} redémarré"

    return reg


def test_confirm_request_is_a_string_with_payload():
    seen = []
    reg = make_registry([])
    reg.execute("redemarrer", {"nom": "jellyfin"}, confirm=lambda r: seen.append(r) or False)
    request = seen[0]
    assert isinstance(request, ConfirmRequest) and isinstance(request, str)
    assert request == "redemarrer(nom='jellyfin')"
    assert request.tool == "redemarrer" and request.arguments == {"nom": "jellyfin"}


def test_confirm_can_return_a_message():
    done = []
    reg = make_registry(done)
    assert reg.execute("redemarrer", {"nom": "a"}, confirm=lambda r: "En attente") == "En attente"
    assert done == []
    assert reg.execute("redemarrer", {"nom": "a"}, confirm=lambda r: 1) \
        == "Action refusée par l'utilisateur."


def test_deferred_then_approved():
    done, notes = [], []
    center = ApprovalCenter(notify=lambda user, msg: notes.append((user, msg)))
    reg = make_registry(done)
    result = reg.execute("redemarrer", {"nom": "jellyfin"},
                         confirm=center.deferred_confirm("owner", source="telephone"))
    assert "mise en attente" in result and "#1" in result
    assert done == []
    pending = center.pending("owner")
    assert [(a.id, a.action, a.source) for a in pending] == \
        [(1, "redemarrer(nom='jellyfin')", "telephone")]
    assert center.pending("alice") == []
    assert center.decide(1, "alice", True) is None  # pas à elle
    assert center.decide(1, "owner", True) == "jellyfin redémarré"
    assert done == ["jellyfin"]
    assert center.decide(1, "owner", True) is None  # déjà traitée
    assert notes[0] == ("owner", "Autorisation demandée (#1) : redemarrer(nom='jellyfin')")
    assert notes[1][1].startswith("Action #1 exécutée") and "jellyfin redémarré" in notes[1][1]


def test_refused_and_expired():
    done = []
    center = ApprovalCenter(ttl=60)
    reg = make_registry(done)
    reg.execute("redemarrer", {"nom": "a"}, confirm=center.deferred_confirm("owner"))
    assert center.decide(1, "owner", False) == "Action refusée."
    reg.execute("redemarrer", {"nom": "b"}, confirm=center.deferred_confirm("owner"))
    center._items[2].created -= 120
    assert center.pending("owner") == []
    assert center.decide(2, "owner", True) is None
    assert done == []


def test_deferred_confirm_without_payload_refuses():
    center = ApprovalCenter()
    assert center.deferred_confirm("owner")("texte simple") == "Action refusée par l'utilisateur."
    assert center.pending("owner") == []
