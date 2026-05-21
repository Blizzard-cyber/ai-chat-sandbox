# AI 聊天沙箱系统 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 构建一个支持自然语言对话的 AI 聊天应用，Agent 可自主调用 AIO Sandbox（浏览器/Shell/文件/代码）来完成任务

**架构：** FastAPI 后端提供 SSE 流式 API，Agent Loop 编排 LLM 与工具调用，前端为纯静态 HTML 聊天界面。LLM 通过统一接口支持 Anthropic 和 OpenAI，沙箱工具通过 Python SDK (`agent-sandbox`) 调用

**技术栈：** Python 3.10+, FastAPI, httpx, anthropic SDK, openai SDK, agent-sandbox, uvicorn

---

## 依赖关系

```
config.py ──────────────────────────────────┐
                                             │
tools/base.py ──► tools/builtin.py           │
    │                │                       │
    │           tools/sandbox.py             │
    │                │                       │
    └────────┬───────┘                       │
             ▼                               │
llm/base.py ──► llm/anthropic_llm.py         │
    │            llm/openai_llm.py            │
    │                │                       │
    └────────┬───────┘                       │
             ▼                               ▼
        agent.py ◄── session.py ◄── config.py
             │
             ▼
        server.py ◄── static/index.html
             │
             ▼
         main.py
```

---

### Task 1: 项目骨架搭建

**Files:**
- Create: `ai-chat-sandbox/requirements.txt`
- Create: `ai-chat-sandbox/.env.example`
- Create: `ai-chat-sandbox/src/__init__.py`
- Create: `ai-chat-sandbox/src/llm/__init__.py`
- Create: `ai-chat-sandbox/src/tools/__init__.py`

- [ ] **Step 1: 创建 requirements.txt**

```txt
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
httpx>=0.27.0
anthropic>=0.40.0
openai>=1.60.0
agent-sandbox
python-dotenv>=1.0.0
```

- [ ] **Step 2: 创建 .env.example**

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-6
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=
SANDBOX_BASE_URL=http://localhost:8080
SANDBOX_ENABLED=true
```

- [ ] **Step 3: 创建各包的 `__init__.py`**

`src/__init__.py`:
```python
```

`src/llm/__init__.py`:
```python
```

`src/tools/__init__.py`:
```python
```

- [ ] **Step 4: commit**

---

### Task 2: 配置管理 (`src/config.py`)

**Files:**
- Create: `ai-chat-sandbox/src/config.py`

- [ ] **Step 1: 实现配置类**

```python
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    llm_provider: str
    anthropic_api_key: str
    anthropic_model: str
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    sandbox_base_url: str
    sandbox_enabled: bool

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "anthropic"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            openai_base_url=os.getenv("OPENAI_BASE_URL", ""),
            sandbox_base_url=os.getenv("SANDBOX_BASE_URL", "http://localhost:8080"),
            sandbox_enabled=os.getenv("SANDBOX_ENABLED", "true").lower() == "true",
        )


config = Config.from_env()
```

- [ ] **Step 2: commit**

---

### Task 3: 工具系统基础 (`src/tools/base.py`)

**Files:**
- Create: `ai-chat-sandbox/src/tools/base.py`

- [ ] **Step 1: 实现 Tool 抽象类和 ToolRegistry**

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """工具的抽象基类，所有工具必须实现此接口。"""

    def __init__(self, name: str, description: str, parameters: dict[str, Any]):
        self.name = name
        self.description = description
        self.parameters = parameters

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """执行工具，返回结果字符串。"""
        ...

    def to_schema(self) -> dict[str, Any]:
        """生成 LLM function calling / tool use 的定义。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class ToolRegistry:
    """工具注册中心，管理所有可用工具。"""

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
```

- [ ] **Step 2: commit**

---

### Task 4: 内置工具 (`src/tools/builtin.py`)

**Files:**
- Create: `ai-chat-sandbox/src/tools/builtin.py`

- [ ] **Step 1: 实现 calculate 工具**

```python
from __future__ import annotations

import ast
import operator
from typing import Any

from .base import Tool


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


# 安全表达式求值，仅允许 AST 白名单节点
_SAFE_NODES: set[type] = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.USub, ast.UAdd,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.Constant, ast.Num,  # ast.Num for Python < 3.8 compat
    ast.Call, ast.Name, ast.Load, ast.Attribute,
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
    if isinstance(node, ast.Num):
        return node.n

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

    if isinstance(node, ast.Attribute):
        raise ValueError("不允许访问属性")

    raise ValueError(f"不支持的表达式类型：{node_type.__name__}")


def register_builtin_tools(registry: "ToolRegistry") -> None:
    """将内置工具注册到工具注册中心。"""
    registry.register(CalculateTool())
```

- [ ] **Step 2: commit**

---

### Task 5: 沙箱工具 (`src/tools/sandbox.py`)

**Files:**
- Create: `ai-chat-sandbox/src/tools/sandbox.py`

- [ ] **Step 1: 实现所有沙箱工具类**

```python
from __future__ import annotations

import asyncio
from typing import Any

from agent_sandbox import AsyncSandbox

from .base import Tool


class SandboxInfoTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="sandbox_info",
            description="获取沙箱环境信息，包括家目录路径、已安装的 Python 包列表等。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        ctx = await self._sandbox.sandbox.get_context()
        return str(ctx)


class BrowserNavigateTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_navigate",
            description="在浏览器中导航到指定 URL。使用此工具打开网页。",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要导航到的完整 URL，如 https://example.com"}
                },
                "required": ["url"],
            },
        )

    async def execute(self, url: str, **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.navigate(url=url)
        return str(result)


class BrowserScreenshotTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_screenshot",
            description="截取当前浏览器页面的截图。返回图片数据。截图为全页面截图。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.screenshot(full_page=True)
        import base64
        if hasattr(result, 'body') and result.body:
            return f"[IMAGE]data:image/png;base64,{base64.b64encode(result.body).decode('utf-8')}"
        return str(result)


class BrowserGetTextTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_get_text",
            description="获取当前页面上所有可见的文本内容。用于提取页面信息。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.get_text()
        body = result.body if hasattr(result, 'body') else result
        return str(body)[:8000]  # 截断过长文本


class BrowserGetMarkdownTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_get_markdown",
            description="将当前页面转换为 Markdown 格式。适合提取文章、文档等结构化内容。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.get_markdown()
        body = result.body if hasattr(result, 'body') else result
        return str(body)[:10000]


class BrowserGetHtmlTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_get_html",
            description="获取当前页面的 HTML 源码。仅在需要分析页面结构时使用。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.get_html()
        body = result.body if hasattr(result, 'body') else result
        return str(body)[:15000]


class BrowserClickTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_click",
            description="点击页面上的元素。可以通过 CSS 选择器或元素索引定位。",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS 选择器，如 '#submit-btn' 或 '.nav-link'"},
                    "index": {"type": "integer", "description": "元素索引（用于无法用选择器定位时）"},
                },
                "required": [],
            },
        )

    async def execute(self, selector: str | None = None, index: int | None = None, **kwargs: Any) -> str:
        params = {}
        if selector:
            params["selector"] = selector
        if index is not None:
            params["index"] = index
        result = await self._sandbox.browser_page.click(**params)
        return str(result)


class BrowserFillTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_fill",
            description="在输入框中填入文本。需要提供 CSS 选择器定位输入框。",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "输入框的 CSS 选择器"},
                    "text": {"type": "string", "description": "要填入的文本"},
                },
                "required": ["selector", "text"],
            },
        )

    async def execute(self, selector: str, text: str, **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.fill(selector=selector, text=text)
        return str(result)


class BrowserScrollTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_scroll",
            description="滚动当前页面。",
            parameters={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["down", "up"],
                        "description": "滚动方向：down 向下，up 向上",
                    }
                },
                "required": [],
            },
        )

    async def execute(self, direction: str = "down", **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.scroll(direction=direction)
        return str(result)


class BrowserEvaluateTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_evaluate",
            description="在页面中执行 JavaScript 表达式并返回结果。用于提取页面数据。",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "JavaScript 表达式，如 'document.title'"}
                },
                "required": ["expression"],
            },
        )

    async def execute(self, expression: str, **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.evaluate(expression=expression)
        return str(result)


class BrowserFindTextTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_find_text",
            description="在页面中搜索指定文本，返回所有匹配位置。",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "要搜索的关键词"},
                },
                "required": ["keyword"],
            },
        )

    async def execute(self, keyword: str, **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.find_text(keyword=keyword)
        return str(result)


class BrowserWaitTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_wait",
            description="等待某个条件满足。可用于等待页面加载、元素出现或网络请求完成。",
            parameters={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["load", "network_idle", "selector", "timeout"],
                        "description": "等待类型",
                    },
                    "selector": {"type": "string", "description": "当 type 为 selector 时的 CSS 选择器"},
                    "timeout": {"type": "integer", "description": "超时时间（毫秒），默认 30000"},
                },
                "required": ["type"],
            },
        )

    async def execute(self, type: str, selector: str | None = None, timeout: int | None = None, **kwargs: Any) -> str:
        params: dict[str, Any] = {"type": type}
        if selector:
            params["selector"] = selector
        if timeout:
            params["timeout"] = timeout
        result = await self._sandbox.browser_page.wait(**params)
        return str(result)


class BrowserBackTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_back",
            description="返回浏览器历史记录的上一页。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.back()
        return str(result)


class BrowserReloadTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_reload",
            description="刷新当前页面。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._sandbox.browser_page.reload()
        return str(result)


class BrowserTabsListTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_tabs_list",
            description="列出所有打开的浏览器标签页。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._sandbox.browser_tabs.list()
        return str(result)


class BrowserTabsCreateTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="browser_tabs_create",
            description="创建一个新的浏览器标签页。",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs: Any) -> str:
        result = await self._sandbox.browser_tabs.create()
        return str(result)


class BrowserTabsActivateTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
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
        result = await self._sandbox.browser_tabs.activate(index=index)
        return str(result)


class ShellExecTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
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
        result = await self._sandbox.shell.exec_command(command=command)
        if hasattr(result, 'data') and hasattr(result.data, 'output'):
            return result.data.output
        return str(result)


class FileReadTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
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
        result = await self._sandbox.file.read_file(file=file)
        if hasattr(result, 'data') and hasattr(result.data, 'content'):
            return result.data.content
        return str(result)


class FileWriteTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
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
        result = await self._sandbox.file.write_file(file=file, content=content)
        return str(result)


class FileListTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
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
        result = await self._sandbox.file.list_path(path=path)
        return str(result)


class FileSearchTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
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
        result = await self._sandbox.file.search_in_file(file=file, regex=regex)
        return str(result)


class FileFindTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
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
        result = await self._sandbox.file.find_files(path=path, glob=glob)
        return str(result)


class CodePythonTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
        super().__init__(
            name="code_python",
            description="在沙箱的 Jupyter 内核中执行 Python 代码。用于数据处理、计算等。代码中的 print 输出将被返回。",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python 代码"},
                },
                "required": ["code"],
            },
        )

    async def execute(self, code: str, **kwargs: Any) -> str:
        result = await self._sandbox.code.execute_code(language="python", code=code)
        return str(result)


class CodeJavaScriptTool(Tool):
    def __init__(self, sandbox: AsyncSandbox):
        self._sandbox = sandbox
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
        result = await self._sandbox.code.execute_code(language="javascript", code=code)
        return str(result)


def register_sandbox_tools(registry: "ToolRegistry", sandbox_base_url: str) -> "ToolRegistry":
    """创建并注册所有沙箱工具。返回传入的 registry 以便链式调用。"""
    import asyncio
    sandbox = AsyncSandbox(base_url=sandbox_base_url)

    tools: list[Tool] = [
        SandboxInfoTool(sandbox),
        BrowserNavigateTool(sandbox),
        BrowserScreenshotTool(sandbox),
        BrowserGetTextTool(sandbox),
        BrowserGetMarkdownTool(sandbox),
        BrowserGetHtmlTool(sandbox),
        BrowserClickTool(sandbox),
        BrowserFillTool(sandbox),
        BrowserScrollTool(sandbox),
        BrowserEvaluateTool(sandbox),
        BrowserFindTextTool(sandbox),
        BrowserWaitTool(sandbox),
        BrowserBackTool(sandbox),
        BrowserReloadTool(sandbox),
        BrowserTabsListTool(sandbox),
        BrowserTabsCreateTool(sandbox),
        BrowserTabsActivateTool(sandbox),
        ShellExecTool(sandbox),
        FileReadTool(sandbox),
        FileWriteTool(sandbox),
        FileListTool(sandbox),
        FileSearchTool(sandbox),
        FileFindTool(sandbox),
        CodePythonTool(sandbox),
        CodeJavaScriptTool(sandbox),
    ]
    registry.register_many(tools)
    return registry
```

- [ ] **Step 2: commit**

---

### Task 6: LLM 基础接口 (`src/llm/base.py`)

**Files:**
- Create: `ai-chat-sandbox/src/llm/base.py`

- [ ] **Step 1: 实现 LLM 基类和响应类型**

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Literal


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    type: Literal["text", "tool_calls"]
    text: str | None = None
    tool_calls: list[ToolCall] | None = None


class BaseLLM(ABC):
    """LLM 提供者的抽象基类。"""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """发送消息并获取响应。返回文本或工具调用。"""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncGenerator[str | LLMResponse, None]:
        """流式发送消息。逐个 yield 文本片段，最后 yield LLMResponse。"""
        ...
```

- [ ] **Step 2: commit**

---

### Task 7: Anthropic LLM 实现 (`src/llm/anthropic_llm.py`)

**Files:**
- Create: `ai-chat-sandbox/src/llm/anthropic_llm.py`

- [ ] **Step 1: 实现 Anthropic LLM**

```python
from __future__ import annotations

from typing import Any, AsyncGenerator

from anthropic import AsyncAnthropic

from .base import BaseLLM, LLMResponse, ToolCall


class AnthropicLLM(BaseLLM):
    """Anthropic Claude 的 LLM 实现。"""

    def __init__(self, model: str, api_key: str):
        super().__init__(model)
        self._client = AsyncAnthropic(api_key=api_key)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        system = _extract_system(messages)
        formatted = _format_messages(messages)

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
    ) -> AsyncGenerator[str | LLMResponse, None]:
        system = _extract_system(messages)
        formatted = _format_messages(messages)
        anthropic_tools = _to_anthropic_tools(tools) if tools else None

        async with self._client.messages.stream(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=formatted,
            tools=anthropic_tools or None,
        ) as stream:
            text_content = ""
            tool_use_blocks: dict[str, dict[str, Any]] = {}

            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        text_content += event.delta.text
                        yield event.delta.text
                    elif event.delta.type == "input_json_delta":
                        # tool_use 的增量参数暂存，不流式输出
                        pass

            # 获取最终的 message 判断是否有 tool_use
            final = await stream.get_final_message()

        # 收集所有 tool_use blocks
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


def _extract_system(messages: list[dict[str, Any]]) -> str:
    for msg in messages:
        if msg["role"] == "system":
            return msg["content"]
    return ""


def _format_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in messages if m["role"] != "system"]


def _to_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for t in tools:
        result.append({
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["input_schema"],
        })
    return result


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
```

- [ ] **Step 2: commit**

---

### Task 8: OpenAI LLM 实现 (`src/llm/openai_llm.py`)

**Files:**
- Create: `ai-chat-sandbox/src/llm/openai_llm.py`

- [ ] **Step 1: 实现 OpenAI LLM**

```python
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from .base import BaseLLM, LLMResponse, ToolCall


class OpenAILLM(BaseLLM):
    """OpenAI GPT 的 LLM 实现，也兼容 MiniMax 等 OpenAI 兼容 API。"""

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
    ) -> AsyncGenerator[str | LLMResponse, None]:
        openai_tools = _to_openai_tools(tools) if tools else None

        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=openai_tools or None,
            stream=True,
        )

        text_content = ""
        tool_calls_acc: dict[int, dict[str, Any]] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            if delta.content:
                text_content += delta.content
                yield delta.content

            if delta.tool_calls:
                for tc in delta.tool_calls:
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
            yield LLMResponse(type="tool_calls", tool_calls=tool_calls)
        else:
            yield LLMResponse(type="text", text=text_content)


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

    if message.tool_calls:
        tool_calls = []
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return LLMResponse(type="tool_calls", tool_calls=tool_calls)

    return LLMResponse(type="text", text=message.content or "")
```

- [ ] **Step 2: commit**

---

### Task 9: 会话管理 (`src/session.py`)

**Files:**
- Create: `ai-chat-sandbox/src/session.py`

- [ ] **Step 1: 实现会话管理器**

```python
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def add_message(self, role: str, content: Any) -> None:
        self.messages.append({"role": role, "content": content})

    def touch(self) -> None:
        self.created_at = time.time()


class SessionManager:
    """内存会话管理器。"""

    def __init__(self, ttl_seconds: int = 1800):
        self._sessions: dict[str, Session] = {}
        self._ttl = ttl_seconds

    def get_or_create(self, session_id: str | None = None) -> Session:
        self._cleanup()
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            session.touch()
            return session

        new_id = session_id or uuid.uuid4().hex[:12]
        session = Session(session_id=new_id)
        self._sessions[new_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        self._cleanup()
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _cleanup(self) -> None:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now - s.created_at > self._ttl]
        for sid in expired:
            del self._sessions[sid]


# 全局单例
session_manager = SessionManager()
```

- [ ] **Step 2: commit**

---

### Task 10: Agent Loop (`src/agent.py`)

**Files:**
- Create: `ai-chat-sandbox/src/agent.py`

- [ ] **Step 1: 实现 Agent Loop**

```python
from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator

from .config import config
from .llm.base import BaseLLM, LLMResponse
from .llm.anthropic_llm import AnthropicLLM
from .llm.openai_llm import OpenAILLM
from .session import Session
from .tools.base import ToolRegistry
from .tools.builtin import register_builtin_tools
from .tools.sandbox import register_sandbox_tools


MAX_ITERATIONS = 15


def create_llm() -> BaseLLM:
    """根据配置创建 LLM 实例。"""
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
    """创建并配置工具注册中心。"""
    registry = ToolRegistry()
    register_builtin_tools(registry)
    if config.sandbox_enabled:
        register_sandbox_tools(registry, config.sandbox_base_url)
    return registry


async def agent_loop(
    session: Session,
    user_message: str,
    llm: BaseLLM | None = None,
    registry: ToolRegistry | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Agent 主循环：与 LLM 交互，执行工具调用。

    Yields dicts:
        {"type": "text", "content": "..."}
        {"type": "tool_start", "tool": "...", "args": {...}}
        {"type": "tool_end", "tool": "...", "result": "..."}
        {"type": "image", "src": "data:image/png;base64,..."}
        {"type": "error", "message": "..."}
    """
    if llm is None:
        llm = create_llm()
    if registry is None:
        registry = create_tool_registry()

    session.add_message("user", user_message)

    system_prompt = """你是一个有用的 AI 助手。你可以进行普通对话，也可以在需要时使用工具来完成用户的任务。

使用工具时：
- 仔细理解用户需求，选择合适的工具
- 如果需要多步操作，逐步执行并在上一步完成后根据结果决定下一步
- 当截图工具返回 [IMAGE] 前缀的数据时，请在你的回复中用 [IMAGE]data:image/png;base64,... 标记来展示图片
- 如果你完成用户的任务，直接回文本总结，不需要再调用工具

当前可用的沙箱工具可以帮你操作浏览器、执行命令、读写文件、运行代码等。"""

    session.messages.insert(0, {"role": "system", "content": system_prompt})

    tool_schemas = registry.get_schemas()

    for iteration in range(MAX_ITERATIONS):
        response = await llm.chat(session.messages, tool_schemas)

        if response.type == "text":
            text = response.text or ""
            # 检查是否包含图片标记
            if "[IMAGE]" in text:
                parts = text.split("[IMAGE]")
                for i, part in enumerate(parts):
                    if i == 0:
                        if part.strip():
                            yield {"type": "text", "content": part}
                    else:
                        # 取 data:... 直到空白或结尾
                        img_data = part.split()[0] if part.strip() else ""
                        img_data = img_data.strip()
                        if img_data.startswith("data:image/"):
                            yield {"type": "image", "src": img_data}
                        rest = part[len(img_data):].strip()
                        if rest:
                            yield {"type": "text", "content": rest}
            else:
                yield {"type": "text", "content": text}

            session.add_message("assistant", text)
            return

        if response.type == "tool_calls":
            tool_results = []
            for tc in response.tool_calls:
                yield {"type": "tool_start", "tool": tc.name, "args": tc.arguments}

                result = await registry.execute(tc.name, **tc.arguments)
                tool_results.append((tc, result))

                # 检查是否包含图片
                if result.startswith("[IMAGE]"):
                    img_src = result[7:]  # 去掉 [IMAGE] 前缀
                    yield {"type": "image", "src": img_src}
                    result_summary = "[截图已获取]"
                else:
                    result_summary = result[:200] + ("..." if len(result) > 200 else "")

                yield {"type": "tool_end", "tool": tc.name, "result": result_summary}

            # 将助手消息（含 tool_use）和工具结果添加到对话
            assistant_content = []
            for tc, result in tool_results:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            session.messages.append({"role": "assistant", "content": assistant_content})

            for tc, result in tool_results:
                session.messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": result,
                    }],
                })

    # 超过最大迭代次数
    yield {"type": "error", "message": f"Agent 执行超过 {MAX_ITERATIONS} 轮，已中止。请简化你的请求。"}
```

- [ ] **Step 2: commit**

---

### Task 11: FastAPI 服务端 (`src/server.py`)

**Files:**
- Create: `ai-chat-sandbox/src/server.py`

- [ ] **Step 1: 实现 FastAPI 应用和 API 端点**

```python
from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import agent_loop
from .session import session_manager


class ChatRequest(BaseModel):
    message: str


app = FastAPI(title="AI Chat Sandbox")


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.post("/api/chat")
async def chat(req: ChatRequest, session_id: str = Query(default="")):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    session_id = session_id or None
    session = session_manager.get_or_create(session_id)

    async def _stream():
        try:
            async for event in agent_loop(session, req.message):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session.session_id,
        },
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 2: commit**

---

### Task 12: 前端聊天界面 (`static/index.html`)

**Files:**
- Create: `ai-chat-sandbox/static/index.html`

- [ ] **Step 1: 实现聊天 UI**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Chat Sandbox</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #e0e0e0; height: 100vh; display: flex; flex-direction: column; }
.header { background: #16213e; padding: 12px 20px; border-bottom: 1px solid #0f3460; font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.header .dot { width: 10px; height: 10px; border-radius: 50%; background: #00c853; }
.messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.msg { max-width: 80%; padding: 12px 16px; border-radius: 12px; line-height: 1.6; word-break: break-word; }
.msg.user { align-self: flex-end; background: #0f3460; }
.msg.assistant { align-self: flex-start; background: #16213e; border: 1px solid #0f3460; }
.msg img { max-width: 100%; border-radius: 8px; margin-top: 8px; }
.tool-indicator { align-self: flex-start; font-size: 12px; color: #888; padding: 4px 12px; background: #1a1a2e; border-radius: 16px; border: 1px solid #333; display: flex; align-items: center; gap: 6px; }
.tool-indicator .spinner { width: 12px; height: 12px; border: 2px solid #333; border-top: 2px solid #00c853; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.input-area { padding: 16px 20px; background: #16213e; border-top: 1px solid #0f3460; display: flex; gap: 10px; }
.input-area input { flex: 1; padding: 10px 16px; border-radius: 24px; border: 1px solid #0f3460; background: #1a1a2e; color: #e0e0e0; font-size: 14px; outline: none; }
.input-area input:focus { border-color: #00c853; }
.input-area button { padding: 10px 20px; border-radius: 24px; border: none; background: #00c853; color: #1a1a2e; font-weight: 600; cursor: pointer; font-size: 14px; }
.input-area button:hover { background: #00e676; }
.input-area button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
</head>
<body>
<div class="header"><span class="dot"></span>AI Chat Sandbox</div>
<div class="messages" id="messages"></div>
<div class="input-area">
  <input id="input" type="text" placeholder="输入消息，如：打开163.com并截图..." autofocus>
  <button id="send" onclick="send()">发送</button>
</div>
<script>
const msgs = document.getElementById('messages');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');

let sessionId = new URLSearchParams(location.search).get('session_id') || '';
if (sessionId) {
  const url = new URL(location);
  url.searchParams.set('session_id', sessionId);
  history.replaceState(null, '', url);
}

function addBubble(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div;
}

function addImage(src) {
  const div = document.createElement('div');
  div.className = 'msg assistant';
  const img = document.createElement('img');
  img.src = src;
  img.onclick = () => window.open(src);
  img.style.cursor = 'pointer';
  div.appendChild(img);
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div;
}

function addToolIndicator(tool, status) {
  const div = document.createElement('div');
  div.className = 'tool-indicator';
  if (status === 'start') {
    div.innerHTML = '<span class="spinner"></span> 正在执行: ' + tool;
    div.id = 'tool-' + tool;
  } else {
    const existing = document.getElementById('tool-' + tool);
    if (existing) {
      existing.innerHTML = '✓ ' + tool + ' 已完成';
      setTimeout(() => existing.remove(), 3000);
    }
  }
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function scrollBottom() {
  msgs.scrollTop = msgs.scrollHeight;
}

async function send() {
  const text = input.value.trim();
  if (!text) return;

  addBubble('user', text);
  input.value = '';
  sendBtn.disabled = true;

  const bubble = addBubble('assistant', '');
  let fullText = '';

  try {
    const resp = await fetch('/api/chat?session_id=' + encodeURIComponent(sessionId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });

    if (!resp.ok) throw new Error('HTTP ' + resp.status);

    // Get session_id from response header
    const newSessionId = resp.headers.get('X-Session-Id');
    if (newSessionId && !sessionId) {
      sessionId = newSessionId;
      const url = new URL(location);
      url.searchParams.set('session_id', sessionId);
      history.replaceState(null, '', url);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (!data) continue;

        try {
          const event = JSON.parse(data);
          switch (event.type) {
            case 'text':
              fullText += event.content;
              bubble.textContent = fullText;
              scrollBottom();
              break;
            case 'image':
              addImage(event.src);
              break;
            case 'tool_start':
              addToolIndicator(event.tool, 'start');
              break;
            case 'tool_end':
              addToolIndicator(event.tool, 'end');
              break;
            case 'error':
              bubble.textContent = '错误: ' + event.message;
              bubble.style.color = '#ff5252';
              break;
            case 'done':
              break;
          }
        } catch (e) {
          console.warn('SSE parse error:', e);
        }
      }
    }
  } catch (err) {
    bubble.textContent = '请求失败: ' + err.message;
    bubble.style.color = '#ff5252';
  } finally {
    sendBtn.disabled = false;
    if (!fullText.trim()) bubble.textContent = '(空响应)';
    input.focus();
  }
}

input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
</script>
</body>
</html>
```

- [ ] **Step 2: commit**

---

### Task 13: 入口文件 (`main.py`)

**Files:**
- Create: `ai-chat-sandbox/main.py`

- [ ] **Step 1: 实现入口**

```python
"""AI Chat Sandbox — 启动入口"""

import uvicorn


def main():
    uvicorn.run(
        "src.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: commit**

---

### Task 14: 冒烟测试与验证

- [ ] **Step 1: 安装依赖**

```bash
cd /data1/root/sandbox1/ai-chat-sandbox && pip install -r requirements.txt
```

- [ ] **Step 2: 验证导入**

```bash
cd /data1/root/sandbox1/ai-chat-sandbox && python -c "
from src.config import config
from src.tools.base import Tool, ToolRegistry
from src.tools.builtin import CalculateTool, register_builtin_tools
from src.llm.base import BaseLLM, LLMResponse, ToolCall
from src.session import Session, SessionManager
print('All imports OK')
"
```
Expected: `All imports OK`

- [ ] **Step 3: 运行单元测试**

```bash
cd /data1/root/sandbox1/ai-chat-sandbox && python -c "
import asyncio
from src.tools.base import ToolRegistry
from src.tools.builtin import CalculateTool, register_builtin_tools

# Test registry
registry = ToolRegistry()
register_builtin_tools(registry)
schemas = registry.get_schemas()
assert len(schemas) == 1
assert schemas[0]['name'] == 'calculate'
print('Registry OK')

# Test calculate
async def test():
    result = await registry.execute('calculate', expression='2+3*4')
    assert '14' in result, f'Expected 14, got {result}'
    print(f'Calculate OK: 2+3*4 = {result}')

    result = await registry.execute('calculate', expression='invalid***')
    assert '错误' in result or 'Error' in result
    print(f'Error handling OK: {result}')

    result = await registry.execute('nonexistent', x=1)
    assert '未找到' in result
    print(f'Missing tool OK: {result}')

asyncio.run(test())
print('All tests passed')
"
```
Expected: All tests pass

- [ ] **Step 4: 启动服务冒烟测试**

```bash
# 在后台启动服务
cd /data1/root/sandbox1/ai-chat-sandbox && timeout 5 python -c "
import uvicorn
uvicorn.run('src.server:app', host='0.0.0.0', port=8000)
" 2>&1 || true
```
Expected: server starts without import errors

- [ ] **Step 5: commit**
```

---

## 自审检查

1. **Spec coverage:**
   - LLM 统一接口 → Task 6-8
   - Anthropic tool use → Task 7
   - OpenAI function calling → Task 8
   - Tool Registry → Task 3
   - 内置工具 → Task 4
   - 沙箱工具(24个) → Task 5
   - Agent Loop → Task 10
   - FastAPI SSE API → Task 11
   - 前端聊天 UI → Task 12
   - 会话管理 → Task 9
   - 配置管理 → Task 2
   - .env → Task 1

2. **Placeholder scan:** 无 TBD/TODO，所有步骤包含实际代码

3. **Type consistency:**
   - `Tool.name/description/parameters` → 在 Task 3 定义，Task 4,5 使用
   - `ToolRegistry.register/register_many/get_schemas/execute` → Task 3 定义，Task 10 使用
   - `BaseLLM.chat/chat_stream` → Task 6 定义，Task 7,8 实现，Task 10 使用
   - `LLMResponse.type/text/tool_calls` → Task 6 定义，全链路一致
   - `Session/session_manager` → Task 9 定义，Task 11 使用
