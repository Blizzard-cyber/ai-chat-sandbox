from __future__ import annotations

import ast
import operator
from typing import Any, TYPE_CHECKING

from .base import Tool

if TYPE_CHECKING:
    from .base import ToolRegistry


class CalculateTool(Tool):
    """安全的数学表达式计算工具。"""

    def __init__(self):
        super().__init__(
            name="calculate",
            description="计算数学表达式。支持 +, -, *, /, **, %, // 及常见数学函数。",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要计算的数学表达式，如 '2 + 3 * 4' 或 'sqrt(16) + log(100)'",
                    }
                },
                "required": ["expression"],
            },
        )

    async def execute(self, expression: str, **kwargs: Any) -> str:
        return _safe_eval(expression)


_SAFE_NODES: set[type] = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.USub, ast.UAdd,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.Constant,
    ast.Call, ast.Name, ast.Load,
}

_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs, "round": round, "min": min, "max": max,
    "int": int, "float": float, "str": str, "bool": bool,
    "len": len, "sum": sum, "pow": pow, "divmod": divmod,
}

_OPERATORS: dict[type, Any] = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _safe_eval(expr: str) -> str:
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        return f"表达式语法错误：{e}"

    try:
        result = _eval_node(tree.body)
        return str(result)
    except Exception as e:
        return f"计算出错：{e}"


def _eval_node(node: ast.AST) -> Any:
    node_type = type(node)

    if node_type not in _SAFE_NODES:
        raise ValueError(f"不支持的语法节点：{node_type.__name__}")

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op_type = type(node.op)
        if op_type in _OPERATORS:
            return _OPERATORS[op_type](left, right)
        raise ValueError(f"不支持的运算符：{op_type.__name__}")

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        op_type = type(node.op)
        if op_type in _OPERATORS:
            return _OPERATORS[op_type](operand)
        raise ValueError(f"不支持的一元运算符：{op_type.__name__}")

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_BUILTINS:
            func = _SAFE_BUILTINS[node.func.id]
            args = [_eval_node(arg) for arg in node.args]
            return func(*args)
        raise ValueError(f"不允许调用的函数：{ast.dump(node.func)}")

    if isinstance(node, ast.Name):
        raise ValueError(f"不允许使用变量：{node.id}")

    raise ValueError(f"不支持的表达式类型：{node_type.__name__}")


def register_builtin_tools(registry: "ToolRegistry") -> None:
    registry.register(CalculateTool())
