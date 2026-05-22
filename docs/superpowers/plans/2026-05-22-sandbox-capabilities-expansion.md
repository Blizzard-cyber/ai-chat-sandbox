# Sandbox Capabilities Expansion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand tool coverage to match AIO Sandbox's real capabilities — add Jupyter, file replace, markitdown, file upload/download, and VSCode integration.

**Architecture:** New tools follow the existing pattern (SandboxAPI method + Tool class in `sandbox.py`, registered in `register_sandbox_tools()`). The VSCode viewer and file upload button are frontend-only additions. File download uses an `[FILE_DOWNLOAD]` prefix protocol like the existing `[IMAGE]` pattern.

**Tech Stack:** Python FastAPI + JS frontend + AIO Sandbox REST API (`/v1/jupyter/execute`, `/v1/file/replace`, `/v1/file/download`, `/v1/file/upload`, MCP `markitdown`)

---

## File Change Map

| File | Change |
|------|--------|
| `src/tools/sandbox.py:55-104` | Add SandboxAPI methods: `jupyter_execute`, `file_replace`, `file_download`, `file_upload`, `mcp_call` (generic), `mcp_markitdown_call` |
| `src/tools/sandbox.py:912-946` | Add 6 new Tool classes + register them |
| `src/agent.py:438-473` | Add `[FILE_DOWNLOAD]` handling in tool result processing (parallel to `[IMAGE]`) |
| `src/agent.py:63-90` | Update system prompt with new capabilities |
| `src/server.py` | Add `POST /api/upload` endpoint for file upload |
| `static/index.html` | Add VSCode iframe view, view-switch buttons, file upload button, `file` event handler in SSE, download result card type |
| `static/js/app.js` | Add `switchSandboxView()`, file upload logic, `case 'file'` SSE handler, `addResultToCard('download', ...)` |

---

### Task 1: Add Jupyter execute tool

**Files:**
- Modify: `src/tools/sandbox.py` (add method + tool class + register)

**Step 1: Add `jupyter_execute` method to SandboxAPI**

Insert after `code_execute` method (~line 103):

```python
    # ------------------------------------------------------------------
    # jupyter
    # ------------------------------------------------------------------

    async def jupyter_execute(self, code: str, timeout: int = 60) -> dict[str, Any]:
        """Execute Python code in a persistent Jupyter kernel. Kernel state
        (variables, imports) persists across calls within the same session."""
        resp = await self._post("/v1/jupyter/execute", {"code": code, "timeout": timeout})
        return resp.get("data", resp)
```

**Step 2: Add `JupyterExecuteTool` class**

Insert before `register_sandbox_tools` (before line 912):

```python
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
        result = await self._api.jupyter_execute(code, timeout)
        outputs = result.get("outputs", [])
        text_parts = []
        for out in outputs:
            otype = out.get("type", "")
            if otype == "stream":
                text_parts.append(out.get("text", ""))
            elif otype == "text" or otype == "display_data":
                text = out.get("text", "") or ""
                # Jupyter may return rich display data; extract plain text
                text_parts.append(text)
            elif otype == "error":
                ename = out.get("ename", "Error")
                evalue = out.get("evalue", "")
                traceback = "\n".join(out.get("traceback", []))
                text_parts.append(f"[{ename}] {evalue}\n{traceback}")
        return "\n".join(text_parts) or json.dumps(result, ensure_ascii=False)
```

**Step 3: Register in `register_sandbox_tools()`**

Add to the tools list in `register_sandbox_tools`:
```python
        JupyterExecuteTool(api),
```

**Step 4: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('src/tools/sandbox.py').read()); print('OK')"`
Expected: `OK`

---

### Task 2: Add File replace tool

**Files:**
- Modify: `src/tools/sandbox.py` (add method + tool class + register)

**Step 1: Add `file_replace` method to SandboxAPI**

Insert after `file_find` method (~line 95):

```python
    async def file_replace(self, path: str, old_text: str, new_text: str) -> dict[str, Any]:
        """Replace the first occurrence of old_text with new_text in file."""
        resp = await self._post("/v1/file/replace", {
            "file": path, "old_text": old_text, "new_text": new_text,
        })
        return resp.get("data", resp)
```

**Step 2: Add `FileReplaceTool` class**

Insert before `register_sandbox_tools`:

```python
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
        self._api = api

    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        result = await self._api.file_replace(path, old_text, new_text)
        replaced = result.get("replaced", False)
        count = result.get("count", 0)
        if replaced:
            return f"已替换 {count} 处匹配"
        return "未找到匹配文本，未做任何替换"
```

**Step 3: Register**

Add to `register_sandbox_tools()`:
```python
        FileReplaceTool(api),
```

---

### Task 3: Add Markitdown convert tool

**Files:**
- Modify: `src/tools/sandbox.py` (add generic `mcp_call` + markitdown tool + register)

**Step 1: Add generic `mcp_call` to SandboxAPI**

Replace the existing `mcp_browser_call` with a generic version, then alias:

```python
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
            return content[0].get("text", "")
        return ""

    async def mcp_browser_call(self, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call the browser MCP server tool."""
        return await self.mcp_call("browser", tool_name, arguments)

    async def mcp_markitdown_call(self, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call the markitdown MCP server tool (document conversion)."""
        return await self.mcp_call("markitdown", tool_name, arguments)
```

**Step 2: Add `MarkitdownConvertTool` class**

Insert before `register_sandbox_tools`:

```python
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
        self._api = api

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
```

**Step 3: Register**

Add to `register_sandbox_tools()`:
```python
        MarkitdownConvertTool(api),
```

---

### Task 4: Add File upload/download tools & API

**Files:**
- Modify: `src/tools/sandbox.py` (add methods + tools + register)
- Modify: `src/agent.py` (add `[FILE_DOWNLOAD]` handling)
- Modify: `src/server.py` (add upload endpoint)
- Modify: `static/js/app.js` (add SSE handler + upload button logic)
- Modify: `static/index.html` (add upload button)
- Create: `static/downloads/.gitkeep`

**Step 1: Add `file_download` and `file_upload` methods to SandboxAPI**

Insert after `file_find` method (~line 95):

```python
    async def file_download(self, path: str) -> bytes:
        """Download a file from the sandbox. Returns raw bytes."""
        # URL-encode the path
        import urllib.parse
        encoded = urllib.parse.quote(path)
        return await self._get_bytes(f"/v1/file/download?file={encoded}")

    async def file_upload(self, path: str, content_b64: str) -> dict[str, Any]:
        """Upload a file to the sandbox. content_b64 is base64-encoded content."""
        resp = await self._post("/v1/file/upload", {
            "file": path, "content": content_b64, "encoding": "base64",
        })
        return resp.get("data", resp)
```

**Step 2: Add `FileDownloadTool` and `FileUploadTool` classes**

```python
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
        self._api = api

    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            raw = await self._api.file_download(path)
            import base64
            b64 = base64.b64encode(raw).decode("utf-8")
            filename = path.rsplit("/", 1)[-1] or "download"
            # Use prefix protocol so agent.py saves it for the user
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
        self._api = api

    async def execute(self, path: str, content_b64: str, **kwargs: Any) -> str:
        try:
            result = await self._api.file_upload(path, content_b64)
            return f"✅ 文件已上传到 {path}"
        except Exception as exc:
            return f"[ERROR] 上传失败：{exc}"
```

**Step 3: Handle `[FILE_DOWNLOAD]` in agent.py**

In the tool result processing block (around line 441-465), add after the `[IMAGE]` block:

```python
                elif result.startswith("[FILE_DOWNLOAD]"):
                    # Save file to static/downloads/ and yield URL
                    payload = result[15:]  # Remove prefix
                    if "|" in payload:
                        b64_data, filename = payload.split("|", 1)
                        safe_name = f"{session.session_id}_{uuid.uuid4().hex[:8]}_{filename}"
                        dl_dir = os.path.join("static", "downloads")
                        os.makedirs(dl_dir, exist_ok=True)
                        filepath = os.path.join(dl_dir, safe_name)
                        try:
                            file_bytes = base64.b64decode(b64_data)
                            with open(filepath, "wb") as f:
                                f.write(file_bytes)
                        except Exception:
                            logger.exception("Failed to save download")
                            result_for_llm = "[ERROR] 保存下载文件失败"
                        else:
                            dl_url = f"/static/downloads/{safe_name}"
                            yield {"type": "file", "src": dl_url, "name": filename}
                            result_for_llm = f"[文件已保存，用户可下载：{filename}]"
                    else:
                        result_for_llm = "[ERROR] 下载数据格式错误"
```

**Step 4: Add upload API endpoint in server.py**

Add after the config endpoint (~line 117):

```python
from fastapi import UploadFile, File, Form

@app.post("/api/upload")
async def upload_file(
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload a file from the user's machine to the sandbox."""
    if not config.sandbox_enabled:
        raise HTTPException(status_code=400, detail="沙箱未启用")
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    from .tools.sandbox import SandboxAPI
    api = SandboxAPI(config.sandbox_base_url)

    # Read file content and encode as base64
    content = await file.read()
    content_b64 = base64.b64encode(content).decode("utf-8")

    # Determine target path in sandbox
    target_dir = f"/home/gem/uploads"
    # Ensure directory exists
    await api.shell_exec(f"mkdir -p {target_dir}", timeout=5)

    target_path = f"{target_dir}/{file.filename}"
    try:
        await api.file_upload(target_path, content_b64)
        return {"status": "ok", "path": target_path, "filename": file.filename, "size": len(content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败：{e}")
    finally:
        await api.close()
```

Also add the imports at the top of server.py if not already there:
```python
import base64
from fastapi import UploadFile, File, Form
```

**Step 5: Add SSE handler for `file` event in app.js**

In the SSE switch block, after `case 'image':`:

```javascript
            case 'file':
              // Show download link in flow card
              addResultToCard('download', { src: ev.src, name: ev.name || 'download' });
              break;
```

**Step 6: Add `download` result card type in app.js**

In `addResultToCard`, after the `log` section:

```javascript
  } else if (type === 'download') {
    card.innerHTML = `
      <div class="rc-header"><span class="rc-left">📥 文件下载</span><span class="rc-right"></span></div>
      <div class="rc-body"><a href="${data.src}" target="_blank" class="dl-link" download="${esc(data.name)}">⬇️ ${esc(data.name)}</a></div>`;
  }
```

**Step 7: Add upload button in frontend**

In `static/index.html`, inside `.input-inner` (before the send button), add:

```html
      <button class="upload-btn" id="uploadBtn" onclick="document.getElementById('fileInput').click()" title="上传文件">📎</button>
      <input type="file" id="fileInput" style="display:none">
```

In `static/js/app.js`, add upload handler:

```javascript
document.getElementById('fileInput').addEventListener('change', async function(e) {
  const file = e.target.files[0];
  if (!file) return;
  if (!sessionId) {
    addNoticeBubble('请先发送一条消息建立会话后再上传文件');
    return;
  }
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('file', file);
  try {
    addNoticeBubble(`正在上传 ${file.name}...`);
    const resp = await fetch('/api/upload', { method: 'POST', body: formData });
    if (!resp.ok) throw new Error(await resp.text());
    const result = await resp.json();
    addNoticeBubble(`✅ 文件 ${result.filename} 已上传到沙箱（${(result.size / 1024).toFixed(1)}KB）`);
  } catch (err) {
    addNoticeBubble(`❌ 上传失败: ${err.message}`);
  }
  this.value = '';
});
```

**Step 8: Add CSS for download link and upload button**

In `static/index.html` CSS, add:

```css
.rc-card .rc-body .dl-link {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; background: var(--accent-light); color: var(--accent);
  border-radius: 8px; text-decoration: none; font-weight: 500; font-size: 13px;
  transition: background 0.15s;
}
.rc-card .rc-body .dl-link:hover { background: #ffe0cc; }
.upload-btn {
  background: none; border: none; color: var(--text-muted); cursor: pointer;
  font-size: 18px; padding: 4px 6px; border-radius: 4px; transition: color 0.15s;
  flex-shrink: 0; line-height: 1;
}
.upload-btn:hover { color: var(--accent); }
```

**Step 9: Create downloads directory**

```bash
mkdir -p static/downloads
touch static/downloads/.gitkeep
```

---

### Task 5: Add VSCode tab to right panel

**Files:**
- Modify: `static/index.html` (add VSCode iframe + view switch buttons + CSS)
- Modify: `static/js/app.js` (add `switchSandboxView()`)

**Step 1: Add VSCode iframe and view switch buttons in index.html**

In the right panel header (around line 1035), replace the current header with:

```html
<div class="rp-header">
  <div class="rp-header-left">
    <div class="rp-view-tabs">
      <button class="rp-view-btn active" data-view="vnc" onclick="switchSandboxView('vnc')">🖥️ 桌面</button>
      <button class="rp-view-btn" data-view="vscode" onclick="switchSandboxView('vscode')">🔧 VSCode</button>
    </div>
  </div>
  <span class="rp-size" id="panelSizeHint">60%</span>
  <div class="rp-actions">
    <button class="rp-btn" onclick="togglePanelMax()" title="最大化">⤢</button>
    <button class="rp-btn" onclick="refreshVnc()" title="刷新">🔄</button>
    <button class="rp-btn" onclick="closeRightPanel()" title="关闭">✕</button>
  </div>
</div>
```

After the VNC container, add the VSCode container:

```html
<div class="rp-vscode" id="vscodeContainer" style="display:none;">
  <iframe id="rpVscode" class="rp-vscode-frame" allow="fullscreen; clipboard-read; clipboard-write"></iframe>
</div>
```

**Step 2: Add VSCode CSS**

Add CSS:

```css
.rp-header-left { display: flex; align-items: center; gap: 8px; }
.rp-view-tabs { display: flex; gap: 2px; background: #f3f4f6; border-radius: 8px; padding: 2px; }
.rp-view-btn {
  padding: 5px 12px; border: none; border-radius: 6px; background: transparent;
  color: var(--text-secondary); font-size: 11px; cursor: pointer; transition: all 0.15s;
  white-space: nowrap;
}
.rp-view-btn:hover { color: var(--text-primary); }
.rp-view-btn.active { background: #fff; color: var(--text-primary); box-shadow: var(--shadow-sm); }
/* VSCode container */
.rp-vscode { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.rp-vscode-frame { width: 100%; flex: 1; border: none; }
```

**Step 3: Store sandbox URL globally**

Add near the top with other state variables:
```javascript
let sandboxBaseUrl = '';
```

In `loadConfig()`, add before the VNC setup:
```javascript
      sandboxBaseUrl = c.sandbox_url.replace(/\/$/, '');
```

**Step 4: Add `switchSandboxView()` in app.js**

```javascript
function switchSandboxView(view) {
  // Update button states
  document.querySelectorAll('.rp-view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  // Toggle containers
  const vnc = document.getElementById('vncContainer');
  const vscode = document.getElementById('vscodeContainer');
  const rpUrl = document.getElementById('rpUrl');
  if (vnc) vnc.style.display = view === 'vnc' ? 'flex' : 'none';
  if (vscode) vscode.style.display = view === 'vscode' ? 'flex' : 'none';
  if (rpUrl) rpUrl.style.display = view === 'vnc' ? 'block' : 'none';
  // Load VSCode URL on first switch
  if (view === 'vscode') {
    const iframe = document.getElementById('rpVscode');
    if (iframe && !iframe.src && sandboxBaseUrl) {
      iframe.src = sandboxBaseUrl + '/code-server/';
    }
    scheduleFitVncFrame();
  }
}
```

---

### Task 6: Update system prompt and empty state

**Files:**
- Modify: `src/agent.py` (system prompt)
- Modify: `static/index.html` (empty state hints)

**Step 1: Update system prompt**

Update the capabilities list in the system prompt (~line 63):

```python
SYSTEM_PROMPT = """你是 AI Chat Sandbox 助手。你可以进行普通对话，也可以在需要时调用工具操作沙箱环境（浏览器、Shell、文件、代码执行、Jupyter、文档处理）。
```

Add a note about Jupyter statefulness in the tool rules section (before or after the existing rules):

```python
6. **Jupyter 有状态** — jupyter_execute 维护内核状态（变量、导入），适合数据分析；一次性脚本用 code_python。
7. **文件传输** — 用户可上传文件到沙箱，你也可以用 file_download 将沙箱中的文件提供给用户下载。
8. **VSCode 可用** — 右侧面板可切换到 VSCode 界面进行代码编辑和开发。
```

**Step 2: Update empty state hints**

In `static/index.html`, the empty state hints were already updated in a previous session. Verify they cover the new capabilities. If `jupyter_execute` and `markitdown_convert` are new, add corresponding hints:

```html
<div class="hint" onclick="sendHint(this.textContent)">📊 用Jupyter分析一组数据（创建列表、计算统计值、画图）</div>
<div class="hint" onclick="sendHint(this.textContent)">📝 把 https://example.com 转为Markdown</div>
```

---

### Verification

1. Start server and open UI
2. Send `用Jupyter计算1加到100的和` → should use `jupyter_execute`, show result
3. Send `把 /home/gem 下的一个文件替换内容` → should use `file_replace`
4. Send `把 https://example.com 转为Markdown` → should use `markitdown_convert`
5. Upload a file via the 📎 button → should upload to sandbox, show confirmation
6. Ask to download a file → should show download link
7. Switch right panel to VSCode → should load code-server
