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

- **Agent Loop** — 25 轮弹性上限（soft limit 15 轮 + hard limit 25 轮），重复调用检测自动终止
- **上下文管理** — 滑动窗口压缩（保留最近 10 组对话对），45% 阈值触发常规压缩，70% 触发紧急压缩
- **工具结果截断** — 按工具类型智能截断（shell_exec: 2000, file_read: 3000 等），默认 300 字符
- **Base64 隔离** — 截图等大块 base64 数据不进入 LLM 上下文窗口，替换为占位符
- **浏览器控制** — MCP browser tools 首选 → REST 降级 → xdotool 兜底
- **SSE 事件流** — phase(planning/analyzing/executing/observing/responding) / thinking / thinking_end / text / image / tool_start / tool_end / notice / error / done
- **取消机制** — 每会话 `asyncio.Event`，前端随时触发
