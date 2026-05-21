from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class StreamChunk:
    type: Literal["text", "reasoning"]
    content: str


@dataclass
class LLMResponse:
    type: Literal["text", "tool_calls"]
    text: str | None = None
    tool_calls: list[ToolCall] | None = None
    reasoning_content: str = ""


class BaseLLM(ABC):
    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncGenerator[StreamChunk | LLMResponse, None]:
        ...

    def format_assistant_tool_calls(
        self, tool_calls: list[tuple[Any, str]], reasoning_content: str = ""
    ) -> dict[str, Any]:
        """构建包含工具调用的 assistant 消息。"""
        raise NotImplementedError

    def format_tool_result(
        self, tool_call_id: str, tool_name: str, result: str
    ) -> dict[str, Any]:
        """构建工具执行结果消息。"""
        raise NotImplementedError

    def inject_system_prompt(
        self, messages: list[dict[str, Any]], system_prompt: str
    ) -> None:
        """将 system prompt 注入消息列表（各 provider 位置不同）。"""
        raise NotImplementedError
