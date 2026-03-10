import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from whimbox.common.path_lib import CONFIG_PATH


DEFAULT_CHAT_SESSIONS_DIR = Path(CONFIG_PATH) / "agent_workspace" / "sessions"


@dataclass
class RuntimeSession:
    session_id: str
    state: str = "IDLE"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    name: str = ""
    profile: str = "default"
    window_handle: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RuntimeSessionManager:
    """Manage RPC/task runtime session state exposed to the frontend."""

    def __init__(self, persisted_sessions_dir: Path | None = None) -> None:
        self._sessions: Dict[str, RuntimeSession] = {}
        self._lock = Lock()
        self._persisted_sessions_dir = persisted_sessions_dir or DEFAULT_CHAT_SESSIONS_DIR

    def create(
        self,
        name: str = "",
        profile: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: str | None = None,
    ) -> RuntimeSession:
        resolved_session_id = session_id or f"sess_{uuid4().hex}"
        session = RuntimeSession(
            session_id=resolved_session_id,
            name=name or "",
            profile=profile or "default",
            metadata=metadata or {},
        )
        with self._lock:
            self._sessions[resolved_session_id] = session
        return session

    def find_default_session(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            for session in self._sessions.values():
                if session.name == "default" and session.profile == "default":
                    return asdict(session)
        restored = self._restore_default_session_from_persisted()
        return asdict(restored) if restored else None

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [asdict(item) for item in self._sessions.values()]

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            return asdict(session) if session else None

    def update_window(self, session_id: str, window_handle: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session.window_handle = window_handle
            return asdict(session)

    def set_state(self, session_id: str, state: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session.state = state
            return asdict(session)

    def close(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _restore_default_session_from_persisted(self) -> RuntimeSession | None:
        candidate = self._find_latest_persisted_chat_session()
        if not candidate:
            return None
        with self._lock:
            existing = self._sessions.get(candidate["session_id"])
            if existing:
                return existing
            session = RuntimeSession(
                session_id=candidate["session_id"],
                name="default",
                profile="default",
            )
            self._sessions[session.session_id] = session
        return session

    def _find_latest_persisted_chat_session(self) -> Dict[str, str] | None:
        sessions_dir = self._persisted_sessions_dir
        if not sessions_dir.exists() or not sessions_dir.is_dir():
            return None

        latest: Dict[str, str] | None = None
        latest_dt: datetime | None = None
        for path in sessions_dir.glob("*.jsonl"):
            metadata = self._read_chat_session_metadata(path)
            if not metadata:
                continue
            updated_at_raw = str(metadata.get("updated_at") or metadata.get("created_at") or "")
            session_id = str(metadata.get("session_id") or path.stem)
            if not session_id:
                continue
            try:
                updated_at = datetime.fromisoformat(updated_at_raw)
            except ValueError:
                updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if latest_dt is None or updated_at > latest_dt:
                latest_dt = updated_at
                latest = {"session_id": session_id}
        return latest

    @staticmethod
    def _read_chat_session_metadata(path: Path) -> Dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                first_line = handle.readline().strip()
        except OSError:
            return None
        if not first_line:
            return None
        try:
            data = json.loads(first_line)
        except json.JSONDecodeError:
            return None
        if data.get("_type") != "metadata":
            return None
        return data


# Backward-compatible aliases. Prefer the explicit Runtime* names in new code.
Session = RuntimeSession
SessionManager = RuntimeSessionManager

runtime_session_manager = RuntimeSessionManager()
session_manager = runtime_session_manager

