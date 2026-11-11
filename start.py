"""
start.py
========
Point d'entrée unique de Jarvis.

    python start.py              → conversation dans le terminal
    python start.py --server     → serveur (API + page web)
"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis — assistant IA personnel")
    parser.add_argument("--server", action="store_true",
                        help="lancer le serveur (API + page de chat web)")
    parser.add_argument("--host", help="adresse d'écoute (défaut : JARVIS_HOST)")
    parser.add_argument("--port", type=int, help="port (défaut : JARVIS_PORT)")
    args = parser.parse_args()

    if args.server:
        from api.server import run
        run(host=args.host, port=args.port)
    else:
        from interface.cli import run
        run()


if __name__ == "__main__":
    main()
