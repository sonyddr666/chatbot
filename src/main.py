#!/usr/bin/env python3
"""Chatbot — Entrypoint principal (CLI interativa + API server)."""

import argparse
import asyncio
import sys


async def run_cli() -> None:
    """Modo CLI interativo."""
    from src.core.memory import ConversationMemory
    from src.core.chat import ChatEngine

    print("=" * 50)
    print("  🤖 Chatbot — modo CLI")
    print('  Digite "sair" para encerrar')
    print("=" * 50)

    memory = ConversationMemory()
    engine = ChatEngine(memory)

    while True:
        try:
            user_input = input("\n🧑 Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("sair", "quit", "exit"):
            print("\n👋 Até logo!")
            break

        print("\n🤖 Bot: ", end="", flush=True)
        async for chunk in engine.chat_stream(user_input):
            print(chunk, end="", flush=True)
        print()


def run_serve() -> None:
    """Modo API server (FastAPI)."""
    print("Iniciando servidor API...")
    import uvicorn
    from src.config import settings

    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=True,
        reload_dirs=["src"],
        reload_excludes=[
            ".venv/*",
            "venv/*",
            "frontend/node_modules/*",
            "frontend/dist/*",
            "data/*",
            "**/__pycache__/*",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Chatbot Inteligente")
    parser.add_argument(
        "mode",
        nargs="?",
        default="chat",
        choices=["chat", "serve", "ingest"],
        help="Modo de operação (default: chat)",
    )
    parser.add_argument(
        "--file", "-f",
        help="Arquivo para ingestão (modo ingest)",
    )

    args = parser.parse_args()

    if args.mode == "chat":
        asyncio.run(run_cli())
    elif args.mode == "serve":
        run_serve()
    elif args.mode == "ingest":
        print("Modo ingest — em breve!")
        # TODO: implementar ingestão de documentos (Fase 3)
        sys.exit(0)


if __name__ == "__main__":
    main()
