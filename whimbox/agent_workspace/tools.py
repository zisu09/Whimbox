from __future__ import annotations

import difflib
from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


def _resolve_path(workspace_root: Path, path: str) -> Path:
    root = workspace_root.resolve()
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = root / target
    resolved = target.resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError("path is outside agent workspace")
    return resolved


class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Workspace-relative path to read, for example skills/memory/SKILL.md")


class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Workspace-relative path to write")
    content: str = Field(..., description="Full file content to write")


class EditFileArgs(BaseModel):
    path: str = Field(..., description="Workspace-relative path to edit")
    old_text: str = Field(..., description="Exact existing text to replace")
    new_text: str = Field(..., description="Replacement text")


class ListDirArgs(BaseModel):
    path: str = Field(..., description="Workspace-relative directory path to inspect")


def build_workspace_tools(workspace_root: Path) -> list[StructuredTool]:
    def _read_file(path: str) -> str:
        target = _resolve_path(workspace_root, path)
        if not target.exists():
            raise FileNotFoundError(path)
        if not target.is_file():
            raise ValueError("path must be a file")
        return target.read_text(encoding="utf-8")

    def _write_file(path: str, content: str) -> str:
        target = _resolve_path(workspace_root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} chars to {target}"

    def _edit_file(path: str, old_text: str, new_text: str) -> str:
        target = _resolve_path(workspace_root, path)
        if not target.exists():
            raise FileNotFoundError(path)
        if not target.is_file():
            raise ValueError("path must be a file")

        content = target.read_text(encoding="utf-8")
        if old_text not in content:
            return _not_found_message(path, old_text, content)

        count = content.count(old_text)
        if count > 1:
            return f"Warning: old_text appears {count} times in {path}. Provide a more specific snippet."

        target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Successfully edited {target}"

    def _list_dir(path: str) -> str:
        target = _resolve_path(workspace_root, path)
        if not target.exists():
            raise FileNotFoundError(path)
        if not target.is_dir():
            raise ValueError("path must be a directory")
        items = [f"{'[dir]' if item.is_dir() else '[file]'} {item.name}" for item in sorted(target.iterdir())]
        return "\n".join(items) if items else f"Directory {path} is empty"

    return [
        StructuredTool.from_function(
            func=_read_file,
            name="read_file",
            description="Read a UTF-8 text file from the agent workspace, such as SKILL.md or MEMORY.md.",
            args_schema=ReadFileArgs,
        ),
        StructuredTool.from_function(
            func=_write_file,
            name="write_file",
            description="Write full content to a file in the agent workspace. Creates parent directories if needed.",
            args_schema=WriteFileArgs,
        ),
        StructuredTool.from_function(
            func=_edit_file,
            name="edit_file",
            description="Edit a file in the agent workspace by replacing exact old_text with new_text.",
            args_schema=EditFileArgs,
        ),
        StructuredTool.from_function(
            func=_list_dir,
            name="list_dir",
            description="List files and directories within the agent workspace.",
            args_schema=ListDirArgs,
        ),
    ]


def _not_found_message(path: str, old_text: str, content: str) -> str:
    lines = content.splitlines(keepends=True)
    old_lines = old_text.splitlines(keepends=True)
    window = max(len(old_lines), 1)

    best_ratio = 0.0
    best_start = 0
    for index in range(max(1, len(lines) - window + 1)):
        candidate = lines[index : index + window]
        ratio = difflib.SequenceMatcher(None, old_lines, candidate).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = index

    if best_ratio > 0.5:
        diff = "\n".join(
            difflib.unified_diff(
                old_lines,
                lines[best_start : best_start + window],
                fromfile="old_text (provided)",
                tofile=f"{path} (actual, line {best_start + 1})",
                lineterm="",
            )
        )
        return f"Error: old_text not found in {path}.\nBest match ({best_ratio:.0%} similar) at line {best_start + 1}:\n{diff}"
    return f"Error: old_text not found in {path}. No similar text found."
