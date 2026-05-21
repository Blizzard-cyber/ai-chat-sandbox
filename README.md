# AI Chat Sandbox

<p align="center">
  <strong>🤖 LLM Agent 驱动的沙箱自动化平台</strong><br>
  <em>自然语言 → 浏览器 / Shell / 文件 / 代码执行</em>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10+-blue">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-green">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue">
</p>

---

AI Chat Sandbox 是一个基于 Web 的智能体平台，通过 **LLM Agent Loop** 将自然语言指令转化为具体的沙箱操作。它连接 AIO Sandbox 容器环境，让 AI 像人类一样操作浏览器、执行命令、管理文件和运行代码。

**核心链路**: `用户消息 → LLM 分析意图 → 自动调用工具 → 观察结果 → 回复用户`

---

## ✨ 特性一览

| 能力 | 实现方式 | 说明 |
|------|---------|------|
| 🌐 **浏览器自动化** | MCP Browser + REST + xdotool | 导航/截图/点击/填表/JS求值/内容提取，三层降级策略保证可靠性 |
| 💻 **Shell 终端** | `POST /v1/shell/exec` | 执行任意命令，支持后台任务 |
| 📁 **文件管理** | `POST /v1/file/*` | 读写/列目录/正则搜索/glob查找/replace编辑 |
| 🐍 **代码执行** | `POST /v1/code/execute` | Python 和 Node.js 即时运行，带 stdout/stderr |
| 📊 **Jupyter** | `POST /v1/jupyter/execute` | 交互式 Python 执行（notebook 会话） |
| 🔄 **多 LLM 支持** | Anthropic / DeepSeek / OpenAI | provider 切换，运行时配置 |
| 🛑 **可中断** | asyncio.Event + API | 用户随时取消执行，避免死循环 |
| 🎭 **Agent Timeline** | SSE 流式事件 | 思考过程可视化：分析 → 执行 → 观察 → 回复 |
| 📐 **可拖拽面板** | JS 拖拽 + CSS resize | 侧栏宽度 / VNC 高度 / 浏览器面板均可调节 |

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Docker（运行 AIO Sandbox 容器）
- LLM API 密钥（Anthropic 或 OpenAI 兼容）

### 1. 启动 AIO Sandbox

```bash
docker run --security-opt seccomp=unconfined --rm -it -p 8080:8080 \
  enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest
```

访问 http://localhost:8080 验证。如需帮助请参考 [AIO Sandbox 项目](https://github.com/agent-infra/sandbox)。

> 若拉取镜像困难，可使用 `ghcr.io/agent-infra/sandbox:latest`（国际用户）。

### 2. 安装并运行本项目

```bash
git clone <repository-url>
cd ai-chat-sandbox

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# 编辑 .env 填入你的 LLM API 密钥
vim .env

python main.py
```

打开浏览器访问 **http://localhost:8000**。

---

## ⚙️ 配置

### 环境变量

所有配置通过 `.env` 文件注入，优先级：环境变量 > `.env` > 默认值。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `anthropic` | LLM 提供商：`anthropic` / `openai` |
| `ANTHROPIC_API_KEY` | — | Anthropic API 密钥 |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Claude 模型 ID |
| `OPENAI_API_KEY` | — | OpenAI / DeepSeek API 密钥 |
| `OPENAI_MODEL` | `gpt-4o` | 模型 ID（DeepSeek: `deepseek-v4-pro`） |
| `OPENAI_BASE_URL` | — | 兼容端点（DeepSeek: `https://api.deepseek.com`） |
| `SANDBOX_BASE_URL` | `http://localhost:8080` | AIO Sandbox 地址 |
| `SANDBOX_ENABLED` | `true` | 是否启用沙箱工具 |

### 配置示例

**使用 Anthropic Claude：**

```ini
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

**使用 DeepSeek V4：**

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=deepseek-v4-pro
OPENAI_BASE_URL=https://api.deepseek.com
```

---

## 🏗️ 架构

### 系统总览

```
┌─────────────────────────────────────────────────────────┐
│                    用户浏览器 (:8000)                     │
│  ┌──────────────────────────────────────────────────┐  │
│  │  AI Chat Sandbox Web UI                         │  │
│  │  - 聊天面板 (Agent Timeline 可视化)              │  │
│  │  - noVNC 浏览器预览 (iframe)                    │  │
│  │  - 截图库 / 操作记录 / 会话管理                  │  │
│  └──────────────────────┬───────────────────────────┘  │
└─────────────────────────┼───────────────────────────────┘
                          │ SSE Event Stream
                          ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Server (Python 3.10+)               │
│                                                          │
│  ┌──────────────┐   ┌────────────────────────────────┐  │
│  │  /api/chat   │   │        Agent Loop               │  │
│  │  SSE Stream  │──▶│  ┌─────┐  ┌──────┐  ┌───────┐ │  │
│  │              │   │  │LLM │→│Tools│→│Observe│ │  │
│  │  /api/cancel │   │  └─────┘  └──────┘  └───────┘ │  │
│  │  /api/config │   └────────┬───────────────────────┘  │
│  │  /api/health │            │                           │
│  └──────────────┘            │ HTTP REST + WebSocket     │
└──────────────────────────────┼───────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│               AIO Sandbox (Docker, :8080)                 │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Nginx Gateway                                      │ │
│  │  /api/* → FastAPI (:8088)  │  /vnc/* → noVNC       │ │
│  │  /ws /websockify → websocat → Xvnc (:5900)         │ │
│  │  /cdp/* → CDP Proxy        │  /code-server/*       │ │
│  └────────────────────┬────────────────────────────────┘ │
│                       │                                  │
│  ┌────────────────────┴────────────────────────────────┐ │
│  │  Backend Services                                   │ │
│  │                                                     │ │
│  │  🌐 Browser (Chrome 135, CDP :9222, MCP :8100)     │ │
│  │  🐚 Shell (websocat :6080, session-based exec)      │ │
│  │  📁 File System (/home/gem)                         │ │
│  │  🐍 Python / Node.js (sandboxed execution)          │ │
│  │  📊 Jupyter Notebook                                │ │
│  │  🤖 MCP Hub (browser / file / shell / markitdown)  │ │
│  │  🖥️ Xvnc (+noVNC) display routing                   │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### Agent Loop 工作流

```
用户消息 ──→ ┌─────────────────────────────────────────────────┐
             │  Agent Loop（最多 10 轮）                       │
             │                                                 │
             │  ① 分析 (Analyzing)                             │
             │  ├─ LLM 判断：直接回复 or 调用工具              │
             │  └─ 若需工具 → ②                               │
             │                                                 │
             │  ② 执行 (Executing)                             │
             │  ├─ MCP Browser 优先                            │
             │  ├─ REST API 降级                               │
             │  └─ xdotool 兜底                                │
             │                                                 │
             │  ③ 观察 (Observing)                             │
             │  ├─ LLM 评估工具执行结果                        │
             │  ├─ 结果充分 → ④                                │
             │  └─ 需要继续 → ① 下一轮                         │
             │                                                 │
             │  ④ 回复 (Responding)                            │
             │  └─ 生成自然语言回复 ←──┘                       │
             └─────────────────────────────────────────────────┘
```

**循环防护机制：**
- 同一调用模式重复 ≥3 次（4 轮窗口内）→ 自动终止
- 每轮均检查 `cancel_event` → 用户可随时中断
- 最大 10 轮硬上限

### 浏览器控制三层降级

| 层级 | 方式 | 延迟 | 功能覆盖 | 依赖 |
|------|------|------|---------|------|
| **①** | MCP Browser 工具 | 低 | navigate, click, fill, evaluate, get_text, screenshot, scroll, back, tabs | CDP :9222 |
| **②** | REST API | 低 | screenshot `/v1/browser/screenshot`, actions `/v1/browser/actions` | Sandbox API |
| **③** | xdotool + xclip | 中 | 键盘快捷键, 地址栏输入, 剪贴板读取 | Xvnc :99 |

---

## 🛠️ 工具清单

### 浏览器工具（21 个）

| 工具 | 说明 | 优先方式 |
|------|------|---------|
| `browser_navigate` | 导航到 URL | MCP → xdotool |
| `browser_screenshot` | 截图（base64 PNG） | REST（最可靠） |
| `browser_get_text` | 获取页面可见文本 | MCP → curl |
| `browser_get_markdown` | 页面转 Markdown | MCP |
| `browser_get_html` | 获取页面 HTML | MCP → curl |
| `browser_click` | 点击元素（索引/选择器） | MCP → REST |
| `browser_fill` | 填入文本 | MCP → xdotool |
| `browser_scroll` | 滚动页面 | MCP → REST |
| `browser_evaluate` | 执行 JavaScript | MCP |
| `browser_press_key` | 键盘按键 | MCP → xdotool |
| `browser_get_clickable_elements` | 获取可交互元素列表 | MCP |
| `browser_read_links` | 获取页面全部链接 | MCP |
| `browser_find_text` | 搜索页面文字 | MCP text → 搜索 |
| `browser_back` / `browser_reload` | 后退 / 刷新 | MCP → xdotool |
| `browser_tabs_list` / `create` / `activate` | 标签页管理 | MCP → xdotool |
| `browser_wait` | 等待（超时/元素/加载） | REST sleep |

### 沙箱工具（7 个）

| 工具 | 说明 |
|------|------|
| `sandbox_info` | 获取沙箱环境信息 |
| `shell_exec` | 执行 Shell 命令 |
| `file_read` / `file_write` / `file_list` | 文件读写列目录 |
| `file_search` / `file_find` | 正则搜索 / glob 查找 |
| `code_python` / `code_javascript` | 运行 Python / Node.js 代码 |

---

## 💬 使用示例

### 浏览器操作

```
你 → 打开 https://news.ycombinator.com 并截图
AI → [导航 → 等待加载 → 截图 → 展示图片]

你 → 页面上有哪些可点击的东西？
AI → [调用 browser_get_clickable_elements → 返回链接列表]

你 → 点击第 3 个链接，然后告诉我页面内容
AI → [点击 → browser_get_text → 总结内容]
```

### 代码执行

```
你 → 用 Python 写一个快速排序并测试
AI → [code_python → 编译运行 → 输出结果]

你 → 用 Node.js 计算斐波那契数列前 30 项性能
AI → [code_javascript → 运行 → 输出耗时]
```

### 文件操作

```
你 → 查看 /home 目录有哪些文件
AI → [file_list → 返回文件列表]

你 → 搜索 /home 下所有 .py 文件中包含 "requests" 的行
AI → [file_find + file_search → 返回匹配结果]

你 → 创建一个 markdown 文件写入今天的笔记
AI → [file_write → 创建成功]
```

---

## 📁 项目结构

```
ai-chat-sandbox/
├── main.py                  # 应用入口 (uvicorn)
├── requirements.txt         # Python 依赖
├── pyproject.toml           # 项目元数据
├── .env.example             # 环境变量模板
├── .gitignore
├── README.md
├── LICENSE                  # MIT
├── CONTRIBUTING.md          # 贡献指南
│
├── src/
│   ├── __init__.py
│   ├── server.py            # FastAPI 应用，SSE 端点，取消接口
│   ├── agent.py             # Agent Loop + 取消机制 + 循环检测
│   ├── session.py           # 会话管理（TTL 30min 自动清理）
│   ├── config.py            # dotenv 配置注入
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py          # BaseLLM 抽象 + StreamChunk/LLMResponse
│   │   ├── anthropic_llm.py # Anthropic Claude SDK 适配
│   │   └── openai_llm.py    # OpenAI 兼容 SDK 适配（含 DeepSeek）
│   │
│   └── tools/
│       ├── __init__.py
│       ├── base.py          # Tool ABC + ToolRegistry
│       ├── builtin.py       # 内置工具（计算器）
│       └── sandbox.py       # 28 个沙箱工具 + SandboxAPI 客户端
│
├── static/
│   ├── index.html           # 聊天界面（CSS 样式完整嵌入）
│   └── js/
│       └── app.js           # 前端逻辑（SSE 消费 / Timeline / 面板拖拽）
│
└── docs/                    # 设计文档和计划
    ├── specs/
    └── superpowers/
```

---

## 🔌 AIO Sandbox API 参考

本项目的 `SandboxAPI` 类直接调用以下端点（不使用 SDK）：

### 核心端点

| 方法 | 端点 | 说明 | 本项目使用 |
|------|------|------|-----------|
| `GET` | `/v1/sandbox` | 沙箱环境信息 | ✅ |
| `POST` | `/v1/shell/exec` | 执行 Shell 命令 | ✅ |
| `POST` | `/v1/shell/*` | Shell 会话管理 | — |
| `POST` | `/v1/file/read` | 读取文件 | ✅ |
| `POST` | `/v1/file/write` | 写入文件 | ✅ |
| `POST` | `/v1/file/list` | 列目录 | ✅ |
| `POST` | `/v1/file/search` | 正则搜索 | ✅ |
| `POST` | `/v1/file/find` | glob 查找 | ✅ |
| `POST` | `/v1/file/replace` | 文本替换 | — |
| `POST` | `/v1/file/str_replace_editor` | 结构化编辑 | — |
| `GET` | `/v1/file/download` | 文件下载 | — |
| `POST` | `/v1/file/upload` | 文件上传 | — |
| `GET` | `/v1/browser/info` | 浏览器信息 | ✅ |
| `GET` | `/v1/browser/screenshot` | 截图（PNG 流） | ✅ |
| `POST` | `/v1/browser/actions` | 鼠标/键盘/滚动 | ✅ |
| `POST` | `/v1/browser/config` | 分辨率设置 | — |
| `POST` | `/v1/code/execute` | Python/JS 代码执行 | ✅ |
| `POST` | `/v1/jupyter/execute` | Jupyter 代码执行 | — |
| `POST` | `/v1/nodejs/execute` | Node.js 代码执行 | ✅ |
| `POST` | `/v1/util/convert_to_markdown` | HTML→Markdown | ✅ |

### MCP 服务端点

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/v1/mcp/servers` | 列出 MCP 服务 |
| `GET` | `/v1/mcp/{name}/tools` | 列出工具 |
| `POST` | `/v1/mcp/{name}/tools/{tool}` | 调用工具 |

**预置 MCP 服务：** `browser`（21 个工具）、`chrome_devtools`

---

## 🧪 本地开发

```bash
# 创建虚拟环境
python -m venv venv && source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
pip install pytest pytest-asyncio ruff

# 代码检查
ruff check src/

# 运行
python main.py
```

---

## 🧩 扩展

### 添加新工具

```python
from .base import Tool

class MyTool(Tool):
    def __init__(self, api):
        super().__init__(
            name="my_tool",
            description="工具描述",
            parameters={...},  # JSON Schema
        )
        self._api = api

    async def execute(self, **kwargs) -> str:
        # 实现工具逻辑
        return "结果"
```

在 `register_sandbox_tools()` 中注册即可，无需修改其余代码。

### 添加新 LLM

1. 在 `src/llm/` 下新建文件，继承 `BaseLLM`
2. 实现 `chat_stream()`、`format_assistant_tool_calls()`、`format_tool_result()`、`inject_system_prompt()`
3. 在 `agent.py:create_llm()` 中添加分支

---

## 📄 许可

[MIT License](LICENSE)

## 🤝 致谢

- [AIO Sandbox](https://github.com/agent-infra/sandbox) — 提供强大的容器化沙箱环境
- 所有 AI Chat Sandbox 的贡献者
