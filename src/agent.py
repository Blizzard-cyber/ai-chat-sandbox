from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from .config import config
from .llm.base import BaseLLM, LLMResponse, StreamChunk
from .llm.anthropic_llm import AnthropicLLM
from .llm.openai_llm import OpenAILLM
from .session import Session
from .tools.base import ToolRegistry
from .tools.builtin import register_builtin_tools
from .tools.sandbox import register_sandbox_tools

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10

SYSTEM_PROMPT = """你是一个有用的 AI 助手。你可以进行普通对话，也可以在需要时使用工具来完成用户的任务。

## 工具使用规则

当你需要使用工具时，请遵循以下规则：

1. **逐步执行**：一次只调用必要的工具，根据上一步结果决定下一步
2. **先获取信息**：操作浏览器前，先使用 browser_get_clickable_elements 或 browser_get_text 了解页面状态
3. **及时停止**：以下情况必须停止调用工具，直接回复用户：
   - 用户的问题已经得到完整回答
   - 同一工具连续 2 次返回错误或相同结果
   - 已经获取了足够的信息来回答用户问题
   - 已经完成了用户要求的操作（如截图、导航、填表等）
4. **截图展示**：当用户要求查看页面时，使用 browser_screenshot 截图
5. **避免循环**：如果你发现自己在重复同样的操作，立即停止并用文字说明当前情况
6. **直接回答**：对于不需要浏览器的常识性问题，直接回复文本，不要调用工具

## 图片显示

当截图工具返回 [IMAGE] 前缀的数据时，请在你的回复中保留 [IMAGE]data:image/png;base64,... 标记来展示图片。

当前可用的沙箱工具可以帮你操作浏览器、执行命令、读写文件、运行代码等。"""


def create_llm() -> BaseLLM:
    if config.llm_provider == "openai":
        return OpenAILLM(
            model=config.openai_model,
            api_key=config.openai_api_key,
            base_url=config.openai_base_url or None,
        )
    else:
        return AnthropicLLM(
            model=config.anthropic_model,
            api_key=config.anthropic_api_key,
        )


def create_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    if config.sandbox_enabled:
        register_sandbox_tools(registry, config.sandbox_base_url)
    return registry


# ------------------------------------------------------------------
# global cancel registry  (per-session cancel events)
# ------------------------------------------------------------------

_cancel_events: dict[str, asyncio.Event] = {}


def get_cancel_event(session_id: str) -> asyncio.Event:
    if session_id not in _cancel_events:
        _cancel_events[session_id] = asyncio.Event()
    return _cancel_events[session_id]


def cancel_session(session_id: str) -> bool:
    evt = _cancel_events.get(session_id)
    if evt and not evt.is_set():
        evt.set()
        return True
    return False


def cleanup_cancel_event(session_id: str) -> None:
    _cancel_events.pop(session_id, None)


# ------------------------------------------------------------------
# agent loop
# ------------------------------------------------------------------


async def agent_loop(
    session: Session,
    user_message: str,
    llm: BaseLLM | None = None,
    registry: ToolRegistry | None = None,
    cancel_event: asyncio.Event | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    if llm is None:
        llm = create_llm()
    if registry is None:
        registry = create_tool_registry()

    session.add_message("user", user_message)
    llm.inject_system_prompt(session.messages, SYSTEM_PROMPT)

    tool_schemas = registry.get_schemas()

    # Track tool calls for loop detection
    recent_tool_calls: list[tuple[str, str]] = []  # (name, args_str)

    for iteration in range(MAX_ITERATIONS):
        # --- check cancellation ---
        if cancel_event and cancel_event.is_set():
            yield {"type": "error", "message": "用户取消了执行"}
            return

        # --- Phase: analyzing ---
        yield {"type": "phase", "phase": "analyzing", "iteration": iteration + 1,
               "label": f"第 {iteration + 1} 轮：分析需求" if iteration == 0 else f"第 {iteration + 1} 轮：分析结果，规划下一步"}
        yield {"type": "thinking_start"}
        full_text = ""
        response: LLMResponse | None = None

        try:
            stream = llm.chat_stream(session.messages, tool_schemas)
            async for chunk in stream:
                # Check cancellation during streaming
                if cancel_event and cancel_event.is_set():
                    yield {"type": "thinking_end"}
                    yield {"type": "error", "message": "用户取消了执行"}
                    return

                if isinstance(chunk, StreamChunk):
                    if chunk.type == "reasoning":
                        yield {"type": "thinking", "content": chunk.content}
                    else:
                        full_text += chunk.content
                        yield {"type": "text", "content": chunk.content}
                elif isinstance(chunk, LLMResponse):
                    response = chunk
        except Exception as e:
            logger.exception("LLM call failed on iteration %d", iteration)
            yield {"type": "thinking_end"}
            yield {"type": "error", "message": f"LLM 调用失败：{e}"}
            return

        yield {"type": "thinking_end"}

        # Check cancellation again
        if cancel_event and cancel_event.is_set():
            yield {"type": "error", "message": "用户取消了执行"}
            return

        if response is None:
            yield {"type": "error", "message": "LLM 未返回有效响应"}
            return

        # --- Phase: responding (final answer) ---
        if response.type == "text":
            yield {"type": "phase", "phase": "responding", "label": "生成回复"}
            text = response.text or ""
            if "[IMAGE]" in text:
                parts = text.split("[IMAGE]")
                for i, part in enumerate(parts):
                    if i == 0:
                        if part.strip():
                            yield {"type": "text", "content": part}
                    else:
                        img_data = part.split()[0] if part.strip() else ""
                        img_data = img_data.strip()
                        if img_data.startswith("data:image/"):
                            yield {"type": "image", "src": img_data}
                        rest = part[len(img_data):].strip()
                        if rest:
                            yield {"type": "text", "content": rest}
            elif full_text.strip():
                if not full_text.strip():
                    yield {"type": "text", "content": text}

            session.add_message("assistant", text, reasoning_content=response.reasoning_content)
            return

        # --- Phase: executing (calling tools) ---
        if response.type == "tool_calls" and response.tool_calls:
            tool_names = [tc.name for tc in response.tool_calls]
            yield {"type": "phase", "phase": "executing", "iteration": iteration + 1,
                   "tools": tool_names, "count": len(tool_names),
                   "label": f"第 {iteration + 1} 轮：调用 {', '.join(tool_names)}"}

            # -------- loop detection --------
            call_sig = (",".join(tool_names), json.dumps([tc.arguments for tc in response.tool_calls], sort_keys=True))
            recent_tool_calls.append(call_sig)
            if len(recent_tool_calls) > 6:
                recent_tool_calls = recent_tool_calls[-6:]

            # Check if the same call pattern repeated 3+ times in the last 4 calls
            if len(recent_tool_calls) >= 4:
                last4 = recent_tool_calls[-4:]
                if last4.count(last4[-1]) >= 3:
                    yield {"type": "error",
                           "message": "检测到重复的工具调用模式。Agent 已停止执行以避免死循环。请简化你的请求或换个方式提问。"}
                    return
            # --------------------------------------------------

            tool_results: list[tuple[Any, str]] = []
            for tc in response.tool_calls:
                # Check cancellation before each tool
                if cancel_event and cancel_event.is_set():
                    yield {"type": "error", "message": "用户取消了执行"}
                    return

                # Emit browser action for frontend preview panel
                if tc.name.startswith("browser_"):
                    action = tc.name.replace("browser_", "")
                    evt: dict[str, Any] = {"type": "browser_action", "action": action}
                    if action == "navigate":
                        evt["url"] = tc.arguments.get("url", "")
                    elif action == "click":
                        evt["selector"] = tc.arguments.get("selector", "") or f"index={tc.arguments.get('index', '')}"
                    elif action == "fill":
                        evt["selector"] = tc.arguments.get("selector", "") or f"index={tc.arguments.get('index', '')}"
                        evt["text"] = tc.arguments.get("value", "") or tc.arguments.get("text", "")
                    elif action == "scroll":
                        evt["direction"] = tc.arguments.get("direction", "")
                    yield evt

                yield {"type": "tool_start", "tool": tc.name, "args": tc.arguments}

                try:
                    result = await registry.execute(tc.name, **tc.arguments)
                except Exception as e:
                    result = f"工具执行异常：{e}"
                    logger.exception("Tool execution failed: %s", tc.name)

                tool_results.append((tc, result))

                if result.startswith("[IMAGE]"):
                    img_src = result[7:]
                    yield {"type": "image", "src": img_src}
                    result_summary = "[截图已获取]"
                elif result.startswith("[ERROR]"):
                    result_summary = result[:200] + ("..." if len(result) > 200 else "")
                else:
                    result_summary = result[:200] + ("..." if len(result) > 200 else "")

                yield {"type": "tool_end", "tool": tc.name, "result": result_summary}

            # Brief observing phase marker
            yield {"type": "phase", "phase": "observing", "iteration": iteration + 1,
                   "label": f"第 {iteration + 1} 轮：分析工具执行结果"}

            # Check cancellation before feeding results back
            if cancel_event and cancel_event.is_set():
                yield {"type": "error", "message": "用户取消了执行"}
                return

            session.messages.append(
                llm.format_assistant_tool_calls(tool_results, reasoning_content=response.reasoning_content)
            )
            for tc, result in tool_results:
                session.messages.append(
                    llm.format_tool_result(tc.id, tc.name, result)
                )

    yield {"type": "error", "message": f"Agent 执行超过 {MAX_ITERATIONS} 轮，已中止。请简化你的请求。"}
