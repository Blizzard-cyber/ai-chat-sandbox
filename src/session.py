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

    def add_message(self, role: str, content: Any, **extra: Any) -> None:
        msg: dict[str, Any] = {"role": role, "content": content}
        msg.update({k: v for k, v in extra.items() if v})
        self.messages.append(msg)

    def touch(self) -> None:
        self.created_at = time.time()


class SessionManager:
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


session_manager = SessionManager()
