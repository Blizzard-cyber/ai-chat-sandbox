from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
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

# ------------------------------------------------------------------
# Agent configuration
# ------------------------------------------------------------------

SOFT_LIMIT = 15         # Normal max iterations — extend for complex tasks
HARD_LIMIT = 25         # Absolute max iterations — hard stop
MAX_CONTEXT_PAIRS = 10  # Max assistant+tool pairs preserved during compression
TRIM_THRESHOLD = 0.45   # Trigger context trim at 45% of estimated context window
EMERGENCY_THRESHOLD = 0.70  # Force compression regardless of content

# Conservative context-window estimates per provider.
# These should be well under the model's true limit so compression
# fires early enough to keep the LLM call efficient.
ESTIMATED_CONTEXT_WINDOW = {
    "anthropic": 80_000,
    "openai": 48_000,
}

# Per-tool truncation limits (characters). Tool names not in this map
# default to 300 characters.
TOOL_TRUNCATION_LIMITS = {
    "shell_exec": 2000,
    "file_read": 3000,
    "browser_get_text": 1200,
    "browser_get_markdown": 2000,
    "browser_get_html": 2000,
    "browser_evaluate": 1000,
    "browser_get_clickable_elements": 1000,
    "browser_read_links": 800,
    "code_python": 2000,
    "code_javascript": 2000,
    "sandbox_info": 1500,
    "file_search": 1500,
    "file_list": 1500,
}
DEFAULT_TRUNCATION = 300

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

SYSTEM_PROMPT = """你是 AI Chat Sandbox 助手。你可以进行普通对话，也可以在需要时调用工具操作沙箱环境（浏览器、Shell、文件、代码执行）。

## 工具使用规则

1. **按需调用** — 只在需要沙箱能力时调用工具。常识问答、简单计算直接回复文字。
2. **逐步执行** — 一次调用必要的工具，观察结果后决定下一步。
3. **先观察后操作** — 操作浏览器前先用 browser_get_text 或 browser_get_clickable_elements 了解页面状态。
4. **及时停止** — 以下情况立即停止调用工具并以文字回复：
   - 任务目标已完成
   - 同一工具连续 2 次返回同样的错误
   - 已获取足够信息回答用户
5. **避免死循环** — 如果发现自己在重复相同的工具调用模式，立即停止用文字说明。

## 复杂任务规划

- **判断复杂度**：如果用户请求需要 3 次以上的工具调用才能完成，请在调用任何工具之前先用文字输出一份简要计划。
- **计划格式**：列出关键步骤即可，不必过于详细。
- **简单任务**：直接执行，不需要规划。
- **执行中调整**：每步完成后检查是否达到目标，必要时调整后续计划。
- **失败处理**：某个工具连续报错 2 次后放弃该方案，换一种方式或向用户说明。

## 上下文管理

- 长对话中较早的轮次可能会被系统压缩以节省空间，压缩处会标注「上下文压缩」标记。
- 看到压缩标记不必在意，继续当前任务即可。
- 工具结果被截断时会标注省略的字符数。

"""


# ------------------------------------------------------------------
# LLM factory
# ------------------------------------------------------------------

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
# Cancel registry (per-session)
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
# Token estimation (approximate, for context management)
# ------------------------------------------------------------------

def _estimate_tokens(obj: Any) -> int:
    """Rough token estimation — 1 token ≈ 3 characters for mixed CJK/ASCII."""
    if isinstance(obj, str):
        return max(1, len(obj) // 3)
    if isinstance(obj, dict):
        return _estimate_tokens(str(obj))
    if isinstance(obj, list):
        return sum(_estimate_tokens(item) for item in obj)
    return 1


# ------------------------------------------------------------------
# Smart tool-result truncation
# ------------------------------------------------------------------

def _truncate_result(tool_name: str, result: str) -> str:
    """Truncate tool result according to tool-specific limits."""
    limit = TOOL_TRUNCATION_LIMITS.get(tool_name, DEFAULT_TRUNCATION)
    if len(result) <= limit:
        return result
    truncated = result[:limit]
    omitted = len(result) - limit
    return f"{truncated}\n\n[...结果已截断，共 {len(result)} 字符，显示前 {limit} 字符，省略 {omitted} 字符]"


# ------------------------------------------------------------------
# Context compression
# ------------------------------------------------------------------

def _trim_context_if_needed(messages: list[dict], provider: str, emergency: bool = False) -> bool:
    """Compress messages when estimated tokens exceed threshold. Returns True if trimmed.

    Normal mode: trims when token count > TRIM_THRESHOLD of context window.
    Emergency mode (called before LLM call): trims more aggressively when
    token count > EMERGENCY_THRESHOLD, guaranteed to reduce size.
    """
    context_window = ESTIMATED_CONTEXT_WINDOW.get(provider, 24_000)
    threshold = EMERGENCY_THRESHOLD if emergency else TRIM_THRESHOLD
    max_tokens = int(context_window * threshold)

    total = _estimate_tokens(messages)
    if not emergency and total <= max_tokens:
        return False

    # Split system vs non-system
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    if len(non_system) <= 3:
        return False

    # Always keep the original user message + last MAX_CONTEXT_PAIRS pairs
    max_keep = MAX_CONTEXT_PAIRS * 2
    first_user = non_system[0]

    # Emergency: even cut into the recent window if still over threshold
    if emergency or len(non_system) > max_keep:
        # In emergency mode, keep fewer pairs
        actual_keep = max_keep // 2 if emergency and len(non_system) > max_keep // 2 else max_keep
        if len(non_system) > actual_keep:
            last_msgs = non_system[-(actual_keep - 1):]
            trimmed = len(non_system) - actual_keep
            # Append compression notice to the original user message instead of
            # inserting a separate message — consecutive user messages break
            # the Anthropic API's strict user/assistant alternation requirement.
            if isinstance(first_user.get("content"), str) and not first_user.get("compressed"):
                first_user["content"] += f"\n\n[上下文压缩：省略了中间 {trimmed} 条消息以节省空间，关键信息已保留在后续轮次中，继续当前任务即可]"
                first_user["compressed"] = True
                compressed = [first_user]
            else:
                compressed = [first_user]
            compressed.extend(last_msgs)

            messages.clear()
            messages.extend(system_msgs)
            messages.extend(compressed)

            # If still over threshold in emergency mode, aggressively trim tool results
            if emergency:
                for m in messages:
                    content = m.get("content", "")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "tool_result":
                                text = item.get("content", "")
                                if isinstance(text, str) and len(text) > 500:
                                    item["content"] = text[:500] + f"[...截断，省略 {len(text) - 500} 字符]"

            return True

    return False


# ------------------------------------------------------------------
# Progress detection for dynamic iteration limits
# ------------------------------------------------------------------

def _is_still_making_progress(recent_calls: list[tuple[str, str]], window: int = 5) -> bool:
    """Check whether recent tool calls show meaningful progress.

    Returns False when the same (tool, args) pattern repeats too often,
    indicating the agent is stuck.
    """
    if len(recent_calls) < window:
        return True  # not enough data yet
    windowed = recent_calls[-window:]
    # If the same exact signature appears 3+ times in the window, we're stuck
    latest = windowed[-1]
    if windowed.count(latest) >= 3:
        return False
    return True


# ------------------------------------------------------------------
# Agent loop
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

    provider = config.llm_provider
    session.add_message("user", user_message)
    llm.inject_system_prompt(session.messages, SYSTEM_PROMPT)

    tool_schemas = registry.get_schemas()

    # Track tool-call signatures for loop and progress detection
    recent_tool_calls: list[tuple[str, str]] = []

    # Track whether we've compressed context already (avoid repeated compression)
    did_compress = False
    turn_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    for iteration in range(HARD_LIMIT):
        # ── cancellation check ──
        if cancel_event and cancel_event.is_set():
            yield {"type": "error", "message": "用户取消了执行"}
            return

        # ── context compression check (before LLM call) ──
        if iteration >= 2:
            # Normal compression — runs every 2 iterations
            if iteration % 2 == 0:
                was_trimmed = _trim_context_if_needed(session.messages, provider)
                if was_trimmed and not did_compress:
                    did_compress = True
                    yield {"type": "notice", "message": "上下文已压缩，旧轮次已优化以节省空间"}
            # Emergency compression — runs EVERY iteration past iteration 4,
            # ensures we never exceed the hard limit
            if iteration >= 4:
                _trim_context_if_needed(session.messages, provider, emergency=True)

        # ── Phase: analyzing ──
        iteration_label = (
            f"第 {iteration + 1} 轮：分析需求" if iteration == 0
            else f"第 {iteration + 1} 轮：分析结果，规划下一步"
        )
        yield {"type": "phase", "phase": "analyzing", "iteration": iteration + 1,
               "label": iteration_label}

        full_text = ""
        response: LLMResponse | None = None

        turn_usage["prompt_tokens"] += _estimate_tokens(session.messages) + _estimate_tokens(tool_schemas)

        try:
            stream = llm.chat_stream(session.messages, tool_schemas)
            while True:
                try:
                    chunk = await asyncio.wait_for(stream.__anext__(), timeout=120.0)
                except StopAsyncIteration:
                    break

                if cancel_event and cancel_event.is_set():
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
        except asyncio.TimeoutError:
            logger.warning("LLM call timed out on iteration %d", iteration)
            yield {"type": "error", "message": "LLM 响应超时，请重试或简化请求"}
            return
        except Exception:
            logger.exception("LLM call failed on iteration %d", iteration)
            yield {"type": "error", "message": "LLM 调用异常，请稍后重试"}
            return

        if cancel_event and cancel_event.is_set():
            yield {"type": "error", "message": "用户取消了执行"}
            return

        # Signal end of LLM thinking/reasoning phase
        yield {"type": "thinking_end"}

        if response is None:
            yield {"type": "error", "message": "LLM 未返回有效响应"}
            return

        # ── Text response → task complete ──
        if response.type == "text":
            yield {"type": "phase", "phase": "responding", "label": "生成回复"}
            text = response.text or ""
            turn_usage["completion_tokens"] += _estimate_tokens(text) + _estimate_tokens(response.reasoning_content)

            session.add_message("assistant", text, reasoning_content=response.reasoning_content)
            yield {
                "type": "usage",
                "prompt_tokens": turn_usage["prompt_tokens"],
                "completion_tokens": turn_usage["completion_tokens"],
                "total_tokens": turn_usage["prompt_tokens"] + turn_usage["completion_tokens"],
            }
            return

        # ── Tool calls ──
        if response.type == "tool_calls" and response.tool_calls:
            turn_usage["completion_tokens"] += _estimate_tokens(response.reasoning_content) + _estimate_tokens([
                {"name": tc.name, "arguments": tc.arguments} for tc in response.tool_calls
            ])
            yield {
                "type": "usage",
                "prompt_tokens": turn_usage["prompt_tokens"],
                "completion_tokens": turn_usage["completion_tokens"],
                "total_tokens": turn_usage["prompt_tokens"] + turn_usage["completion_tokens"],
            }
            tool_names = [tc.name for tc in response.tool_calls]
            yield {"type": "phase", "phase": "executing", "iteration": iteration + 1,
                   "tools": tool_names, "count": len(tool_names),
                   "label": f"第 {iteration + 1} 轮：调用 {', '.join(tool_names)}"}

            # ── loop detection ──
            call_sig = (
                ",".join(tool_names),
                json.dumps([tc.arguments for tc in response.tool_calls], sort_keys=True),
            )
            recent_tool_calls.append(call_sig)
            if len(recent_tool_calls) > 8:
                recent_tool_calls = recent_tool_calls[-8:]

            # Same pattern 3+ times in last 4 → stuck
            if not _is_still_making_progress(recent_tool_calls, window=4):
                yield {"type": "error",
                       "message": "检测到重复的工具调用模式，Agent 已停止。请简化请求或换个方式提问。"}
                return

            # ── execute tools ──
            tool_results: list[tuple[Any, str]] = []
            for tc in response.tool_calls:
                if cancel_event and cancel_event.is_set():
                    yield {"type": "error", "message": "用户取消了执行"}
                    return

                # Emit action event for frontend panel
                if tc.name.startswith("browser_"):
                    action = tc.name.removeprefix("browser_")
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
                else:
                    # Non-browser tools: show in action log
                    detail = ""
                    for k, v in tc.arguments.items():
                        if isinstance(v, str) and len(v) > 60:
                            v = v[:60] + "…"
                        detail += f"{k}={v}, "
                    yield {"type": "browser_action", "action": tc.name, "detail": detail.rstrip(", ")}

                yield {"type": "tool_start", "tool": tc.name, "args": tc.arguments}

                try:
                    result = await registry.execute(tc.name, **tc.arguments)
                except Exception as e:
                    result = f"工具执行异常：{e}"
                    logger.exception("Tool execution failed: %s", tc.name)

                # **IMPORTANT**: convert the raw result into an LLM-safe form
                # before storing.  Full base64 images (500 K+) would blow the
                # context window immediately.
                if result.startswith("[IMAGE]"):
                    # Save screenshot to file and yield URL instead of base64
                    img_data = result[7:]  # data:image/png;base64,...
                    try:
                        # Parse base64 from data URI
                        b64_str = img_data
                        if "," in b64_str:
                            b64_str = b64_str.split(",", 1)[1]
                        png_bytes = base64.b64decode(b64_str)
                        filename = f"{session.session_id}_{uuid.uuid4().hex[:8]}.png"
                        filepath = os.path.join("static", "screenshots", filename)
                        with open(filepath, "wb") as f:
                            f.write(png_bytes)
                        img_url = f"/static/screenshots/{filename}"
                    except Exception:
                        logger.exception("Failed to save screenshot")
                        img_url = img_data  # fallback to base64
                    yield {"type": "image", "src": img_url}
                    result_for_llm = "[截图已获取]"
                elif result.startswith("[ERROR]"):
                    result_for_llm = result[:500]
                else:
                    result_for_llm = _truncate_result(tc.name, result)

                tool_results.append((tc, result_for_llm))

                yield {"type": "tool_end", "tool": tc.name, "result": result_for_llm,
                       "truncated": len(result) > TOOL_TRUNCATION_LIMITS.get(tc.name, DEFAULT_TRUNCATION)}

            # ── Observing phase ──
            yield {"type": "phase", "phase": "observing", "iteration": iteration + 1,
                   "label": f"第 {iteration + 1} 轮：分析执行结果"}

            if cancel_event and cancel_event.is_set():
                yield {"type": "error", "message": "用户取消了执行"}
                return

            # Append messages for next LLM turn
            session.messages.append(
                llm.format_assistant_tool_calls(tool_results, reasoning_content=response.reasoning_content)
            )
            for tc, result in tool_results:
                session.messages.append(
                    llm.format_tool_result(tc.id, tc.name, result)
                )

            # ── Dynamic early termination after soft limit ──
            if iteration + 1 >= SOFT_LIMIT:
                if not _is_still_making_progress(recent_tool_calls):
                    yield {"type": "error",
                           "message": f"Agent 执行已进行 {iteration + 1} 轮，但未取得有效进展，已自动停止。"}
                    return

    # Hard limit reached
    yield {"type": "error", "message": f"Agent 执行已进行 {HARD_LIMIT} 轮，已达到最大限制。请简化请求或换个方式提问。"}
