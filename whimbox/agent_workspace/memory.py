from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from whimbox.common.logger import logger


class MemoryStore:
    def __init__(self, workspace_root: Path) -> None:
        self.memory_dir = workspace_root / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"

    def get_memory_context(self) -> str:
        if not self.memory_file.exists():
            return ""
        content = self.memory_file.read_text(encoding="utf-8").strip()
        return content

    async def consolidate(
        self,
        *,
        session: Any,
        llm: Any,
        memory_window: int,
    ) -> bool:
        keep_count = max(memory_window // 2, 10)
        if len(session.messages) - session.last_consolidated < memory_window:
            return True

        old_messages = session.messages[session.last_consolidated:-keep_count]
        if not old_messages:
            return True

        current_memory = self.get_memory_context()
        transcript = "\n".join(
            f"[{item.get('timestamp', '?')[:16]}] {item.get('role', '').upper()}: {item.get('content', '')}"
            for item in old_messages
            if item.get("content")
        )

        prompt = (
            "请把下面的历史会话压缩为 JSON，且只能输出 JSON 对象。\n"
            '字段要求：{"history_entry": "字符串", "memory_update": "markdown字符串"}。\n'
            "history_entry 需要用 [YYYY-MM-DD HH:MM] 开头，memory_update 需要保留已有长期记忆并合并新增稳定信息。\n\n"
            f"当前长期记忆:\n{current_memory or '(empty)'}\n\n"
            f"待压缩会话:\n{transcript}"
        )

        try:
            response = await llm.ainvoke(prompt)
            content = self._extract_text(response)
            data = self._parse_json(content)
            history_entry = str(data.get("history_entry") or "").strip()
            memory_update = str(data.get("memory_update") or "").strip()
            if history_entry:
                with self.history_file.open("a", encoding="utf-8") as handle:
                    handle.write(history_entry.rstrip() + "\n\n")
            if memory_update:
                self.memory_file.write_text(memory_update + "\n", encoding="utf-8")
            session.last_consolidated = max(len(session.messages) - keep_count, 0)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"memory consolidation failed: {exc}")
            return False

    def _extract_text(self, response: Any) -> str:
        return str(getattr(response, "content", response))

    def _parse_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.endswith("```"):
                text = text[:-3]
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("memory response is not an object")
        if not data.get("history_entry"):
            data["history_entry"] = f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 会话已压缩归档。"
        if "memory_update" not in data:
            data["memory_update"] = self.get_memory_context()
        return data
