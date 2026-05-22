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
| 📁 **文件管理** | `POST /v1/file/*` | 读写/列目录/正则搜索/glob查找/replace编辑/上传下载 |
| 🐍 **代码执行** | `POST /v1/code/execute` | Python 和 Node.js 即时运行，带 stdout/stderr |
| 📊 **Jupyter** | `POST /v1/jupyter/execute` | 交互式 Python 执行（notebook 会话），内核状态保持 |
| 🖥️ **VSCode 视图** | code-server iframe | 右侧面板切换，`code <path>` 命令打开文件 |
| 📄 **文档转换** | MCP Markitdown | URL/HTML 转 Markdown 格式 |
| 📤 **文件上传** | `POST /api/upload` | 前端上传文件到沙箱容器 |
| 📥 **文件下载** | `POST /v1/file/download` | 沙箱文件下载到浏览器 |
| 🔄 **多 LLM 支持** | Anthropic / DeepSeek / OpenAI | provider 切换，运行时配置 |
| 🛑 **可中断** | asyncio.Event + API | 用户随时取消执行，避免死循环 |
| 🎭 **Agent Timeline** | SSE 流式事件 | 思考过程可视化：规划 → 分析(含推理) → 执行 → 观察 → 回复 |
| 🧠 **推理展示** | reasoning block | LLM 思考过程折叠展示，可展开查看 |
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
│  │  - 右侧双视图: noVNC 桌面 + VSCode (code-server) │  │
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
用户消息 ──→ ┌─────────────────────────────────────────────────────────┐
             │  Agent Loop（最多 25 轮，弹性终止）                     │
             │                                                         │
             │  ① 规划 (Planning)  ← 复杂任务预输出计划                │
             │                                                         │
             │  ② 分析 (Analyzing)                                     │
             │  ├─ LLM 判断：直接回复 or 调用工具                      │
             │  └─ 若需工具 → ③                                       │
             │                                                         │
             │  ③ 执行 (Executing)                                     │
             │  ├─ 工具调用（浏览器/Shell/文件/代码）                  │
             │  └─ 结果截断 + 上下文压缩检查                           │
             │                                                         │
             │  ④ 观察 (Observing)                                     │
             │  ├─ LLM 评估工具执行结果                                │
             │  ├─ 结果充分 → ⑤                                       │
             │  └─ 需要继续 → ② 下一轮                                │
             │                                                         │
             │  ⑤ 回复 (Responding)                                    │
             │  └─ 生成自然语言回复 ←──────────┘                       │
             └─────────────────────────────────────────────────────────┘
```

### Agent 智能增强机制

#### 沙箱强制调用

Agent Loop 在首轮迭代时检测用户消息中的关键词（如 `jupyter`、`画图`、`截图`、`打开`、`浏览器`、`shell`、`终端`、`pip` 等），若 LLM 尝试用纯文本回复而非调用工具，系统会自动插入一条强制指令，要求 LLM 调用实际工具完成操作。这确保了涉及沙箱的操作总是真实执行，而非文字描述。

#### VSCode 意图识别

系统自动识别用户请求中与 VSCode / 代码编辑相关的关键词，触发右侧面板自动切换到 VSCode 视图，无需用户手动切换。

#### 上下文压缩

- **滑动窗口压缩** — 超过 45% 上下文窗口时裁剪早期轮次，保留最近 10 组 assistant+tool 消息对
- **紧急压缩** — 超过 70% 时强制压缩并截断所有工具结果至 500 字符
- **工具结果截断** — 按工具类型设置不同截断限制（shell_exec: 2000, file_read: 3000 等）
- **Base64 隔离** — 截图 base64 数据不进入 LLM 消息，替换为 `[截图已获取]` 占位符

#### 循环防护

- **Soft limit (15 轮)** — 超过后检查进度，无进展则自动终止
- **Hard limit (25 轮)** — 绝对上限，强制停止
- **重复调用检测** — 同一调用模式在最近 4 轮中出现 ≥3 次 → 自动终止
- **用户可取消** — 每轮均检查 `cancel_event`，前端随时中断

### 浏览器控制三层降级

| 层级 | 方式 | 延迟 | 功能覆盖 | 依赖 |
|------|------|------|---------|------|
| **①** | MCP Browser 工具 | 低 | navigate, click, fill, evaluate, get_text, screenshot, scroll, back, tabs | CDP :9222 |
| **②** | REST API | 低 | screenshot `/v1/browser/screenshot`, actions `/v1/browser/actions` | Sandbox API |
| **③** | xdotool + xclip | 中 | 键盘快捷键, 地址栏输入, 剪贴板读取 | Xvnc :99 |

---

## 🛠️ 工具清单（33 个）

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

### 沙箱工具（14 个）

| 工具 | 说明 |
|------|------|
| `sandbox_info` | 获取沙箱环境信息 |
| `shell_exec` | 执行 Shell 命令 |
| `file_read` / `file_write` / `file_list` | 文件读写列目录 |
| `file_search` / `file_find` | 正则搜索 / glob 查找 |
| `file_replace` | 文本替换编辑 |
| `file_download` | 从沙箱下载文件到本地 |
| `file_upload` | 上传文件到沙箱 |
| `code_python` / `code_javascript` | 运行 Python / Node.js 代码 |
| `jupyter_execute` | Jupyter notebook 代码执行（有状态） |
| `markitdown_convert` | URL/HTML 转 Markdown |

---

## 💬 使用示例

### 浏览器沙箱

```
你 → 打开 https://news.ycombinator.com 并截图
AI → [browser_navigate → 等待加载 → browser_screenshot → 展示图片]

你 → 打开 baidu.com，搜索"人工智能"
AI → [browser_navigate → browser_fill 搜索框 → browser_click 搜索按钮 → screenshot]

你 → 打开 https://www.w3.org 查看页面主要内容
AI → [browser_navigate → browser_get_markdown → 输出内容]
```

### VSCode 开发

```
你 → 在VSCode里创建一个Python文件输出Hello World并运行
AI → [file_write 创建文件 → shell_exec "code <路径>" 在VSCode中打开 → code_python 运行]

你 → 创建一个HTML文件并预览
AI → [file_write 创建HTML → shell_exec "code <路径>" 打开 → browser_navigate 预览]
```

### 数据处理

```
你 → 用Jupyter画一个正弦波和余弦波的对比图
AI → [jupyter_execute 运行numpy/matplotlib代码 → 展示生成的图表]

你 → 分析当前目录下的Python代码行数
AI → [shell_exec find/wc统计 → 输出汇总结果]
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
│   ├── agent.py             # Agent Loop + 上下文管理 + 取消机制 + 循环检测
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
│   ├── index.html           # 聊天界面（CSS 样式完整嵌入，含 VSCode iframe）
│   ├── js/
│   │   └── app.js           # 前端逻辑（SSE 消费 / Timeline / 面板拖拽 / 视图切换）
│   ├── screenshots/         # 运行时截图保存目录（已 gitignore）
│   └── downloads/           # 文件下载保存目录（已 gitignore）
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
| `POST` | `/v1/file/replace` | 文本替换 | ✅ |
| `POST` | `/v1/file/str_replace_editor` | 结构化编辑 | — |
| `GET` | `/v1/file/download` | 文件下载 | ✅ |
| `POST` | `/v1/file/upload` | 文件上传 | ✅ |
| `GET` | `/v1/browser/info` | 浏览器信息 | ✅ |
| `GET` | `/v1/browser/screenshot` | 截图（PNG 流） | ✅ |
| `POST` | `/v1/browser/actions` | 鼠标/键盘/滚动 | ✅ |
| `POST` | `/v1/browser/config` | 分辨率设置 | — |
| `POST` | `/v1/code/execute` | Python/JS 代码执行 | ✅ |
| `POST` | `/v1/jupyter/execute` | Jupyter 代码执行 | ✅ |
| `POST` | `/v1/nodejs/execute` | Node.js 代码执行 | ✅ |
| `POST` | `/v1/util/convert_to_markdown` | HTML→Markdown | ✅ |
| `POST` | `/v1/mcp/{name}/tools/{tool}` | MCP 工具调用 | ✅ (browser, markitdown) |

### MCP 服务端点

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/v1/mcp/servers` | 列出 MCP 服务 |
| `GET` | `/v1/mcp/{name}/tools` | 列出工具 |
| `POST` | `/v1/mcp/{name}/tools/{tool}` | 调用工具 |

**预置 MCP 服务：** `browser`（21 个工具）、`markitdown`（文档转换）、`chrome_devtools`

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
