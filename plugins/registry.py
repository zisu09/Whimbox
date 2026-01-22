from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


class ToolRegistryError(Exception):
    pass


@dataclass
class ToolSpec:
    tool_id: str
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    func: Callable[[str, Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
    plugin_id: str
    permissions: List[str]


class PluginRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        self._plugins: Dict[str, Dict[str, Any]] = {}

    def clear(self) -> None:
        self._tools.clear()
        self._plugins.clear()

    def register_plugin(self, plugin_meta: Dict[str, Any]) -> None:
        plugin_id = plugin_meta.get("id")
        if not plugin_id:
            raise ToolRegistryError("plugin_meta.id is required")
        if plugin_id in self._plugins:
            raise ToolRegistryError(f"plugin already registered: {plugin_id}")
        self._plugins[plugin_id] = plugin_meta

    def register(
        self,
        tool_id: str,
        func: Callable[[str, Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
        input_schema: Dict[str, Any],
        output_schema: Dict[str, Any],
        name: Optional[str] = None,
        description: str = "",
        plugin_id: str = "",
        permissions: Optional[List[str]] = None,
    ) -> None:
        if tool_id in self._tools:
            raise ToolRegistryError(f"tool already registered: {tool_id}")
        if not plugin_id:
            raise ToolRegistryError("plugin_id is required")
        tool_spec = ToolSpec(
            tool_id=tool_id,
            name=name or tool_id,
            description=description or "",
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            func=func,
            plugin_id=plugin_id,
            permissions=permissions or [],
        )
        self._tools[tool_id] = tool_spec

    def list_tools(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for spec in self._tools.values():
            items.append(
                {
                    "tool_id": spec.tool_id,
                    "name": spec.name,
                    "description": spec.description,
                    "input_schema": spec.input_schema,
                    "output_schema": spec.output_schema,
                    "plugin_id": spec.plugin_id,
                    "permissions": spec.permissions,
                }
            )
        return items

    def invoke(
        self,
        tool_id: str,
        session_id: str,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if tool_id not in self._tools:
            raise ToolRegistryError(f"tool not found: {tool_id}")
        spec = self._tools[tool_id]
        return spec.func(session_id=session_id, input=input_data, context=context or {})

