from __future__ import annotations

from pathlib import Path

from whimbox.common.path_lib import CONFIG_PATH


DEFAULT_BOOTSTRAP_FILES = {
    "AGENTS.md": """# Agent操作准则

你是奇想盒AI游戏助手。

## 核心规则
- 先理解用户需求，再决定是否调用工具。
- 当需求与游戏自动化、任务执行相关时，优先使用当前可用工具。
- 对于工具还不支持的任务，要承认无法做到，不要强行调用不相关的工具。
- 如果工具运行失败，不要直接重试，应先询问用户意见。
""",

    "SOUL.md": """# 灵魂

你是奇想盒AI游戏助手。

## 性格

- 乐于助人，友善亲切
- 言简意赅，直奔主题
- 好奇心强，渴望学习

## 价值观
- 注重准确性而非速度
- 重视用户隐私和安全
- 行事透明

## 沟通风格
- 表达清晰直接
- 必要时解释原因
- 需要澄清时提出问题
""",

    "USER.md": """# 用户画像

在这里记录用户的长期信息，例如偏好、长期目标和沟通习惯。
""",
}


DEFAULT_SKILLS = {
    "memory": """---
name: memory
description: 双层记忆系统，支持立即写入长期记忆。
always: true
---

# Memory

## 结构

- `memory/MEMORY.md`：长期事实，例如用户偏好、项目上下文、关系信息。该文件会被加载进上下文。
- `memory/HISTORY.md`：旧对话的追加式事件归档。该文件不会直接注入上下文。

## 何时更新 MEMORY.md

当出现以下信息时，立即用 `edit_file` 或 `write_file` 写入 `MEMORY.md`：
- 用户的偏好
- 用户明确的要求
- 用户觉得重要的信息

## 自动压缩

会话变长后，旧对话会被自动总结到 `HISTORY.md`，长期事实也可能被合并进 `MEMORY.md`。你不需要管理这些。
""",
}


class AgentWorkspace:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path(CONFIG_PATH) / "agent_workspace")
        self.memory_dir = self.root / "memory"
        self.sessions_dir = self.root / "sessions"
        self.skills_dir = self.root / "skills"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        for name, content in DEFAULT_BOOTSTRAP_FILES.items():
            path = self.root / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")

        for name, content in DEFAULT_SKILLS.items():
            skill_dir = self.skills_dir / name
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                skill_file.write_text(content, encoding="utf-8")

        memory_file = self.memory_dir / "MEMORY.md"
        if not memory_file.exists():
            memory_file.write_text("# 长期记忆\n", encoding="utf-8")

        history_file = self.memory_dir / "HISTORY.md"
        if not history_file.exists():
            history_file.write_text("", encoding="utf-8")
