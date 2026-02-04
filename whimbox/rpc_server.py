import asyncio
import json
from typing import Any, Dict, Optional, Set

import websockets

from whimbox.common.cvars import RPC_CONFIG
from whimbox.common.logger import logger
from whimbox.mcp_agent import mcp_agent
from whimbox.plugin_runtime import get_registry, init_plugins, get_loaded_plugins, get_plugins_version
from whimbox.session_manager import session_manager
from whimbox.task_manager import task_manager


_clients: Set[Any] = set()
_loop: Optional[asyncio.AbstractEventLoop] = None


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
            raise ValueError(err_msg or "Agent not ready")

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
        ok = task_manager.stop(task_id)
        if not ok:
            raise ValueError("task not found")
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
    async with websockets.serve(_ws_handler, host, port, max_size=10 * 1024 * 1024):
        await asyncio.Future()

