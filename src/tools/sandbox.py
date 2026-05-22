from __future__ import annotations

import base64
import json
import logging
import urllib.parse
from typing import Any, TYPE_CHECKING

import httpx

from .base import Tool

if TYPE_CHECKING:
    from .base import ToolRegistry

logger = logging.getLogger(__name__)


class SandboxAPI:
    """Low-level HTTP wrapper for the AIO Sandbox REST API (v1.0.0.156).

    Uses three mechanisms for browser control, in priority order:
      1. MCP browser server  (richest, but can degrade when CDP stalls)
      2. REST browser_action  (display-level mouse/keyboard/scroll)
      3. xdotool + xclip via shell_exec  (keyboard/mouse/clipboard)

    Screenshots always use the REST endpoint (most reliable).
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60))

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # raw HTTP helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str) -> dict[str, Any]:
        r = await self._client.get(f"{self.base_url}{path}")
        r.raise_for_status()
        return r.json()

    async def _get_bytes(self, path: str) -> bytes:
        r = await self._client.get(f"{self.base_url}{path}")
        r.raise_for_status()
        return r.content

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        r = await self._client.post(f"{self.base_url}{path}", json=body or {})
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # sandbox info
    # ------------------------------------------------------------------

    async def get_info(self) -> dict[str, Any]:
        return await self._get("/v1/sandbox")

    # ------------------------------------------------------------------
    # shell
    # ------------------------------------------------------------------

    async def shell_exec(self, command: str, timeout: int = 30) -> dict[str, Any]:
        body: dict[str, Any] = {"command": command}
        if timeout:
            body["timeout"] = timeout
        resp = await self._post("/v1/shell/exec", body)
        return resp.get("data", resp)

    # ------------------------------------------------------------------
    # file operations
    # ------------------------------------------------------------------

    async def file_read(self, path: str) -> dict[str, Any]:
        resp = await self._post("/v1/file/read", {"file": path})
        return resp.get("data", resp)

    async def file_write(self, path: str, content: str, encoding: str = "utf-8") -> dict[str, Any]:
        resp = await self._post("/v1/file/write", {"file": path, "content": content, "encoding": encoding})
        return resp.get("data", resp)

    async def file_list(self, path: str) -> dict[str, Any]:
        resp = await self._post("/v1/file/list", {"path": path})
        return resp.get("data", resp)

    async def file_search(self, path: str, regex: str) -> dict[str, Any]:
        resp = await self._post("/v1/file/search", {"file": path, "regex": regex})
        return resp.get("data", resp)

    async def file_find(self, path: str, glob: str) -> dict[str, Any]:
        resp = await self._post("/v1/file/find", {"path": path, "glob": glob})
        return resp.get("data", resp)

    async def file_replace(self, path: str, old_text: str, new_text: str) -> dict[str, Any]:
        """Replace the first occurrence of old_text with new_text in file."""
        resp = await self._post("/v1/file/replace", {
            "file": path, "old_text": old_text, "new_text": new_text,
        })
        return resp.get("data", resp)

    async def file_download(self, path: str) -> bytes:
        """Download a file from the sandbox. Returns raw bytes."""
        encoded = urllib.parse.quote(path)
        return await self._get_bytes(f"/v1/file/download?file={encoded}")

    async def file_upload(self, path: str, content_b64: str) -> dict[str, Any]:
        """Upload a file to the sandbox. content_b64 is base64-encoded content."""
        resp = await self._post("/v1/file/upload", {
            "file": path, "content": content_b64, "encoding": "base64",
        })
        return resp.get("data", resp)

    # ------------------------------------------------------------------
    # code execution
    # ------------------------------------------------------------------

    async def code_execute(self, language: str, code: str, timeout: int = 30) -> dict[str, Any]:
        resp = await self._post("/v1/code/execute", {"language": language, "code": code, "timeout": timeout})
        return resp.get("data", resp)

    # ------------------------------------------------------------------
    # jupyter
    # ------------------------------------------------------------------

    async def jupyter_execute(self, code: str, timeout: int = 60) -> dict[str, Any]:
        """Execute Python code in a persistent Jupyter kernel. Kernel state
        (variables, imports) persists across calls within the same session."""
        resp = await self._post("/v1/jupyter/execute", {"code": code, "timeout": timeout})
        return resp.get("data", resp)

    # ------------------------------------------------------------------
    # browser – REST endpoints
    # ------------------------------------------------------------------

    async def browser_info(self) -> dict[str, Any]:
        resp = await self._get("/v1/browser/info")
        return resp.get("data", resp)

    async def browser_screenshot(self) -> bytes:
        """Returns raw PNG bytes from the REST endpoint (most reliable)."""
        return await self._get_bytes("/v1/browser/screenshot")

    async def browser_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Post a single display-level action (SCROLL, MOUSE_MOVE, LEFT_CLICK, etc.)."""
        return await self._post("/v1/browser/actions", action)

    # ------------------------------------------------------------------
    # MCP tool calls  (generic + browser + markitdown)
    # ------------------------------------------------------------------

    async def mcp_call(self, server: str, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call any MCP server tool and return its text content.
        Returns the text string on success, or a string starting with [ERROR]
        on failure.
        """
        try:
            resp = await self._post(
                f"/v1/mcp/{server}/tools/{tool_name}",
                arguments or {},
            )
        except Exception as exc:
            return f"[ERROR] MCP call '{server}/{tool_name}' failed: {exc}"

        if not resp.get("success"):
            msg = resp.get("message", "unknown error")
            return f"[ERROR] MCP '{server}/{tool_name}' returned failure: {msg}"

        data = resp.get("data", {})
        if data.get("isError"):
            content = data.get("content", [])
            err_text = content[0].get("text", "unknown") if content else "unknown"
            return f"[ERROR] MCP '{server}/{tool_name}' error: {err_text}"

        content = data.get("content", [])
        if content:
            item = content[0]
            if isinstance(item, dict):
                return item.get("text", "")
            return str(item)
        return ""

    async def mcp_browser_call(self, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call the browser MCP server tool."""
        return await self.mcp_call("browser", tool_name, arguments)

    async def mcp_markitdown_call(self, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call the markitdown MCP server tool (document conversion)."""
        return await self.mcp_call("markitdown", tool_name, arguments)

    # ------------------------------------------------------------------
    # xdotool helpers  (fallback when MCP is unresponsive)
    # ------------------------------------------------------------------

    async def _xdotool(self, args: str, timeout: int = 8) -> str:
        """Run an xdotool command inside the sandbox. Returns stdout or [ERROR]."""
        cmd = f"export DISPLAY=:99.0; timeout {timeout} xdotool {args} 2>&1"
        try:
            result = await self.shell_exec(cmd, timeout=timeout + 3)
            output = (result.get("output") or "").strip()
            return output
        except Exception as exc:
            return f"[ERROR] xdotool failed: {exc}"

    async def _xclip_get(self) -> str:
        """Read clipboard text via xclip."""
        try:
            result = await self.shell_exec("timeout 3 xclip -selection clipboard -o 2>&1", timeout=6)
            return (result.get("output") or "").strip()
        except Exception:
            return ""

    async def _get_current_url_via_clipboard(self) -> str:
        """Get current browser URL by copying from the address bar."""
        await self._xdotool("key ctrl+l", timeout=5)
        await _sleep_in_sandbox(self, 0.3)
        await self._xdotool("key ctrl+c", timeout=5)
        await _sleep_in_sandbox(self, 0.3)
        url = await self._xclip_get()
        await self._xdotool("key Escape", timeout=3)
        return url


# ======================================================================
# Tool implementations
# ======================================================================


class SandboxInfoTool(Tool):
    def __init__(self, api: SandboxAPI):
        super().__init__(
            name="sandbox_info",
            description="获取沙箱环境信息，包括家目录路径、已安装的 Python 包列表等。",
            parameters={"type": "object", "properties": {}, "required": []},
        )
        self._api = api

    async def execute(self, **kwargs: Any) -> str:
        info = await self._api.get_info()
        return json.dumps(info, ensure_ascii=False, indent=2)


class BrowserNavigateTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_navigate",
            description="在浏览器中导航到指定 URL。返回页面文本和可交互元素列表。",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要导航到的完整 URL，如 https://example.com"}
                },
                "required": ["url"],
            },
        )

    async def execute(self, url: str, **kwargs: Any) -> str:
        # Primary: MCP browser tool
        result = await self._api.mcp_browser_call("browser_navigate", {"url": url})
        if not result.startswith("[ERROR]"):
            return result

        # Fallback: xdotool type URL in address bar
        logger.warning("MCP navigate failed, using xdotool fallback: %s", result)
        await self._api._xdotool("key ctrl+l", timeout=5)
        await _sleep_in_sandbox(self._api, 0.3)
        await self._api._xdotool(f"type '{url}'", timeout=5)
        await _sleep_in_sandbox(self._api, 0.2)
        await self._api._xdotool("key Return", timeout=5)
        await _sleep_in_sandbox(self._api, 3)
        return f"已导航到 {url}（使用 xdotool 方式）"


class BrowserScreenshotTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_screenshot",
            description="截取当前浏览器页面的截图。返回 base64 编码的 PNG 图片。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        try:
            png_bytes = await self._api.browser_screenshot()
            if png_bytes:
                return f"[IMAGE]data:image/png;base64,{base64.b64encode(png_bytes).decode('utf-8')}"
            return "[ERROR] 截图返回空数据"
        except Exception as exc:
            return f"[ERROR] 截图失败：{exc}"


class BrowserGetTextTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_get_text",
            description="获取当前页面上所有可见的文本内容。用于提取页面信息。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        # Primary: MCP browser tool
        result = await self._api.mcp_browser_call("browser_get_text", {})
        if not result.startswith("[ERROR]") and result.strip():
            return result

        # Fallback: curl current URL for text
        logger.warning("MCP get_text failed, trying curl fallback")
        url = await self._api._get_current_url_via_clipboard()
        if url and url.startswith("http"):
            try:
                curl_result = await self._api.shell_exec(
                    f"curl -s --max-time 10 -L '{url}' 2>/dev/null | python3 -c "
                    f"\"import sys,html.parser; "
                    f"class T(html.parser.HTMLParser):"
                    f" def __init__(s):super().__init__();s.t=[];s.skip=False;"
                    f" def handle_starttag(s,t,a):s.skip=t in('script','style','noscript');"
                    f" def handle_endtag(s,t):"
                    f"  if t in('p','div','li','tr','h1','h2','h3','h4','h5','h6','br'):s.t.append('\\n');"
                    f" def handle_data(s,d):"
                    f"  if not s.skip:s.t.append(d.strip());"
                    f"p=T();p.feed(sys.stdin.read());print(' '.join(p.t)[:8000])\"",
                    timeout=15,
                )
                text = (curl_result.get("output") or "").strip()
                if text:
                    return text
            except Exception:
                pass

        return "[WARN] 无法获取页面文本。请使用 browser_screenshot 查看页面。"


class BrowserGetMarkdownTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_get_markdown",
            description="将当前页面转换为 Markdown 格式。适合提取文章、文档等结构化内容。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._api.mcp_browser_call("browser_get_markdown", {})
        if not result.startswith("[ERROR]") and result.strip():
            return result

        # Fallback: get text instead
        logger.warning("MCP get_markdown failed, falling back to get_text")
        text = await self._api.mcp_browser_call("browser_get_text", {})
        return text if text.strip() else "[WARN] 无法获取页面内容"


class BrowserGetHtmlTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_get_html",
            description="获取当前页面的 HTML 源码。仅在需要分析页面结构时使用。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        # Try MCP evaluate to get HTML, fall back to curl
        result = await self._api.mcp_browser_call(
            "browser_evaluate",
            {"expression": "document.documentElement.outerHTML"},
        )
        if not result.startswith("[ERROR]") and result.strip():
            return result[:15000]

        # Fallback: curl the current URL
        url = await self._api._get_current_url_via_clipboard()
        if url and url.startswith("http"):
            try:
                curl_result = await self._api.shell_exec(
                    f"curl -s --max-time 10 -L '{url}' 2>/dev/null | head -c 15000",
                    timeout=15,
                )
                html = (curl_result.get("output") or "").strip()
                if html:
                    return html
            except Exception:
                pass

        return "[WARN] 无法获取页面 HTML"


class BrowserClickTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_click",
            description="点击页面上的可交互元素。需要先使用 browser_get_clickable_elements 获取元素索引，然后使用索引点击。也可以直接使用 CSS 选择器。",
            parameters={
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "从 browser_get_clickable_elements 获取的元素索引，优先使用"},
                    "selector": {"type": "string", "description": "CSS 选择器，如 '#submit-btn'，当 index 不可用时使用"},
                },
                "required": [],
            },
        )

    async def execute(self, index: int | None = None, selector: str | None = None, **kwargs: Any) -> str:
        args: dict[str, Any] = {}
        if index is not None:
            args["index"] = index
        elif selector is not None:
            args["selector"] = selector
        else:
            return "[ERROR] 必须提供 index 或 selector 参数"

        # Primary: MCP browser tool
        result = await self._api.mcp_browser_call("browser_click", args)
        if not result.startswith("[ERROR]"):
            return result

        # Fallback: use xdotool to click at center or use browser_action
        logger.warning("MCP click failed, using display-level fallback: %s", result)
        try:
            await self._api.browser_action({"action_type": "LEFT_CLICK"})
            return "已点击（使用 display-level 点击）"
        except Exception:
            return f"[ERROR] 点击失败：{result}"


class BrowserFillTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_fill",
            description="在输入框中填入文本。优先使用元素索引，也可使用 CSS 选择器。",
            parameters={
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "从 browser_get_clickable_elements 获取的元素索引"},
                    "selector": {"type": "string", "description": "输入框的 CSS 选择器"},
                    "value": {"type": "string", "description": "要填入的文本"},
                    "clear": {"type": "boolean", "description": "是否先清空已有内容，默认 false"},
                },
                "required": ["value"],
            },
        )

    async def execute(self, value: str, index: int | None = None, selector: str | None = None, clear: bool = False, **kwargs: Any) -> str:
        args: dict[str, Any] = {"value": value}
        if index is not None:
            args["index"] = index
        if selector is not None:
            args["selector"] = selector
        if clear:
            args["clear"] = True

        # Primary: MCP browser tool
        result = await self._api.mcp_browser_call("browser_form_input_fill", args)
        if not result.startswith("[ERROR]"):
            return result

        # Fallback: xdotool type
        logger.warning("MCP fill failed, using xdotool fallback: %s", result)
        escaped = value.replace("'", "\\'")
        await self._api._xdotool(f"type '{escaped}'", timeout=8)
        return f"已输入文本（使用 xdotool 方式）"


class BrowserScrollTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_scroll",
            description="滚动当前页面或指定元素。",
            parameters={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["down", "up"],
                        "description": "滚动方向：down 向下，up 向上",
                    },
                    "amount": {"type": "integer", "description": "滚动像素量，默认 500"},
                },
                "required": [],
            },
        )

    async def execute(self, direction: str = "down", amount: int = 500, **kwargs: Any) -> str:
        dy = -amount if direction == "up" else amount

        # Primary: MCP browser tool
        result = await self._api.mcp_browser_call("browser_scroll", {"dy": dy})
        if not result.startswith("[ERROR]"):
            return result

        # Fallback: REST browser_action
        logger.warning("MCP scroll failed, using REST fallback")
        try:
            resp = await self._api.browser_action({"action_type": "SCROLL", "dx": 0, "dy": dy})
            return json.dumps(resp, ensure_ascii=False)
        except Exception as exc:
            return f"[ERROR] 滚动失败：{exc}"


class BrowserEvaluateTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_evaluate",
            description="在页面中执行 JavaScript 表达式并返回结果。用于提取页面数据、操作 DOM 等。",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "JavaScript 表达式，如 'document.title'"}
                },
                "required": ["expression"],
            },
        )

    async def execute(self, expression: str, **kwargs: Any) -> str:
        result = await self._api.mcp_browser_call("browser_evaluate", {"expression": expression})
        if not result.startswith("[ERROR]"):
            return result
        return f"[ERROR] JavaScript 执行不可用：{result}"


class BrowserFindTextTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_find_text",
            description="在页面中搜索指定文本。先获取页面文本再搜索。",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "要搜索的关键词"},
                },
                "required": ["keyword"],
            },
        )

    async def execute(self, keyword: str, **kwargs: Any) -> str:
        text = await self._api.mcp_browser_call("browser_get_text", {})
        if text.startswith("[ERROR]"):
            return json.dumps({"found": False, "error": text}, ensure_ascii=False)
        if keyword in text:
            idx = text.index(keyword)
            ctx = text[max(0, idx - 50):idx + len(keyword) + 50]
            return json.dumps({"found": True, "context": ctx}, ensure_ascii=False)
        return json.dumps({"found": False}, ensure_ascii=False)


class BrowserWaitTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_wait",
            description="等待指定的时间（毫秒）。用于等待页面加载或动画完成。",
            parameters={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["timeout", "load", "selector"],
                        "description": "等待类型：timeout 固定等待，load 等待页面加载，selector 等待元素出现",
                    },
                    "selector": {"type": "string", "description": "当 type 为 selector 时的 CSS 选择器"},
                    "timeout": {"type": "integer", "description": "超时时间（毫秒），默认 3000"},
                },
                "required": ["type"],
            },
        )

    async def execute(self, type: str, selector: str | None = None, timeout: int | None = None, **kwargs: Any) -> str:
        ms = timeout or 3000
        seconds = max(0.5, ms / 1000.0)

        if type == "selector" and selector:
            return f"[INFO] 等待选择器 '{selector}' 功能需要 MCP 支持，已等待 {ms}ms"

        await _sleep_in_sandbox(self._api, seconds)
        return json.dumps({"waited": True, "duration_ms": ms}, ensure_ascii=False)


class BrowserBackTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_back",
            description="返回浏览器历史记录的上一页。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._api.mcp_browser_call("browser_go_back", {})
        if not result.startswith("[ERROR]"):
            return result
        # Fallback: Alt+Left via xdotool
        await self._api._xdotool("key Alt+Left", timeout=5)
        await _sleep_in_sandbox(self._api, 1.5)
        return "已返回上一页（xdotool 方式）"


class BrowserReloadTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_reload",
            description="刷新当前页面。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        # Try MCP evaluate first to reload
        result = await self._api.mcp_browser_call(
            "browser_evaluate", {"expression": "location.reload()"}
        )
        if not result.startswith("[ERROR]"):
            await _sleep_in_sandbox(self._api, 2)
            return "页面已刷新"

        # Fallback: F5 via xdotool
        await self._api._xdotool("key F5", timeout=5)
        await _sleep_in_sandbox(self._api, 2)
        return "页面已刷新（xdotool 方式）"


class BrowserGetClickableElementsTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_get_clickable_elements",
            description="获取页面上所有可交互元素（链接、按钮、输入框等）的索引列表。使用这些索引来点击或填写元素。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._api.mcp_browser_call("browser_get_clickable_elements", {})
        if not result.startswith("[ERROR]"):
            return result
        return f"[ERROR] 无法获取可交互元素：{result}"


class BrowserReadLinksTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_read_links",
            description="获取当前页面上所有链接（文本和 URL）。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._api.mcp_browser_call("browser_read_links", {})
        if not result.startswith("[ERROR]"):
            return result
        return f"[ERROR] 无法获取链接：{result}"


class BrowserPressKeyTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_press_key",
            description="在浏览器中按下键盘按键。用于快捷键操作。",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "按键名称，如 'Enter', 'Escape', 'F5', 'Page_Down'"},
                },
                "required": ["key"],
            },
        )

    async def execute(self, key: str, **kwargs: Any) -> str:
        # Try MCP
        result = await self._api.mcp_browser_call("browser_press_key", {"key": key})
        if not result.startswith("[ERROR]"):
            return result
        # Fallback: xdotool
        await self._api._xdotool(f"key {key}", timeout=5)
        return f"已按下 {key}（xdotool 方式）"


class BrowserTabsListTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_tabs_list",
            description="列出所有打开的浏览器标签页。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._api.mcp_browser_call("browser_tab_list", {})
        if not result.startswith("[ERROR]"):
            return result
        return f"[ERROR] 无法获取标签页列表：{result}"


class BrowserTabsCreateTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_tabs_create",
            description="创建一个新的浏览器标签页。",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "新标签页要打开的 URL，默认为 about:blank"},
                },
                "required": ["url"],
            },
        )

    async def execute(self, url: str = "about:blank", **kwargs: Any) -> str:
        result = await self._api.mcp_browser_call("browser_new_tab", {"url": url})
        if not result.startswith("[ERROR]"):
            return result
        # Fallback: Ctrl+T, type URL, Enter
        await self._api._xdotool("key ctrl+t", timeout=5)
        await _sleep_in_sandbox(self._api, 0.5)
        await self._api._xdotool(f"type '{url}'", timeout=5)
        await _sleep_in_sandbox(self._api, 0.3)
        await self._api._xdotool("key Return", timeout=5)
        await _sleep_in_sandbox(self._api, 2)
        return f"已创建新标签页：{url}（xdotool 方式）"


class BrowserTabsActivateTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="browser_tabs_activate",
            description="切换到指定的浏览器标签页。",
            parameters={
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "标签页索引（从 0 开始）"},
                },
                "required": ["index"],
            },
        )

    async def execute(self, index: int, **kwargs: Any) -> str:
        result = await self._api.mcp_browser_call("browser_switch_tab", {"index": index})
        if not result.startswith("[ERROR]"):
            return result
        return f"[ERROR] 无法切换标签页：{result}"


class ShellExecTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="shell_exec",
            description="在沙箱终端中执行 Shell 命令，返回命令输出。可用于文件操作、安装包等。",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 Shell 命令"},
                },
                "required": ["command"],
            },
        )

    async def execute(self, command: str, **kwargs: Any) -> str:
        result = await self._api.shell_exec(command)
        output = result.get("output", "")
        exit_code = result.get("exit_code", -1)
        if exit_code != 0 and not output:
            return json.dumps(result, ensure_ascii=False)
        return output or json.dumps(result, ensure_ascii=False)


class FileReadTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="file_read",
            description="读取沙箱中的文件内容。",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "文件的绝对路径"},
                },
                "required": ["file"],
            },
        )

    async def execute(self, file: str, **kwargs: Any) -> str:
        result = await self._api.file_read(file)
        return result.get("content", str(result))


class FileWriteTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="file_write",
            description="将内容写入沙箱中的文件。",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "文件的绝对路径"},
                    "content": {"type": "string", "description": "要写入的内容"},
                },
                "required": ["file", "content"],
            },
        )

    async def execute(self, file: str, content: str, **kwargs: Any) -> str:
        result = await self._api.file_write(file, content)
        return json.dumps(result, ensure_ascii=False)


class FileListTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="file_list",
            description="列出沙箱中指定目录的内容。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录的绝对路径"},
                },
                "required": ["path"],
            },
        )

    async def execute(self, path: str, **kwargs: Any) -> str:
        result = await self._api.file_list(path)
        files = result.get("files", [])
        return json.dumps(files, ensure_ascii=False, indent=2)


class FileSearchTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="file_search",
            description="在文件中搜索匹配正则表达式的内容。",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "文件的绝对路径"},
                    "regex": {"type": "string", "description": "正则表达式模式"},
                },
                "required": ["file", "regex"],
            },
        )

    async def execute(self, file: str, regex: str, **kwargs: Any) -> str:
        result = await self._api.file_search(file, regex)
        matches = result.get("matches", [])
        return json.dumps(matches, ensure_ascii=False)


class FileFindTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="file_find",
            description="按 glob 模式在沙箱中查找文件。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "搜索起始路径"},
                    "glob": {"type": "string", "description": "Glob 模式，如 '*.py' 或 '**/*.txt'"},
                },
                "required": ["path", "glob"],
            },
        )

    async def execute(self, path: str, glob: str, **kwargs: Any) -> str:
        result = await self._api.file_find(path, glob)
        files = result.get("files", [])
        return json.dumps(files, ensure_ascii=False, indent=2)


class CodePythonTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="code_python",
            description="在沙箱中执行 Python 代码。用于数据处理、计算等。代码中的 print 输出将被返回。",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python 代码"},
                },
                "required": ["code"],
            },
        )

    async def execute(self, code: str, **kwargs: Any) -> str:
        result = await self._api.code_execute("python", code)
        stdout = result.get("stdout", "") or ""
        stderr = result.get("stderr", "") or ""
        if stderr:
            stdout += f"\n[STDERR]\n{stderr}"
        return stdout or json.dumps(result, ensure_ascii=False)


class CodeJavaScriptTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="code_javascript",
            description="在沙箱的 Node.js 环境中执行 JavaScript 代码。",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "JavaScript 代码"},
                },
                "required": ["code"],
            },
        )

    async def execute(self, code: str, **kwargs: Any) -> str:
        result = await self._api.code_execute("javascript", code)
        stdout = result.get("stdout", "") or ""
        stderr = result.get("stderr", "") or ""
        if stderr:
            stdout += f"\n[STDERR]\n{stderr}"
        return stdout or json.dumps(result, ensure_ascii=False)


class FileReplaceTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="file_replace",
            description="在文件中精确替换文本。将文件中首次出现的 old_text 替换为 new_text。比 read + write 更安全，用于修改配置文件、代码等场景。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件绝对路径"},
                    "old_text": {"type": "string", "description": "要替换的旧文本（首次出现被替换）"},
                    "new_text": {"type": "string", "description": "替换后的新文本"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        )

    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        result = await self._api.file_replace(path, old_text, new_text)
        # Surface API-level errors (e.g. file not found)
        if isinstance(result, dict) and ("error" in result or not result.get("success", True)):
            return json.dumps(result, ensure_ascii=False)
        replaced = result.get("replaced", False)
        count = result.get("count", 0)
        if replaced:
            return f"已替换 {count} 处匹配"
        return "未找到匹配文本，未做任何替换"


class FileDownloadTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="file_download",
            description="从沙箱下载文件。返回文件内容供 LLM 读取或保存到本地。适合查看沙箱中的文件、将处理结果提供给用户等场景。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件在沙箱中的绝对路径"},
                },
                "required": ["path"],
            },
        )

    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            raw = await self._api.file_download(path)
            b64 = base64.b64encode(raw).decode("utf-8")
            filename = path.rsplit("/", 1)[-1] or "download"
            return f"[FILE_DOWNLOAD]{b64}|{filename}"
        except Exception as exc:
            return f"[ERROR] 下载失败：{exc}"


class FileUploadTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="file_upload",
            description="将 base64 编码的内容上传到沙箱中的指定路径。用于向沙箱写入文件（图片、数据文件等）。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件在沙箱中的目标绝对路径"},
                    "content_b64": {"type": "string", "description": "文件的 base64 编码内容"},
                },
                "required": ["path", "content_b64"],
            },
        )

    async def execute(self, path: str, content_b64: str, **kwargs: Any) -> str:
        try:
            result = await self._api.file_upload(path, content_b64)
            if isinstance(result, dict) and not result.get("success", True):
                return f"[ERROR] 上传失败：{result.get('message', '未知错误')}"
            return f"✅ 文件已上传到 {path}"
        except Exception as exc:
            return f"[ERROR] 上传失败：{exc}"


class MarkitdownConvertTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="markitdown_convert",
            description="将 URL 指向的网页或原始 HTML 内容转换为 Markdown 格式。适合提取网页内容、文档归档等场景。如果已打开浏览器页面，使用 browser_get_markdown 更直接。",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要转换的网页 URL（与 html 二选一）"},
                    "html": {"type": "string", "description": "原始 HTML 内容（与 url 二选一）"},
                },
                "required": [],
            },
        )

    async def execute(self, url: str | None = None, html: str | None = None, **kwargs: Any) -> str:
        args: dict[str, Any] = {}
        if url:
            args["url"] = url
        elif html:
            args["html"] = html
        else:
            return "[ERROR] 必须提供 url 或 html 参数"
        result = await self._api.mcp_markitdown_call("convert", args)
        if result.startswith("[ERROR]"):
            return result
        if len(result) > 20000:
            result = result[:20000] + f"\n\n[...结果已截断，共 {len(result)} 字符]"
        return result or "[INFO] 转换完成但无内容返回"


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------


async def _sleep_in_sandbox(api: SandboxAPI, seconds: float) -> None:
    """Sleep inside the sandbox (so we don't block the host)."""
    try:
        await api.shell_exec(f"sleep {seconds}", timeout=int(seconds) + 5)
    except Exception:
        pass


class JupyterExecuteTool(Tool):
    def __init__(self, api: SandboxAPI):
        self._api = api
        super().__init__(
            name="jupyter_execute",
            description="在沙箱的 Jupyter 内核中执行 Python 代码。Jupyter 维护内核状态——变量、导入、函数定义在多次调用间保持，适合数据分析、可视化、逐步实验等需要连续上下文的场景。如果是一次性脚本用 code_python 即可。",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要执行的 Python 代码"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认 60"},
                },
                "required": ["code"],
            },
        )

    async def execute(self, code: str, timeout: int = 60, **kwargs: Any) -> str:
        try:
            result = await self._api.jupyter_execute(code, timeout)
        except Exception as exc:
            return f"[ERROR] Jupyter 执行失败：{exc}"
        outputs = result.get("outputs", [])
        text_parts = []
        for out in outputs:
            otype = out.get("type", "")
            if otype == "stream":
                text_parts.append(out.get("text", "") or "")
            elif otype == "text" or otype == "display_data":
                text = out.get("text", "") or ""
                text_parts.append(text)
            elif otype == "error":
                ename = out.get("ename", "Error")
                evalue = out.get("evalue", "")
                traceback = "\n".join(out.get("traceback", []))
                text_parts.append(f"[{ename}] {evalue}\n{traceback}")
        return "\n".join(text_parts) or json.dumps(result, ensure_ascii=False)


# ------------------------------------------------------------------
# registration
# ------------------------------------------------------------------


def register_sandbox_tools(registry: "ToolRegistry", sandbox_base_url: str) -> "ToolRegistry":
    api = SandboxAPI(base_url=sandbox_base_url)

    tools: list[Tool] = [
        SandboxInfoTool(api),
        BrowserNavigateTool(api),
        BrowserScreenshotTool(api),
        BrowserGetTextTool(api),
        BrowserGetMarkdownTool(api),
        BrowserGetHtmlTool(api),
        BrowserClickTool(api),
        BrowserFillTool(api),
        BrowserScrollTool(api),
        BrowserEvaluateTool(api),
        BrowserFindTextTool(api),
        BrowserWaitTool(api),
        BrowserBackTool(api),
        BrowserReloadTool(api),
        BrowserGetClickableElementsTool(api),
        BrowserReadLinksTool(api),
        BrowserPressKeyTool(api),
        BrowserTabsListTool(api),
        BrowserTabsCreateTool(api),
        BrowserTabsActivateTool(api),
        ShellExecTool(api),
        FileReadTool(api),
        FileWriteTool(api),
        FileListTool(api),
        FileSearchTool(api),
        FileFindTool(api),
        FileReplaceTool(api),
        FileDownloadTool(api),
        FileUploadTool(api),
        MarkitdownConvertTool(api),
        CodePythonTool(api),
        CodeJavaScriptTool(api),
        JupyterExecuteTool(api),
    ]
    registry.register_many(tools)
    return registry
