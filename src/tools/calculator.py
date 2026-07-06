"""Ferramenta de calculadora (exemplo de function calling)."""

import math
import re
from typing import Optional


def calculate(expression: str) -> Optional[str]:
    """Avalia uma expressão matemática de forma segura."""
    # Remove caracteres não permitidos
    cleaned = re.sub(r"[^0-9+\-*/().% ]", "", expression)
    if not cleaned:
        return None

    # Lista de funções matemáticas seguras
    safe_globals = {
        "__builtins__": {},
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        "math": math,
    }

    try:
        result = eval(cleaned, safe_globals)
        return f"O resultado de `{expression}` é **{result}**"
    except Exception as e:
        return f"Erro ao calcular: {e}"


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Executa uma operação matemática",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Expressão matemática (ex: 2 + 2, sqrt(16))",
                }
            },
            "required": ["expression"],
        },
    },
}
