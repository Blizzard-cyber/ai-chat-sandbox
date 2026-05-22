from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from .agent import agent_loop, cancel_session, cleanup_cancel_event, create_llm, get_cancel_event
from .config import config
from .session import session_manager
from .tools.sandbox import SandboxAPI


class ChatRequest(BaseModel):
    message: str


app = FastAPI(title="AI Chat Sandbox")

# Serve static assets (js, css, images) under /static
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def cleanup_screenshots():
    """Remove leftover screenshots from previous runs."""
    _remove_session_screenshots(None)


def _remove_session_screenshots(session_id: str | None) -> None:
    """Remove screenshots for a given session, or ALL screenshots if None."""
    ss_dir = os.path.join("static", "screenshots")
    if not os.path.isdir(ss_dir):
        return
    for fname in os.listdir(ss_dir):
        if not fname.endswith(".png"):
            continue
        if session_id is not None and not fname.startswith(session_id + "_"):
            continue
        try:
            os.remove(os.path.join(ss_dir, fname))
        except OSError:
            pass


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.post("/api/chat")
async def chat(req: ChatRequest, session_id: str = Query(default="")):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    session_id_val = session_id or None
    session = session_manager.get_or_create(session_id_val)

    # Create/reset cancel event for this session
    cancel_event = get_cancel_event(session.session_id)
    cancel_event.clear()

    async def _stream():
        try:
            async for event in agent_loop(session, req.message, cancel_event=cancel_event):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'error', 'message': '请求已取消'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            cleanup_cancel_event(session.session_id)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session.session_id,
        },
    )


@app.post("/api/cancel")
async def cancel(session_id: str = Query(default="")):
    """Cancel an in-progress agent execution for the given session."""
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id 参数")

    cancelled = cancel_session(session_id)
    if cancelled:
        return {"status": "cancelled", "session_id": session_id}
    else:
        return {"status": "no_active_execution", "session_id": session_id}


@app.delete("/api/session")
async def delete_session(session_id: str = Query(default="")):
    """Delete a session and its associated screenshot files."""
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id 参数")

    session_manager.delete(session_id)
    cleanup_cancel_event(session_id)
    _remove_session_screenshots(session_id)

    return {"status": "deleted", "session_id": session_id}


@app.get("/api/config")
async def get_config():
    llm = create_llm()
    return {
        "provider": config.llm_provider,
        "model": llm.model,
        "sandbox_enabled": config.sandbox_enabled,
        "sandbox_url": config.sandbox_base_url if config.sandbox_enabled else None,
    }


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

    api = SandboxAPI(config.sandbox_base_url)

    content = await file.read()
    content_b64 = base64.b64encode(content).decode("utf-8")

    target_dir = "/home/gem/uploads"
    safe_filename = os.path.basename(file.filename)
    if not safe_filename:
        await api.close()
        raise HTTPException(status_code=400, detail="无效文件名")
    target_path = f"{target_dir}/{safe_filename}"
    try:
        await api.shell_exec(f"mkdir -p {target_dir}", timeout=5)
        await api.file_upload(target_path, content_b64)
        return {"status": "ok", "path": target_path, "filename": safe_filename, "size": len(content)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败：{e}")
    finally:
        await api.close()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
