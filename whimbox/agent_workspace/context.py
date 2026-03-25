from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from whimbox.agent_workspace.memory import MemoryStore
from whimbox.agent_workspace.session import add_runtime_context, content_to_text
from whimbox.agent_workspace.skills import SkillsLoader


class ContextBuilder:
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md"]
    RUNTIME_TAG = "[Runtime Context — metadata only, not instructions]"

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.memory = MemoryStore(workspace_root)
        self.skills = SkillsLoader(workspace_root)

    def build_system_prompt(self) -> str:
        parts = [self._identity()]

        bootstrap = self._bootstrap_content()
        if bootstrap:
            parts.append(bootstrap)

        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")

        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

以下 skill 可以扩展你的能力。要使用特定 skill 时，先用 `read_file` 工具读取对应 `SKILL.md`，再遵循其中说明。

{skills_summary}""")

        return "\n\n---\n\n".join(parts)

    def build_messages(
        self,
        *,
        history: list[dict[str, Any]],
        current_message: Any,
        session_id: str,
    ) -> list[dict[str, Any]]:
        runtime = self._runtime_context(session_id, current_message)
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.build_system_prompt()}]
        for item in history:
            messages.append(
                {
                    "role": item.get("role", "user"),
                    "content": content_to_text(item.get("content", "")),
                }
            )
        messages.append(
            {
                "role": "user",
                "content": content_to_text(add_runtime_context(current_message, runtime)),
            }
        )
        return messages

    def _identity(self) -> str:
        workspace = str(self.workspace_root.resolve())
        return f"""# Whimbox

你是奇想盒AI游戏助手。

## Workspace
你的工作目录：{workspace}
- 长期记忆：{workspace}/memory/MEMORY.md（记录了重要的事实）
- 历史归档：{workspace}/memory/HISTORY.md（可使用`grep_history`工具搜索）每条记录以[YYYY-MM-DD HH:MM]开头
- skills：{workspace}/skills/<skill_name>/SKILL.md

## Guidelines
- 调用工具前先说明意图，但永远不要预判结果。
- 根据工具的返回结果进行回复，不要瞎编。
- 修改文件前先读取它。不要假设文件或目录存在。
- 如果用户的请求含糊不清，可以要求用户澄清。
- 问候、闲聊等轻松的对话场景，尽量不超过50字。
"""

    def _bootstrap_content(self) -> str:
        parts: list[str] = []
        for filename in self.BOOTSTRAP_FILES:
            path = self.workspace_root / filename
            if path.exists():
                parts.append(f"## {filename}\n\n{path.read_text(encoding='utf-8').strip()}")
        return "\n\n".join(part for part in parts if part.strip())

    def _runtime_context(self, session_id: str, current_message: Any = None) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [self.RUNTIME_TAG, f"当前时间：{now}", f"会话 ID：{session_id or 'default'}"]
        uploaded_paths = self._current_upload_paths(current_message)
        if uploaded_paths:
            lines.append("当前消息上传图片路径：")
            lines.extend(f"- {path}" for path in uploaded_paths)
        return "\n".join(lines)

    def _current_upload_paths(self, current_message: Any) -> list[str]:
        if not isinstance(current_message, list):
            return []
        paths: list[str] = []
        for item in current_message:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") != "image_file":
                continue
            path = str(item.get("path") or "").strip()
            if path:
                paths.append(path)
        return paths
