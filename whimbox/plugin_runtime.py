from pathlib import Path
from typing import Any, Dict, List, Optional

from plugins import PluginRegistry, load_plugins
from whimbox.common.logger import logger
from whimbox.common.path_lib import PLUGINS_PATH


_registry = PluginRegistry()
_loaded_plugins: List[Dict[str, Any]] = []
_initialized = False
_version = 0


def init_plugins(
    plugins_dir: Optional[Path] = None,
    force_reload: bool = False,
) -> List[Dict[str, Any]]:
    global _loaded_plugins, _initialized, _version

    if _initialized and not force_reload:
        return list(_loaded_plugins)

    if plugins_dir is None:
        plugins_dir = Path(PLUGINS_PATH)

    if force_reload:
        _registry.clear()

    logger.info(f"加载插件目录: {plugins_dir}")
    _loaded_plugins = load_plugins(plugins_dir, _registry)
    for item in _loaded_plugins:
        if item.get("error"):
            logger.warning(f"插件加载失败: {item.get('id')} - {item.get('error')}")
        else:
            logger.info(f"插件加载成功: {item.get('id')}")
    _initialized = True
    _version += 1
    return _loaded_plugins


def get_registry() -> PluginRegistry:
    return _registry


def get_loaded_plugins() -> List[Dict[str, Any]]:
    return list(_loaded_plugins)


def get_plugins_version() -> int:
    return _version

