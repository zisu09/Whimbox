from __future__ import annotations

import base64
import io
import json
import mimetypes
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


ContentBlock = dict[str, Any]
MessageContent = str | list[ContentBlock]
MAX_IMAGE_EDGE = 1000


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return normalized or "default"


def compose_user_content(
    text: str = "",
    attachments: list[dict[str, Any]] | None = None,
) -> MessageContent:
    normalized_text = str(text or "")
    normalized_attachments = attachments or []
    blocks: list[ContentBlock] = []
    if normalized_text.strip():
        blocks.append({"type": "text", "text": normalized_text})
    for item in normalized_attachments:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "image_file":
            continue
        path = str(item.get("path") or "").strip()
        if path:
            blocks.append({"type": "image_file", "path": path})
    if not blocks:
        return ""
    if len(blocks) == 1 and blocks[0].get("type") == "text":
        return str(blocks[0].get("text") or "")
    return blocks


def has_content(content: MessageContent | None) -> bool:
    if content is None:
        return False
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list):
        return False
    for item in content:
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("type") or "")
        if block_type == "text" and str(item.get("text") or "").strip():
            return True
        if block_type == "image_file" and str(item.get("path") or "").strip():
            return True
        if block_type == "screenshot":
            return True
    return False


def content_to_text(content: MessageContent | None, *, include_paths: bool = False) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("type") or "")
        if block_type == "text":
            text = str(item.get("text") or "")
            if text:
                parts.append(text)
        elif block_type == "image_file":
            path = str(item.get("path") or "").strip()
            if include_paths and path:
                parts.append(f"[image: {path}]")
            else:
                parts.append("[image]")
        elif block_type == "screenshot":
            parts.append("[screenshot]")
    return "\n\n".join(part for part in parts if part)


def content_to_model_content(content: MessageContent | None) -> Any:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    blocks: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("type") or "")
        if block_type == "text":
            text = str(item.get("text") or "")
            if text:
                blocks.append({"type": "text", "text": text})
        elif block_type == "image_file":
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            try:
                blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": _file_to_data_url(Path(path))},
                    }
                )
            except Exception:
                blocks.append({"type": "text", "text": "[image unavailable]"})
        elif block_type == "screenshot":
            blocks.append({"type": "text", "text": "[screenshot]"})
    if not blocks:
        return ""
    if len(blocks) == 1 and blocks[0].get("type") == "text":
        return str(blocks[0].get("text") or "")
    return blocks


def add_runtime_context(content: MessageContent, runtime: str) -> MessageContent:
    runtime_text = str(runtime or "").strip()
    if isinstance(content, str):
        if not runtime_text:
            return content
        if not content.strip():
            return runtime_text
        return f"{runtime_text}\n\n{content}"

    if not isinstance(content, list):
        return add_runtime_context(str(content), runtime_text)

    text_parts: list[str] = []
    non_text_blocks: list[ContentBlock] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "") == "text":
            text = str(item.get("text") or "")
            if text:
                text_parts.append(text)
        else:
            non_text_blocks.append(item)

    merged_text = "\n\n".join(part for part in [runtime_text, *text_parts] if part)
    result: list[ContentBlock] = []
    if merged_text:
        result.append({"type": "text", "text": merged_text})
    result.extend(non_text_blocks)
    if not result:
        return runtime_text
    if len(result) == 1 and result[0].get("type") == "text":
        return str(result[0].get("text") or "")
    return result


def _file_to_data_url(path: Path) -> str:
    target = path.expanduser().resolve()
    mime_type, _ = mimetypes.guess_type(str(target))
    if not mime_type:
        mime_type = "application/octet-stream"
    data = _read_image_bytes(target, mime_type)
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _read_image_bytes(path: Path, mime_type: str) -> bytes:
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            longest_edge = max(width, height)
            if longest_edge <= MAX_IMAGE_EDGE:
                return path.read_bytes()

            scale = MAX_IMAGE_EDGE / float(longest_edge)
            resized = image.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )
            output = io.BytesIO()
            save_format = _resolve_image_format(image, mime_type, path)
            save_options: dict[str, Any] = {}
            if save_format in {"JPEG", "JPG"}:
                if resized.mode not in {"RGB", "L"}:
                    resized = resized.convert("RGB")
                save_options["quality"] = 90
                save_format = "JPEG"
            resized.save(output, format=save_format, **save_options)
            return output.getvalue()
    except Exception:
        return path.read_bytes()


def _resolve_image_format(image: Image.Image, mime_type: str, path: Path) -> str:
    if image.format:
        return image.format.upper()
    if mime_type == "image/jpeg":
        return "JPEG"
    if mime_type == "image/png":
        return "PNG"
    if mime_type == "image/webp":
        return "WEBP"
    if mime_type == "image/gif":
        return "GIF"
    if mime_type == "image/bmp":
        return "BMP"
    return path.suffix.lstrip(".").upper() or "PNG"


@dataclass
class ChatSession:
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
                    if has_content(item.get("content"))
                ]
        return [
            {"role": item["role"], "content": item.get("content", "")}
            for item in sliced
            if has_content(item.get("content"))
        ]

    def add_message(self, role: str, content: MessageContent, **extra: Any) -> None:
        if not has_content(content):
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


class ChatSessionManager:
    """Persist agent conversation history under agent_workspace/sessions."""

    def __init__(self, sessions_dir: Path) -> None:
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, ChatSession] = {}

    def _path_for(self, session_id: str) -> Path:
        return self.sessions_dir / f"{_safe_name(session_id)}.jsonl"

    def get_or_create(self, session_id: str) -> ChatSession:
        sid = session_id or "default"
        if sid in self._cache:
            return self._cache[sid]
        session = self._load(sid) or ChatSession(session_id=sid)
        self._cache[sid] = session
        return session

    def save(self, session: ChatSession) -> None:
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

    def _load(self, session_id: str) -> ChatSession | None:
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

        return ChatSession(
            session_id=session_id,
            messages=messages,
            created_at=created_at,
            updated_at=updated_at,
            last_consolidated=last_consolidated,
        )


# Backward-compatible aliases. Prefer the explicit Chat* names in new code.
Session = ChatSession
SessionManager = ChatSessionManager
