"""Authoritative definitions for safe, user-enabled chatbot skills."""

from __future__ import annotations

from typing import Any


DEFAULT_SKILLS: tuple[dict[str, Any], ...] = (
    {
        "name": "perplexo_search",
        "description": "Pesquisa atual, profunda ou academica com respostas completas e fontes pelo Perplexo.",
        "kind": "external_research",
        "definition": {
            "inputs": {"query": "string"},
            "permissions": {
                "network": True,
                "workspace_read": False,
                "workspace_write": False,
                "shell": False,
            },
            "default_enabled": False,
            "executor": "perplexo_search",
            "endpoint": "/search",
            "modes": ["web", "deep-research", "academic"],
            "fallback": "web_search",
            "examples": [
                "pesquise as noticias mais recentes sobre inteligencia artificial",
                "faca uma pesquisa profunda sobre agentes autonomos",
            ],
        },
        "requires_network": True,
        "requires_shell": False,
        "risk_level": 1,
    },
    {
        "name": "simple_search",
        "description": "Pesquisa web simples e entrega resultados com fontes.",
        "kind": "external_search",
        "definition": {
            "inputs": {"query": "string"},
            "permissions": {
                "network": True,
                "workspace_read": False,
                "workspace_write": False,
                "shell": False,
            },
            "executor": "web_search",
            "examples": ["pesquise noticias sobre energia solar"],
        },
        "requires_network": True,
        "requires_shell": False,
        "risk_level": 1,
    },
    {
        "name": "search_and_answer",
        "description": "Pesquisa na web, prepara contexto com fontes e deixa o chat responder.",
        "kind": "workflow",
        "definition": {
            "inputs": {"query": "string"},
            "permissions": {
                "network": True,
                "workspace_read": False,
                "workspace_write": False,
                "shell": False,
            },
            "steps": ["query", "web_search", "answer_with_sources"],
            "executor": "web_search",
            "examples": ["pesquise e explique o que mudou em Python"],
        },
        "requires_network": True,
        "requires_shell": False,
        "risk_level": 2,
    },
    {
        "name": "personal_rag",
        "description": "Consulta a base de conhecimento pessoal antes de responder.",
        "kind": "internal_tool",
        "definition": {
            "inputs": {"query": "string"},
            "permissions": {
                "network": False,
                "workspace_read": False,
                "workspace_write": False,
                "shell": False,
            },
            "collection": "per_user",
            "examples": ["ative para consultar meus documentos em todas as perguntas"],
        },
        "requires_network": False,
        "requires_shell": False,
        "risk_level": 1,
    },
    {
        "name": "workspace_manager",
        "description": "Planeja e executa gerenciamento completo do workspace somente apos confirmacao do usuario.",
        "kind": "workspace_agent",
        "definition": {
            "inputs": {"instruction": "string"},
            "permissions": {
                "network": False,
                "workspace_read": True,
                "workspace_write": True,
                "shell": False,
            },
            "default_enabled": True,
            "confirmation_required": True,
            "actions": ["mkdir", "write_file", "move", "delete"],
            "examples": ["crie uma pasta projeto e um README.md sobre mim"],
        },
        "requires_network": False,
        "requires_shell": False,
        "risk_level": 2,
    },
    {
        "name": "workspace_read",
        "description": "Le um arquivo somente do workspace do usuario quando o comando explicito for usado.",
        "kind": "workspace_read",
        "definition": {
            "inputs": {"path": "string"},
            "permissions": {
                "network": False,
                "workspace_read": True,
                "workspace_write": False,
                "shell": False,
            },
            "command": "@workspace:read caminho/do/arquivo.md",
            "examples": ["@workspace:read notas/projeto.md"],
        },
        "requires_network": False,
        "requires_shell": False,
        "risk_level": 1,
    },
    {
        "name": "workspace_write_preview",
        "description": "Gera apenas um preview de diff para um arquivo do workspace; nunca aplica a alteracao.",
        "kind": "workspace_write_preview",
        "definition": {
            "inputs": {"path": "string", "content": "string"},
            "permissions": {
                "network": False,
                "workspace_read": True,
                "workspace_write": True,
                "shell": False,
            },
            "command": "@workspace:preview caminho/do/arquivo.md\\n---\\nnovo conteudo",
            "examples": ["@workspace:preview notas/projeto.md\\n---\\nNovo conteudo"],
        },
        "requires_network": False,
        "requires_shell": False,
        "risk_level": 2,
    },
)


def get_skill_definition(name: str) -> dict[str, Any] | None:
    """Return a copy so callers cannot mutate the registry in memory."""
    for skill in DEFAULT_SKILLS:
        if skill["name"] == name:
            return {
                **skill,
                "definition": dict(skill["definition"]),
            }
    return None
