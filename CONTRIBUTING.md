# 贡献指南

感谢对 AI Chat Sandbox 的关注！

## 开发环境

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio ruff
```

## 规范

- **Python 3.10+** — 使用 `from __future__ import annotations` + 类型注解
- **异步优先** — 所有 I/O 操作用 `async/await`
- **代码检查** — 提交前运行 `ruff check src/`
- **测试** — 新增功能包含对应测试

## 提交信息格式

```
<type>: <简短描述>
```

类型: `feat` / `fix` / `refactor` / `docs` / `style` / `chore`

## 分支

```
feat/my-feature
fix/issue-description
```

## 添加工具

1. 继承 `Tool` 基类，实现 `execute(**kwargs) → str`
2. 定义 `name`、`description`、`parameters`（LLM tool schema）
3. 在 `register_*_tools()` 中注册

## 架构要点

- **Agent Loop** — 10 轮上限 + 重复调用检测自动终止
- **浏览器控制** — MCP browser tools 首选 → REST 降级 → xdotool 兜底
- **SSE 事件流** — phase / text / image / tool_start / tool_end / error
- **取消机制** — 每会话 `asyncio.Event`，前端随时触发
