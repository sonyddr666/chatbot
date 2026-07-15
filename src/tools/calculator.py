"""Bounded arithmetic evaluator for the agent runtime."""

from __future__ import annotations

import ast
import math
import operator


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {
    "abs": abs,
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
    "sqrt": math.sqrt,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}


def _evaluate(node: ast.AST, depth: int = 0) -> int | float:
    if depth > 20:
        raise ValueError("Expressao complexa demais")
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, depth + 1)
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        if abs(node.value) > 1e100:
            raise ValueError("Numero grande demais")
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate(node.left, depth + 1)
        right = _evaluate(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e20):
            raise ValueError("Potencia grande demais")
        value = _BINARY_OPERATORS[type(node.op)](left, right)
        if isinstance(value, (int, float)) and abs(value) > 1e100:
            raise ValueError("Resultado grande demais")
        return value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS:
        if node.keywords or len(node.args) > 2:
            raise ValueError("Argumentos invalidos")
        return _FUNCTIONS[node.func.id](*[_evaluate(arg, depth + 1) for arg in node.args])
    raise ValueError("Operacao nao permitida")


def calculate(expression: str) -> str:
    """Evaluate arithmetic without eval, attribute access, imports or comprehensions."""
    cleaned = (expression or "").strip()
    if not cleaned:
        raise ValueError("Expressao nao pode ser vazia")
    if len(cleaned) > 200:
        raise ValueError("Expressao grande demais")
    try:
        tree = ast.parse(cleaned, mode="eval")
        result = _evaluate(tree)
    except (SyntaxError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"Expressao invalida: {exc}") from exc
    return f"O resultado de `{cleaned}` e **{result}**"


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Executa uma operacao matematica segura",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Expressao matematica, por exemplo 2 + 2 ou sqrt(16)",
                }
            },
            "required": ["expression"],
        },
    },
}
