from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from .base import BaseLLM, LLMResponse, StreamChunk, ToolCall


class OpenAILLM(BaseLLM):
    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        super().__init__(model)
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**kwargs)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        openai_tools = _to_openai_tools(tools) if tools else None

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=openai_tools or None,
        )

        return _parse_response(response)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncGenerator[StreamChunk | LLMResponse, None]:
        openai_tools = _to_openai_tools(tools) if tools else None

        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=openai_tools or None,
            stream=True,
        )

        text_content = ""
        reasoning_content = ""
        tool_calls_acc: dict[int, dict[str, Any]] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            rc = getattr(delta, "reasoning_content", None) or ""
            if rc:
                reasoning_content += rc
                yield StreamChunk(type="reasoning", content=rc)

            if delta.content:
                text_content += delta.content
                yield StreamChunk(type="text", content=delta.content)

            tc_list = getattr(delta, "tool_calls", None)
            if tc_list:
                for tc in tc_list:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {"id": tc.id or "", "name": "", "arguments": ""}
                    if tc.id:
                        tool_calls_acc[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments

        if tool_calls_acc:
            tool_calls = []
            for idx in sorted(tool_calls_acc.keys()):
                tc = tool_calls_acc[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], arguments=args))
            yield LLMResponse(type="tool_calls", tool_calls=tool_calls, reasoning_content=reasoning_content)
        else:
            yield LLMResponse(type="text", text=text_content, reasoning_content=reasoning_content)

    def format_assistant_tool_calls(
        self, tool_calls: list[tuple[Any, str]], reasoning_content: str = ""
    ) -> dict[str, Any]:
        openai_tool_calls = []
        for tc, _result in tool_calls:
            openai_tool_calls.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            })
        msg: dict[str, Any] = {"role": "assistant", "content": None, "tool_calls": openai_tool_calls}
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        return msg

    def format_tool_result(
        self, tool_call_id: str, tool_name: str, result: str
    ) -> dict[str, Any]:
        return {"role": "tool", "content": result, "tool_call_id": tool_call_id}

    def inject_system_prompt(
        self, messages: list[dict[str, Any]], system_prompt: str
    ) -> None:
        for m in messages:
            if m["role"] == "system":
                return
        messages.insert(0, {"role": "system", "content": system_prompt})


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for t in tools:
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        })
    return result


def _parse_response(response: Any) -> LLMResponse:
    choice = response.choices[0]
    message = choice.message

    reasoning = getattr(message, "reasoning_content", "") or ""
    tc_list = getattr(message, "tool_calls", None)

    if tc_list:
        tool_calls = []
        for tc in tc_list:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return LLMResponse(type="tool_calls", tool_calls=tool_calls, reasoning_content=reasoning)

    return LLMResponse(type="text", text=message.content or "", reasoning_content=reasoning)
