"""Small provider-neutral contracts used by the agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    permission: str = ""
    confirmation_required: bool = False
    risk_level: int = 1
    # Tempo limite de execucao do handler; exceder vira ToolResult failed.
    timeout_seconds: float = 60.0
    # Categoria para orcamento de uso por turno ("" = fallback legado por nome).
    category: str = ""
    # Acao terminal: executa por ultimo, em lote proprio, e encerra o plano.
    terminal: bool = False
    # Ferramentas cujos resultados devem existir antes desta executar.
    depends_on: tuple[str, ...] = ()

    def as_model_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    name: str
    status: str
    content: str
    attachments: list[dict[str, Any]] = field(default_factory=list)
    activity: dict[str, Any] | None = None
    data: dict[str, Any] = field(default_factory=dict)
    audit_recorded: bool = False
    error: str = ""

    def model_payload(self, max_chars: int | None = None) -> dict[str, Any]:
        """Payload serializado para eventos e para o contexto do modelo.

        ``max_chars`` trunca apenas ``content`` (com marcador explicito) e deve
        ser usado somente nos destinos de modelo (model_context, prior_results);
        eventos de UI recebem o conteudo integral com max_chars=None.
        """
        def attachment_value(item: Any, key: str, fallback: str = "") -> Any:
            if isinstance(item, dict):
                return item.get(key) or (item.get(fallback) if fallback else None)
            return getattr(item, key, None) or (getattr(item, fallback, None) if fallback else None)

        content = self.content
        if max_chars is not None and len(content) > max_chars:
            content = content[:max_chars] + "\n\n...[truncado]"
        return {
            "tool_call_id": self.call_id,
            "name": self.name,
            "status": self.status,
            "content": content,
            "attachments": [
                {
                    "filename": attachment_value(item, "filename"),
                    "relative_path": attachment_value(item, "relative_path", "path"),
                    "content_type": attachment_value(item, "content_type"),
                }
                for item in self.attachments
            ],
            "data": self.data,
            "error": self.error,
        }


ToolHandler = Callable[[Any, dict[str, Any]], Awaitable[ToolResult]]


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler
