from __future__ import annotations

import re
from pathlib import Path


class SkillsLoader:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.skills_dir = self.workspace_root / "skills"

    def list_skills(self) -> list[dict[str, str]]:
        if not self.skills_dir.exists():
            return []
        items: list[dict[str, str]] = []
        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            items.append(
                {
                    "name": skill_dir.name,
                    "path": str(skill_file),
                    "description": self._description(skill_file),
                }
            )
        return items

    def build_skills_summary(self) -> str:
        skills = self.list_skills()
        if not skills:
            return ""
        lines = ["<skills>"]
        for item in skills:
            lines.append("  <skill>")
            lines.append(f"    <name>{item['name']}</name>")
            lines.append(f"    <description>{item['description']}</description>")
            lines.append(f"    <location>{item['path']}</location>")
            lines.append("  </skill>")
        lines.append("</skills>")
        return "\n".join(lines)

    def _description(self, skill_file: Path) -> str:
        content = skill_file.read_text(encoding="utf-8")
        if content.startswith("---"):
            match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                for line in match.group(1).splitlines():
                    if line.startswith("description:"):
                        return line.split(":", 1)[1].strip().strip("'\"")
        return skill_file.parent.name
