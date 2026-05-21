from __future__ import annotations

from typing import Any, AsyncGenerator

from anthropic import AsyncAnthropic

from .base import BaseLLM, LLMResponse, StreamChunk, ToolCall


class AnthropicLLM(BaseLLM):
    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        super().__init__(model)
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncAnthropic(**kwargs)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        system = _extract_system(messages)
        formatted = self._format_messages(messages)
        anthropic_tools = _to_anthropic_tools(tools) if tools else None

        response = await self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=formatted,
            tools=anthropic_tools or None,
        )

        return _parse_response(response)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncGenerator[StreamChunk | LLMResponse, None]:
        system = _extract_system(messages)
        formatted = self._format_messages(messages)
        anthropic_tools = _to_anthropic_tools(tools) if tools else None

        async with self._client.messages.stream(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=formatted,
            tools=anthropic_tools or None,
        ) as stream:
            text_content = ""

            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        text_content += event.delta.text
                        yield StreamChunk(type="text", content=event.delta.text)

            final = await stream.get_final_message()

        tool_calls = []
        for block in final.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))

        if tool_calls:
            yield LLMResponse(type="tool_calls", tool_calls=tool_calls)
        else:
            yield LLMResponse(type="text", text=text_content)

    def format_assistant_tool_calls(
        self, tool_calls: list[tuple[Any, str]], reasoning_content: str = ""
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        for tc, _result in tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.arguments,
            })
        return {"role": "assistant", "content": content}

    def format_tool_result(
        self, tool_call_id: str, tool_name: str, result: str
    ) -> dict[str, Any]:
        return {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": result,
            }],
        }

    def inject_system_prompt(
        self, messages: list[dict[str, Any]], system_prompt: str
    ) -> None:
        messages.insert(0, {"role": "system", "content": system_prompt})

    def _format_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [m for m in messages if m["role"] != "system"]


def _extract_system(messages: list[dict[str, Any]]) -> str:
    for msg in messages:
        if msg["role"] == "system":
            return msg["content"]
    return ""


def _to_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in tools
    ]


def _parse_response(response: Any) -> LLMResponse:
    tool_calls = []
    for block in response.content:
        if block.type == "tool_use":
            tool_calls.append(ToolCall(
                id=block.id,
                name=block.name,
                arguments=block.input if isinstance(block.input, dict) else {},
            ))
    if tool_calls:
        return LLMResponse(type="tool_calls", tool_calls=tool_calls)

    text = "".join(block.text for block in response.content if block.type == "text")
    return LLMResponse(type="text", text=text)
