from __future__ import annotations

from pathlib import Path
from shutil import copy2

from whimbox.common.path_lib import ASSETS_PATH, CONFIG_PATH


AGENT_WORKSPACE_TEMPLATE_DIR = Path(ASSETS_PATH) / "agent_workspace_template"


class AgentWorkspace:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path(CONFIG_PATH) / "agent_workspace")
        self.memory_dir = self.root / "memory"
        self.sessions_dir = self.root / "sessions"
        self.skills_dir = self.root / "skills"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._copy_missing_from_template()

    def _copy_missing_from_template(self) -> None:
        if not AGENT_WORKSPACE_TEMPLATE_DIR.exists():
            raise FileNotFoundError(
                f"agent workspace 模板目录不存在: {AGENT_WORKSPACE_TEMPLATE_DIR}"
            )

        for template_path in AGENT_WORKSPACE_TEMPLATE_DIR.rglob("*"):
            relative_path = template_path.relative_to(AGENT_WORKSPACE_TEMPLATE_DIR)
            target_path = self.root / relative_path

            if template_path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            if not target_path.exists():
                copy2(template_path, target_path)
