import asyncio
import json
from typing import Any, Dict, Optional

import websockets

from whimbox.common.cvars import RPC_CONFIG
from whimbox.common.logger import logger
from whimbox.mcp_agent import mcp_agent
from whimbox.plugin_runtime import get_registry, init_plugins, get_loaded_plugins, get_plugins_version
from whimbox.session_manager import session_manager


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
        return {"output": output}

    if method == "agent.send_message":
        session_id = params.get("session_id", "default")
        message = params.get("message", "")
        if not message:
            raise ValueError("message is required")
        await mcp_agent.start()
        response_text = await mcp_agent.query_agent(
            message,
            thread_id=session_id,
        )
        return {"message": response_text}

    if method == "session.create":
        name = params.get("name", "")
        profile = params.get("profile", "default")
        metadata = params.get("metadata", {}) or {}
        session = session_manager.create(name=name, profile=profile, metadata=metadata)
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

    if method == "session.close":
        session_id = params.get("session_id")
        if not session_id:
            raise ValueError("session_id is required")
        ok = session_manager.close(session_id)
        if not ok:
            raise ValueError("session not found")
        return {"ok": True}

    if method == "health":
        return {"status": "ok"}

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
    async for message in websocket:
        response = await _handle_message(message)
        if response is not None:
            await websocket.send(json.dumps(response, ensure_ascii=False))


async def start_rpc_server():
    host = RPC_CONFIG["host"]
    port = RPC_CONFIG["port"]
    logger.info(f"RPC server listening on ws://{host}:{port}")
    async with websockets.serve(_ws_handler, host, port, max_size=10 * 1024 * 1024):
        await asyncio.Future()

