import asyncio
import json
import os
import time
from typing import Any, Dict, Optional, Set

import websockets
from pynput import keyboard

from whimbox.common.cvars import RPC_CONFIG, has_foreground_task
from whimbox.common.logger import logger
from whimbox.common.path_lib import ASSETS_PATH
from whimbox.config.default_config import DEFAULT_CONFIG
from whimbox.config.config import global_config
from whimbox.mcp_agent import mcp_agent
from whimbox.plugin_runtime import get_registry, init_plugins, get_loaded_plugins, get_plugins_version
from whimbox.session_manager import session_manager
from whimbox.task_manager import task_manager
from whimbox.task.background_task import background_manager, BackgroundFeature
from whimbox.common.scripts_manager import scripts_manager


_clients: Set[Any] = set()
_loop: Optional[asyncio.AbstractEventLoop] = None
_setting_options_cache: Optional[Dict[str, Any]] = None
_material_options_cache: Optional[list[str]] = None
_overlay_hotkey_listener: Optional[keyboard.Listener] = None
_last_overlay_hotkey_ts = 0.0


async def _broadcast(method: str, params: Dict[str, Any]) -> None:
    if not _clients:
        return
    payload = {"jsonrpc": "2.0", "method": method, "params": params}
    message = json.dumps(payload, ensure_ascii=False)
    stale = []
    for client in _clients:
        try:
            await client.send(message)
        except Exception:  # noqa: BLE001
            stale.append(client)
    for client in stale:
        _clients.discard(client)


def _notify(method: str, params: Dict[str, Any]) -> None:
    global _loop
    if _loop is None:
        try:
            _loop = asyncio.get_running_loop()
        except RuntimeError:
            return

    if _loop.is_running():
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not None and _loop == running_loop:
            asyncio.create_task(_broadcast(method, params))
        else:
            asyncio.run_coroutine_threadsafe(_broadcast(method, params), _loop)


def notify_event(method: str, params: Dict[str, Any]) -> None:
    _notify(method, params)


def _get_stop_hotkey() -> str:
    try:
        key = global_config.get("Whimbox", "stop_key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    except Exception:
        pass
    return "/"


def _is_hotkey_match(key: keyboard.Key | keyboard.KeyCode, configured: str) -> bool:
    if not configured:
        return False
    configured = configured.strip()
    if not configured:
        return False
    if len(configured) == 1:
        return hasattr(key, "char") and key.char == configured
    try:
        return key == getattr(keyboard.Key, configured)
    except AttributeError:
        return False


def _start_overlay_hotkey_listener() -> None:
    global _overlay_hotkey_listener, _last_overlay_hotkey_ts
    if _overlay_hotkey_listener is not None:
        return

    def on_press(key):
        global _last_overlay_hotkey_ts
        try:
            # 有前台任务时，停止热键由任务链自己处理，避免同次按键双触发。
            if has_foreground_task():
                return
            configured = _get_stop_hotkey()
            if not _is_hotkey_match(key, configured):
                return

            now = time.monotonic()
            if now - _last_overlay_hotkey_ts < 0.2:
                return
            _last_overlay_hotkey_ts = now

            _notify(
                "event.overlay.show",
                {
                    "reason": "hotkey",
                    "hotkey": configured,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"overlay hotkey listener error: {exc}")

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    _overlay_hotkey_listener = listener
    logger.info("Overlay global hotkey listener started")


def _load_setting_options() -> Dict[str, Any]:
    global _setting_options_cache
    if _setting_options_cache is not None:
        return _setting_options_cache
    try:
        path = os.path.join(ASSETS_PATH, "setting_options.json")
        with open(path, "r", encoding="utf-8") as f:
            _setting_options_cache = json.load(f)
    except Exception:
        _setting_options_cache = {}
    return _setting_options_cache


def _load_material_options() -> list[str]:
    global _material_options_cache
    if _material_options_cache is not None:
        return _material_options_cache
    try:
        path = os.path.join(ASSETS_PATH, "material.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _material_options_cache = list(data.keys())
    except Exception:
        _material_options_cache = []
    return _material_options_cache


def _infer_config_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in ("true", "false"):
            return "boolean"
        numeric = value.replace(".", "", 1).replace("-", "", 1)
        if numeric.isdigit():
            return "number"
    return "string"


def _serialize_script_info(record: Any) -> Dict[str, Any]:
    info = getattr(record, "info", None)
    if info is None:
        return {}
    try:
        return info.model_dump()
    except Exception:  # noqa: BLE001
        return {}


def _get_background_state() -> Dict[str, Any]:
    return {
        "running": background_manager.is_running(),
        "features": {
            feature.value: background_manager.is_feature_enabled(feature)
            for feature in BackgroundFeature
        },
    }


def _set_background_feature(feature_key: str, enabled: bool) -> None:
    try:
        feature = BackgroundFeature(feature_key)
    except ValueError as exc:
        raise ValueError(f"invalid feature: {feature_key}") from exc
    background_manager.set_feature_enabled(feature, enabled)
    any_enabled = any(
        background_manager.is_feature_enabled(item) for item in BackgroundFeature
    )
    if any_enabled and not background_manager.is_running():
        background_manager.start_background_task()
    elif not any_enabled and background_manager.is_running():
        background_manager.stop_background_task()


def _split_config_path(path: str) -> list[str]:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path is required")
    return [part for part in path.split(".") if part]


def _get_config_value(path: str) -> Any:
    parts = _split_config_path(path)
    if len(parts) == 1:
        section = global_config.config.get(parts[0])
        if section is None:
            raise ValueError(f"config section not found: {parts[0]}")
        return section
    if len(parts) == 2:
        section = global_config.config.get(parts[0]) or {}
        if parts[1] not in section:
            raise ValueError(f"config key not found: {path}")
        return section.get(parts[1])
    raise ValueError("path must be in 'Section' or 'Section.key' format")


def _apply_config_update(path: str, value: Any) -> None:
    parts = _split_config_path(path)
    if len(parts) != 2:
        raise ValueError("update path must be in 'Section.key' format")
    section, key = parts
    global_config.set(section, key, value)


def _result_response(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_response(
    request_id: Any,
    code: int,
    message: str,
    data: Optional[Any] = None,
) -> Dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    if data is not None:
        payload["error"]["data"] = data
    return payload


async def _dispatch(method: str, params: Dict[str, Any]) -> Any:
    if method == "tool.list":
        registry = get_registry()
        return registry.list_tools()

    if method == "tool.invoke":
        tool_id = params.get("tool_id")
        session_id = params.get("session_id", "default")
        input_data = params.get("input", {}) or {}
        if not tool_id:
            raise ValueError("tool_id is required")
        registry = get_registry()
        output = registry.invoke(
            tool_id=tool_id,
            session_id=session_id,
            input_data=input_data,
            context={"session_id": session_id},
        )
        _notify(
            "event.action.executed",
            {"session_id": session_id, "tool_id": tool_id, "output": output},
        )
        return {"output": output}

    if method == "agent.send_message":
        session_id = params.get("session_id", "default")
        message = params.get("message", "")
        if not message:
            raise ValueError("message is required")
        agent_ready, _, err_msg = mcp_agent.is_ready()
        if not agent_ready:
            return {"message": err_msg or "Agent not ready"}

        def stream_callback(chunk: str) -> None:
            _notify(
                "event.agent.message",
                {
                    "session_id": session_id,
                    "message": {"role": "assistant", "message": chunk},
                },
            )

        def status_callback(status_type: str, detail: str = "") -> None:
            logger.info(f"Agent status: {status_type}, {detail}")
            _notify(
                "event.agent.status",
                {
                    "session_id": session_id,
                    "status": status_type,
                    "detail": detail,
                },
            )

        response_text = await mcp_agent.query_agent(
            message,
            thread_id=session_id,
            stream_callback=stream_callback,
            status_callback=status_callback,
        )
        return {"message": response_text}

    if method == "session.create":
        name = params.get("name", "")
        profile = params.get("profile", "default")
        metadata = params.get("metadata", {}) or {}
        session = session_manager.create(name=name, profile=profile, metadata=metadata)
        _notify("event.session.state", session_manager.get(session.session_id) or {})
        return {"session_id": session.session_id}

    if method == "session.list":
        return session_manager.list()

    if method == "session.get":
        session_id = params.get("session_id")
        if not session_id:
            raise ValueError("session_id is required")
        session = session_manager.get(session_id)
        if not session:
            raise ValueError("session not found")
        return session

    if method == "session.attach_window":
        session_id = params.get("session_id")
        window_handle = params.get("window_handle")
        if not session_id:
            raise ValueError("session_id is required")
        if window_handle is None:
            raise ValueError("window_handle is required")
        if not isinstance(window_handle, int):
            raise ValueError("window_handle must be integer")
        session = session_manager.update_window(session_id, window_handle)
        if not session:
            raise ValueError("session not found")
        _notify("event.session.state", session)
        return {"ok": True}

    if method == "session.close":
        session_id = params.get("session_id")
        if not session_id:
            raise ValueError("session_id is required")
        session = session_manager.get(session_id)
        ok = session_manager.close(session_id)
        if not ok:
            raise ValueError("session not found")
        if session:
            session["state"] = "CLOSED"
            _notify("event.session.state", session)
        return {"ok": True}

    if method == "task.run":
        session_id = params.get("session_id")
        tool_id = params.get("tool_id")
        input_data = params.get("input", {}) or {}
        if not session_id:
            raise ValueError("session_id is required")
        if not tool_id:
            raise ValueError("tool_id is required")
        if not session_manager.get(session_id):
            raise ValueError("session not found")

        task = task_manager.create(session_id=session_id, tool_id=tool_id)
        session_state = session_manager.set_state(session_id, "RUNNING")
        if session_state:
            _notify("event.session.state", session_state)

        async def _run_task():
            registry = get_registry()
            task_manager.set_state(task.task_id, "RUNNING")
            _notify(
                "event.task.progress",
                {
                    "session_id": session_id,
                    "task_id": task.task_id,
                    "tool_id": tool_id,
                    "progress": 0,
                    "detail": "started",
                },
            )
            try:
                result = await asyncio.to_thread(
                    registry.invoke,
                    tool_id,
                    session_id,
                    input_data,
                    {"session_id": session_id, "stop_event": task.stop_event},
                )
                task_manager.set_state(task.task_id, "SUCCESS", result=result)
                _notify(
                    "event.task.progress",
                    {
                        "session_id": session_id,
                        "task_id": task.task_id,
                        "tool_id": tool_id,
                        "progress": 1,
                        "detail": "completed",
                    },
                )
            except asyncio.CancelledError:
                task_manager.set_state(task.task_id, "CANCELLED")
                _notify(
                    "event.task.progress",
                    {
                        "session_id": session_id,
                        "task_id": task.task_id,
                        "tool_id": tool_id,
                        "progress": 1,
                        "detail": "cancelled",
                    },
                )
            except Exception as exc:  # noqa: BLE001
                task_manager.set_state(task.task_id, "ERROR", error=str(exc))
                _notify(
                    "event.error",
                    {
                        "session_id": session_id,
                        "code": 1201,
                        "message": "Task failed",
                        "detail": {"task_id": task.task_id, "error": str(exc)},
                    },
                )
            finally:
                idle_state = session_manager.set_state(session_id, "IDLE")
                if idle_state:
                    _notify("event.session.state", idle_state)

        asyncio_task = asyncio.create_task(_run_task())
        task_manager.attach_asyncio_task(task.task_id, asyncio_task)
        return {"task_id": task.task_id}

    if method == "task.stop":
        task_id = params.get("task_id")
        if not task_id:
            raise ValueError("task_id is required")
        task_info = task_manager.get(task_id)
        ok = task_manager.stop(task_id)
        if not ok:
            raise ValueError("task not found")
        _notify(
            "event.agent.status",
            {
                "session_id": (task_info or {}).get("session_id", "default"),
                "status": "on_tool_stopping",
                "detail": "manual_stop",
            },
        )
        return {"ok": True}

    if method == "script.query_path":
        name = params.get("name")
        target = params.get("target")
        nav_type = params.get("type")
        count = params.get("count")
        show_default = bool(params.get("show_default", False))
        if isinstance(count, str):
            try:
                count = int(count)
            except ValueError as exc:
                raise ValueError("count must be a number") from exc
        paths = scripts_manager.query_path(
            name=name,
            target=target,
            type=nav_type,
            count=count,
            return_one=False,
            show_default=show_default,
        )
        items = [{"info": _serialize_script_info(record)} for record in paths]
        return items

    if method == "script.query_macro":
        name = params.get("name")
        is_play_music = bool(params.get("is_play_music", False))
        show_default = bool(params.get("show_default", False))
        macros = scripts_manager.query_macro(
            name=name,
            is_play_music=is_play_music,
            return_one=False,
            show_default=show_default,
        )
        items = [{"info": _serialize_script_info(record)} for record in macros]
        return items

    if method == "script.delete":
        name = params.get("name")
        category = params.get("category")
        if not name:
            raise ValueError("name is required")
        if category not in ("path", "macro", "music"):
            raise ValueError("category must be one of: path, macro, music")
        if category == "path":
            deleted = scripts_manager.delete_path(name)
        else:
            deleted = scripts_manager.delete_macro(name)
        return {"deleted": deleted}

    if method == "script.refresh":
        scripts_manager.init_scripts_dict()
        return {"ok": True}

    if method == "health":
        return {"status": "ok"}

    if method == "config.get":
        path = params.get("path", "Game")
        value = _get_config_value(path)
        return {"path": path, "value": value}

    if method == "config.meta":
        section = params.get("section", "Game")
        if section not in DEFAULT_CONFIG:
            raise ValueError(f"config section not found: {section}")
        setting_options = _load_setting_options()
        material_options = _load_material_options()
        items = []
        for key, item in DEFAULT_CONFIG.get(section, {}).items():
            value = item.get("value")
            meta_item = {
                "key": key,
                "description": item.get("description", ""),
                "type": _infer_config_type(value),
            }
            if key in setting_options:
                meta_item["options"] = setting_options.get(key, [])
            if key in ("jihua_cost", "jihua_cost_2", "jihua_cost_3"):
                meta_item["options"] = material_options
            items.append(meta_item)
        return {"section": section, "items": items}

    if method == "config.update":
        updates = params.get("updates")
        if updates is not None:
            if not isinstance(updates, list):
                raise ValueError("updates must be a list")
            for item in updates:
                if not isinstance(item, dict):
                    raise ValueError("update item must be object")
                _apply_config_update(item.get("path"), item.get("value"))
        else:
            _apply_config_update(params.get("path"), params.get("value"))
        if not global_config.save():
            raise ValueError("config save failed")
        return {"ok": True}

    if method == "background.get":
        return _get_background_state()

    if method == "background.set":
        updates = params.get("updates")
        if updates is not None:
            if not isinstance(updates, list):
                raise ValueError("updates must be a list")
            for item in updates:
                if not isinstance(item, dict):
                    raise ValueError("update item must be object")
                _set_background_feature(
                    item.get("feature"), bool(item.get("enabled"))
                )
        else:
            _set_background_feature(
                params.get("feature"), bool(params.get("enabled"))
            )
        return _get_background_state()

    if method == "plugin.reload":
        init_plugins(force_reload=True)
        mcp_agent.reload_tools()
        return {
            "version": get_plugins_version(),
            "plugins": get_loaded_plugins(),
        }

    if method == "plugin.list":
        return {
            "version": get_plugins_version(),
            "plugins": get_loaded_plugins(),
        }

    raise NotImplementedError(f"method not found: {method}")


async def _handle_message(message: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return _error_response(None, -32700, "Parse error")

    if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
        return _error_response(data.get("id") if isinstance(data, dict) else None, -32600, "Invalid Request")

    request_id = data.get("id")
    method = data.get("method")
    params = data.get("params") or {}

    if not method:
        return _error_response(request_id, -32600, "Invalid Request")

    # notification (no response)
    if request_id is None:
        try:
            await _dispatch(method, params if isinstance(params, dict) else {})
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"RPC notification error: {exc}")
        return None

    try:
        if params is not None and not isinstance(params, dict):
            return _error_response(request_id, -32602, "Invalid params")
        result = await _dispatch(method, params if isinstance(params, dict) else {})
        return _result_response(request_id, result)
    except ValueError as exc:
        return _error_response(request_id, -32602, "Invalid params", {"detail": str(exc)})
    except NotImplementedError as exc:
        return _error_response(request_id, -32601, "Method not found", {"detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        logger.exception("RPC internal error")
        return _error_response(request_id, -32603, "Internal error", {"detail": str(exc)})


async def _ws_handler(websocket):
    _clients.add(websocket)
    try:
        async for message in websocket:
            response = await _handle_message(message)
            if response is not None:
                await websocket.send(json.dumps(response, ensure_ascii=False))
    finally:
        _clients.discard(websocket)


async def start_rpc_server():
    host = RPC_CONFIG["host"]
    port = RPC_CONFIG["port"]
    logger.info(f"RPC server listening on ws://{host}:{port}")
    global _loop
    _loop = asyncio.get_running_loop()
    _start_overlay_hotkey_listener()
    async with websockets.serve(_ws_handler, host, port, max_size=10 * 1024 * 1024):
        await asyncio.Future()

