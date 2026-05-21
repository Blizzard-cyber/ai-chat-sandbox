# AI 聊天沙箱系统 — 设计文档

## 概述

一个基于 Web 的 AI 聊天应用。用户通过自然语言发送请求，由 LLM 驱动的 Agent Loop 解析意图，并在需要时调用 AIO Sandbox 的各项能力（浏览器、Shell、文件、代码执行）来完成任务。结果通过 SSE 流式推送至聊天界面，支持文本和图片展示。

## 架构设计

```
┌────────────────────────────────────────────┐
│              聊天界面 (HTML/CSS/JS)         │
│           SSE 流式接收，对话气泡             │
└──────────────────┬─────────────────────────┘
                   │ POST /api/chat (SSE)
┌──────────────────▼─────────────────────────┐
│           FastAPI 后端 (async)              │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │           Agent Loop                  │   │
│  │  while True:                          │   │
│  │    response = await llm.chat(         │   │
│  │      messages, tools)                 │   │
│  │    if 文本: 流式输出 → 结束            │   │
│  │    if 工具调用: 执行 → 结果送回 LLM    │   │
│  └──────────┬───────────────────────────┘   │
│             │                                │
│  ┌──────────▼───────────────────────────┐   │
│  │           工具注册中心                  │   │
│  │  - 内置工具 (搜索、计算等)              │   │
│  │  - 沙箱工具 (浏览器/Shell/文件/代码)    │   │
│  └──────────┬───────────────────────────┘   │
│             │                                │
│  ┌──────────▼───────────────────────────┐   │
│  │         LLM 提供者接口                  │   │
│  │  AnthropicClaude | OpenAIGPT           │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
                   │ HTTP (AsyncSandbox SDK)
┌──────────────────▼─────────────────────────┐
│         AIO Sandbox 容器                    │
│  Browser | Shell | File | Jupyter | Nodejs  │
│  (统一文件系统，共享工作目录)                │
└─────────────────────────────────────────────┘
```

## 组件设计

### 1. LLM 提供者接口 (`src/llm/`)

统一的 LLM 调用接口，屏蔽不同厂商的实现差异。

```python
class BaseLLM(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict]
    ) -> LLMResponse:
        """发送消息，返回文本或工具调用。"""
        ...

class LLMResponse:
    type: Literal["text", "tool_calls"]
    text: str | None
    tool_calls: list[ToolCall] | None
```

具体实现：
- `AnthropicLLM` — 使用 `anthropic` SDK，走 Messages API + tool use
- `OpenAILLM` — 使用 `openai` SDK，走 Chat Completions + function calling

通过环境变量 `LLM_PROVIDER=anthropic|openai` 切换。

### 2. 工具注册中心 (`src/tools/`)

```python
class Tool(ABC):
    name: str              # 工具唯一标识
    description: str       # 描述，供 LLM 理解用途
    parameters: dict       # JSON Schema，供 LLM 生成调用参数

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """执行工具，返回结果字符串。"""
        ...

class ToolRegistry:
    def register(self, tool: Tool): ...
    def get_schemas(self) -> list[dict]: ...   # 生成 LLM tool definitions
    async def execute(self, name: str, **kwargs) -> str: ...
```

#### 内置工具（始终可用）

| 工具名 | 说明 |
|--------|------|
| `calculate` | 执行数学表达式计算 |

内置工具不依赖沙箱，Agent 始终可以调用。如需新增通用工具（如网页搜索），只需实现 `Tool` 接口并注册即可。

#### 沙箱工具（需配置 SANDBOX_BASE_URL）

沙箱工具是 AIO Sandbox Python SDK (`AsyncSandbox`) 的封装，仅在 `SANDBOX_ENABLED=true` 时注册。

**浏览器操作：**

| 工具名 | SDK 调用 | 说明 |
|--------|----------|------|
| `browser_navigate` | `browser_page.navigate(url=...)` | 导航到指定 URL |
| `browser_screenshot` | `browser_page.screenshot()` | 截取页面截图，返回 base64 图片 |
| `browser_get_text` | `browser_page.get_text()` | 提取页面可见文本 |
| `browser_get_markdown` | `browser_page.get_markdown()` | 将页面转为 Markdown 格式 |
| `browser_get_html` | `browser_page.get_html()` | 获取页面 HTML 源码 |
| `browser_click` | `browser_page.click(selector=..., index=...)` | 点击元素（支持选择器或索引） |
| `browser_fill` | `browser_page.fill(selector=..., text=...)` | 填充输入框 |
| `browser_scroll` | `browser_page.scroll(direction=...)` | 滚动页面 |
| `browser_evaluate` | `browser_page.evaluate(expression=...)` | 执行 JavaScript 并返回结果 |
| `browser_find_text` | `browser_page.find_text(keyword=...)` | 在页面中搜索文本 |
| `browser_wait` | `browser_page.wait(type=..., timeout=...)` | 等待元素/加载/网络空闲 |
| `browser_back` | `browser_page.back()` | 后退到上一页 |
| `browser_reload` | `browser_page.reload()` | 刷新当前页面 |
| `browser_tabs_list` | `browser_tabs.list()` | 列出所有打开的标签页 |
| `browser_tabs_create` | `browser_tabs.create()` | 新建标签页 |
| `browser_tabs_activate` | `browser_tabs.activate(index=...)` | 切换到指定标签页 |

**Shell 操作：**

| 工具名 | SDK 调用 | 说明 |
|--------|----------|------|
| `shell_exec` | `shell.exec_command(command=...)` | 在沙箱中执行 Shell 命令 |

**文件操作：**

| 工具名 | SDK 调用 | 说明 |
|--------|----------|------|
| `file_read` | `file.read_file(file=...)` | 读取文件内容 |
| `file_write` | `file.write_file(file=..., content=...)` | 将内容写入文件 |
| `file_list` | `file.list_path(path=...)` | 列出目录下的文件 |
| `file_search` | `file.search_in_file(file=..., regex=...)` | 在文件中搜索匹配内容 |
| `file_find` | `file.find_files(path=..., glob=...)` | 按 glob 模式查找文件 |

**代码执行：**

| 工具名 | SDK 调用 | 说明 |
|--------|----------|------|
| `code_python` | `code.execute_code(language="python", code=...)` | 执行 Python 代码（Jupyter 内核） |
| `code_javascript` | `code.execute_code(language="javascript", code=...)` | 执行 JavaScript 代码（Node.js 环境） |

**环境信息：**

| 工具名 | SDK 调用 | 说明 |
|--------|----------|------|
| `sandbox_info` | `sandbox.get_context()` | 获取沙箱环境信息（家目录、已安装包等） |

### 3. Agent Loop (`src/agent.py`)

```
while 未完成:
    response = await llm.chat(对话消息, 工具定义)

    if response 是文本:
        yield SSE("text", response.text)
        break

    if response 包含工具调用:
        for 每个工具调用:
            yield SSE("tool_start", 工具名)
            result = await registry.execute(工具调用)
            yield SSE("tool_end", 工具名, 结果摘要)
            将工具调用+结果追加到对话消息
        # 继续循环 — LLM 看到工具结果后可再次调用工具
```

关键设计要点：
- **最大迭代次数**：15 轮，防止无限循环
- **流式输出**：文本通过 SSE `text` 事件流式推送；工具执行通过 `tool_start` / `tool_end` 事件通知前端
- **错误处理**：工具执行异常作为工具返回内容送回 LLM，让 LLM 自行决定重试或告知用户
- **对话记忆**：消息数组按 `session_id` 存储在内存中，支持多轮对话上下文

### 4. API 层 (`src/server.py`)

FastAPI 应用，提供以下端点：

**POST `/api/chat`**
- Query 参数：`session_id` (str，未提供时自动生成)
- 请求体：`{"message": "打开浏览器访问163.com，截图返回今天的天气"}`
- 响应：`text/event-stream` (SSE)

SSE 事件类型：
- `text` — LLM 文本片段（流式推送）
- `tool_start` — `{"tool": "browser_navigate", "args": {...}}`
- `tool_end` — `{"tool": "browser_navigate", "result_summary": "..."}`
- `image` — `{"src": "data:image/png;base64,...", "alt": "截图"}`
- `error` — `{"message": "错误信息"}`
- `done` — 流结束标记

**GET `/`** — 返回聊天界面静态页面

### 5. 前端界面 (`static/index.html`)

单页聊天界面，纯 HTML/CSS/JS：
- 对话气泡布局（用户消息靠右，AI 消息靠左）
- AI 消息支持文字渲染
- 截图等图片以内联 base64 方式展示
- 工具执行提示（可折叠，显示正在执行的工具名称）
- 会话 ID 存储在 URL 参数中，支持刷新后恢复
- 消息自动滚动至底部

### 6. 会话管理 (`src/session.py`)

简易内存存储：

```python
class Session:
    session_id: str
    messages: list[dict]       # 完整对话历史
    created_at: datetime
    sandbox_client: AsyncSandbox | None
```

v1 版本不持久化到数据库。会话空闲 30 分钟后自动清除。

## 数据流示例

用户发送："打开163.com并截图"

1. 前端发送 `POST /api/chat {"message": "打开163.com并截图"}`
2. Agent Loop 第 1 轮：LLM 决定调用 `browser_navigate(url="https://163.com")`
3. 工具注册中心通过 `AsyncSandbox.browser_page.navigate(url="https://163.com")` 执行
4. 结果返回 LLM："Page navigated successfully"
5. Agent Loop 第 2 轮：LLM 调用 `browser_wait(type="network_idle")`
6. 沙箱等待网络空闲
7. Agent Loop 第 3 轮：LLM 调用 `browser_screenshot()`
8. 返回结果包含 base64 图片数据
9. Agent Loop 第 4 轮：LLM 用文字描述结果，附带图片标记
10. SSE 将文字和图片流向客户端
11. 聊天界面渲染消息和截图

## 配置说明

通过 `.env` 文件配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `anthropic` | LLM 提供商：`anthropic` 或 `openai` |
| `ANTHROPIC_API_KEY` | — | Anthropic API 密钥 |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Anthropic 模型 ID |
| `OPENAI_API_KEY` | — | OpenAI API 密钥 |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI 模型 ID |
| `OPENAI_BASE_URL` | — | 可选的 OpenAI 兼容端点（如 MiniMax） |
| `SANDBOX_BASE_URL` | `http://localhost:8080` | AIO Sandbox 容器地址 |
| `SANDBOX_ENABLED` | `true` | 是否启用沙箱工具 |

## 项目结构

```
ai-chat-sandbox/
├── .env.example          # 环境变量模板
├── requirements.txt      # Python 依赖
├── main.py               # 入口文件：启动 uvicorn
├── src/
│   ├── __init__.py
│   ├── server.py         # FastAPI 应用 + API 端点
│   ├── agent.py          # Agent Loop (LLM + 工具编排)
│   ├── session.py        # 会话管理器
│   ├── config.py         # 环境变量配置
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py       # BaseLLM 抽象 + LLMResponse
│   │   ├── anthropic_llm.py
│   │   └── openai_llm.py
│   └── tools/
│       ├── __init__.py
│       ├── base.py       # Tool 抽象 + ToolRegistry
│       ├── builtin.py    # 内置工具（calculate）
│       └── sandbox.py    # 所有沙箱工具
├── static/
│   └── index.html        # 聊天界面
└── docs/
    └── specs/             # 设计文档
```

## 测试策略

- **单元测试**：Tool Registry、LLM 接口、Agent Loop 核心逻辑
- **集成测试**：对接真实沙箱容器的端到端工具调用
- **手动验收**：启动服务 → 打开浏览器 → 发送聊天消息 → 确认结果

## 版本范围

**v1 包含：**
- 统一 LLM 接口（Anthropic + OpenAI）
- 完整沙箱工具集（浏览器 / Shell / 文件 / 代码，共 24 个工具）
- Agent Loop 工具编排
- SSE 流式聊天 API
- 网页聊天界面（文字 + 图片）
- 内存会话管理

**v1 不包含：**
- 用户认证 / 多用户
- 持久化对话历史 / 数据库
- 文件上传
- 自定义工具插件
- 移动端响应式适配
- 多语言支持
