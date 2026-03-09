from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return normalized or "default"


@dataclass
class Session:
    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_consolidated: int = 0

    def get_history(self, max_messages: int = 100) -> list[dict[str, Any]]:
        unconsolidated = self.messages[self.last_consolidated :]
        sliced = unconsolidated[-max_messages:]
        for index, message in enumerate(sliced):
            if message.get("role") == "user":
                return [
                    {"role": item["role"], "content": item.get("content", "")}
                    for item in sliced[index:]
                    if item.get("content")
                ]
        return [
            {"role": item["role"], "content": item.get("content", "")}
            for item in sliced
            if item.get("content")
        ]

    def add_message(self, role: str, content: str, **extra: Any) -> None:
        if not content:
            return
        self.messages.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(),
                **extra,
            }
        )
        self.updated_at = datetime.now()


class SessionManager:
    def __init__(self, sessions_dir: Path) -> None:
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def _path_for(self, session_id: str) -> Path:
        return self.sessions_dir / f"{_safe_name(session_id)}.jsonl"

    def get_or_create(self, session_id: str) -> Session:
        sid = session_id or "default"
        if sid in self._cache:
            return self._cache[sid]
        session = self._load(sid) or Session(session_id=sid)
        self._cache[sid] = session
        return session

    def save(self, session: Session) -> None:
        path = self._path_for(session.session_id)
        with path.open("w", encoding="utf-8") as handle:
            metadata = {
                "_type": "metadata",
                "session_id": session.session_id,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "last_consolidated": session.last_consolidated,
            }
            handle.write(json.dumps(metadata, ensure_ascii=False) + "\n")
            for message in session.messages:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._cache[session.session_id] = session

    def _load(self, session_id: str) -> Session | None:
        path = self._path_for(session_id)
        if not path.exists():
            return None

        messages: list[dict[str, Any]] = []
        created_at = datetime.now()
        updated_at = created_at
        last_consolidated = 0

        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if item.get("_type") == "metadata":
                    if item.get("created_at"):
                        created_at = datetime.fromisoformat(item["created_at"])
                    if item.get("updated_at"):
                        updated_at = datetime.fromisoformat(item["updated_at"])
                    last_consolidated = int(item.get("last_consolidated", 0))
                    continue
                messages.append(item)

        return Session(
            session_id=session_id,
            messages=messages,
            created_at=created_at,
            updated_at=updated_at,
            last_consolidated=last_consolidated,
        )
