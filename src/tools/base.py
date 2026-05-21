from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    def __init__(self, name: str, description: str, parameters: dict[str, Any]):
        self.name = name
        self.description = description
        self.parameters = parameters

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        ...

    def to_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def register_many(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def get_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]

    def get_names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, name: str, **kwargs: Any) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"错误：未找到工具 '{name}'。可用工具：{', '.join(self.get_names())}"
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            return f"工具 '{name}' 执行失败：{type(e).__name__}: {e}"
