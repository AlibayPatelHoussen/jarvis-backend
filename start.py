"""
start.py
========
Point d'entrée unique de Jarvis.

    python start.py                       → conversation dans le terminal
    python start.py --server              → serveur (API, sans interface)
    python start.py cles liste            → applications autorisées
    python start.py cles ajouter NOM      → nouvelle clé d'application
    python start.py cles supprimer NOM    → retirer une application
"""

import argparse


def manage_keys(args) -> int:
    """Gestion des clés d'application (voir core/clients.py)."""
    from config import settings
    from core.clients import ClientStore

    store = ClientStore(settings.DATA_DIR / "clients.db")
    if args.action == "liste":
        apps = store.list()
        if not apps:
            print("Aucune application. Ajoutez-en une : python start.py cles ajouter telephone")
        for app in apps:
            trust = ", confiance" if app.trusted else ""
            used = app.last_used or "jamais"
            print(f"- {app.name} : rôle {app.role}, utilisateur {app.user}{trust} "
                  f"(créée {app.created_at}, dernière utilisation : {used})")
        return 0

    if not args.nom:
        print("Précisez le nom de l'application.")
        return 1

    if args.action == "ajouter":
        try:
            key = store.add(args.nom, role=args.role, user=args.utilisateur,
                            trusted=args.confiance)
        except ValueError as e:
            print(f"Erreur : {e}")
            return 1
        print(f"Application « {args.nom.lower()} » ajoutée (rôle {args.role}).")
        print("\nClé (affichée une seule fois, gardez-la secrète) :\n")
        print(f"    {key}\n")
        print("À utiliser dans l'en-tête : Authorization: Bearer <clé>")
        print("Application au format standard « OpenAI » (sans compte OpenAI) : "
              "adresse https://<jarvis>/v1, modèle « jarvis ».")
        print("Prise en compte immédiate, sans redémarrer Jarvis.")
        return 0

    if store.remove(args.nom):
        print(f"Application « {args.nom.lower()} » supprimée : sa clé ne fonctionne plus.")
        return 0
    print(f"Application « {args.nom} » introuvable.")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis — assistant IA personnel")
    parser.add_argument("--server", action="store_true",
                        help="lancer le serveur (API HTTP, sans interface)")
    parser.add_argument("--host", help="adresse d'écoute (défaut : JARVIS_HOST)")
    parser.add_argument("--port", type=int, help="port (défaut : JARVIS_PORT)")
    sub = parser.add_subparsers(dest="commande")
    keys = sub.add_parser("cles", help="gérer les clés d'application")
    keys.add_argument("action", choices=["liste", "ajouter", "supprimer"])
    keys.add_argument("nom", nargs="?", help="nom de l'application (ex. telephone, nexus)")
    keys.add_argument("--role", choices=["admin", "user"], default="admin",
                      help="rôle maximal de la clé (défaut : admin)")
    keys.add_argument("--utilisateur", default="owner",
                      help="utilisateur dont la clé utilise les données (défaut : owner)")
    keys.add_argument("--confiance", action="store_true",
                      help="l'application peut parler au nom de ses utilisateurs "
                           "(en-tête X-Jarvis-User), ex. Nexus")
    args = parser.parse_args(argv)

    if args.commande == "cles":
        return manage_keys(args)
    if args.server:
        from api.server import run
        run(host=args.host, port=args.port)
    else:
        from interface.cli import run
        run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
