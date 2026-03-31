from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from whimbox.agent import whimbox_agent
from whimbox.event_bus import emit_event
from whimbox.plugin_runtime import get_registry
from whimbox.session_manager import session_manager
from whimbox.task_manager import task_manager


STOP_KEYWORDS = ("停止", "结束", "停止任务", "结束任务", "stop")
DEFAULT_SESSION_ID = "default"


class ChannelReplyHandle:
    async def send_text(self, text: str) -> None:
        raise NotImplementedError

    async def send_tool_start(self, tool_name: str) -> None:
        raise NotImplementedError

    async def send_error(self, message: str) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class ChannelInboundMessage:
    channel: str
    sender_id: str
    text: str
    reply: ChannelReplyHandle
    session_id: str = DEFAULT_SESSION_ID
    sender_name: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)


def resolve_channel_session_id(session_id: str | None = None) -> str:
    candidate = str(session_id or "").strip()
    if candidate and candidate != DEFAULT_SESSION_ID:
        return candidate

    existing_session = session_manager.find_default_session()
    existing_session_id = str((existing_session or {}).get("session_id") or "").strip()
    if existing_session_id:
        return existing_session_id

    created_session = session_manager.create(name="default", profile="default")
    return created_session.session_id


def is_session_busy(session_id: str) -> bool:
    return whimbox_agent.is_tool_running(session_id) or task_manager.has_active(session_id)


def _resolve_tool_display_name(tool_id: str) -> str:
    resolved_tool_id = str(tool_id or "").strip()
    if not resolved_tool_id:
        return ""
    try:
        registry = get_registry()
        for item in registry.list_tools():
            if str(item.get("tool_id") or "").strip() == resolved_tool_id:
                return str(item.get("name") or resolved_tool_id).strip()
    except Exception:
        pass
    return resolved_tool_id


def describe_session_activity(session_id: str) -> str:
    active_tasks = task_manager.get_active_for_session(session_id)
    if active_tasks:
        tool_id = str(active_tasks[0].get("tool_id") or "").strip()
        task_name = _resolve_tool_display_name(tool_id)
        if task_name:
            return f"当前已有任务在运行：{task_name}。请先发送“停止”或等待任务结束。"
        return "当前已有任务在运行，请先发送“停止”或等待任务结束。"

    running_tool = str(whimbox_agent.get_running_tool(session_id) or "").strip()
    if running_tool:
        return f"当前正在调用工具：{running_tool}。请先发送“停止”或等待任务结束。"

    if whimbox_agent.is_tool_running(session_id):
        return "当前正在调用工具，请先发送“停止”或等待任务结束。"

    return "当前正在处理上一条消息。请先发送“停止”或等待任务结束。"


def stop_session_work(session_id: str) -> dict[str, Any]:
    stop_result = whimbox_agent.request_stop(session_id)
    stopped_tasks = task_manager.stop_active_for_session(session_id)
    stopped_any = bool(stop_result.get("tool_running")) or bool(stopped_tasks)
    return {
        "stopped": stopped_any,
        "tool_running": bool(stop_result.get("tool_running")),
        "task_count": len(stopped_tasks),
    }


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _is_stop_command(text: str) -> bool:
    normalized = _normalize_text(text).lower()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in STOP_KEYWORDS)


def _broadcast_user_message(message: ChannelInboundMessage) -> None:
    emit_event(
        "event.conversation.user_message",
        {
            "session_id": message.session_id or DEFAULT_SESSION_ID,
            "channel": message.channel,
            "sender_id": message.sender_id,
            "sender_name": message.sender_name,
            "message": message.text,
        },
    )


def _broadcast_agent_message(session_id: str, chunk: str) -> None:
    payload = str(chunk or "")
    if not payload.strip():
        return
    emit_event(
        "event.agent.message",
        {
            "session_id": session_id or DEFAULT_SESSION_ID,
            "message": {"role": "assistant", "message": payload},
        },
    )


def _broadcast_agent_status(session_id: str, phase: str, detail: str = "") -> None:
    emit_event(
        "event.run.status",
        {
            "session_id": session_id or DEFAULT_SESSION_ID,
            "run_id": session_id or DEFAULT_SESSION_ID,
            "source": "agent",
            "phase": phase,
            "detail": detail,
        },
    )


async def handle_inbound_message(message: ChannelInboundMessage) -> None:
    session_id = resolve_channel_session_id(message.session_id)
    message.session_id = session_id
    text = _normalize_text(message.text)
    if not text:
        await message.reply.send_error("暂不支持该消息类型，请发送文本指令。")
        return

    _broadcast_user_message(message)

    if _is_stop_command(text):
        stop_result = stop_session_work(session_id)
        if stop_result["stopped"]:
            await message.reply.send_text("已收到停止指令，正在结束当前任务。")
        else:
            await message.reply.send_text("当前没有运行中的任务。")
        return

    if is_session_busy(session_id):
        await message.reply.send_text(describe_session_activity(session_id))
        return

    outbound_tasks: list[asyncio.Task[Any]] = []
    sent_model_turns = False

    _broadcast_agent_status(session_id, "started", "thinking")

    def _queue_send(coro: Any) -> None:
        outbound_tasks.append(asyncio.create_task(coro))

    def stream_callback(chunk: str) -> None:
        nonlocal sent_model_turns
        raw_chunk = str(chunk or "")
        if not raw_chunk.strip():
            return
        _broadcast_agent_message(session_id, raw_chunk)

    def model_turn_callback(content: str) -> None:
        nonlocal sent_model_turns
        text = str(content or "")
        if not text.strip():
            return
        sent_model_turns = True
        _queue_send(message.reply.send_text(text))

    def status_callback(
        status_type: str,
        detail: str = "",
        meta: dict[str, Any] | None = None,
    ) -> None:
        if status_type == "generating":
            _broadcast_agent_status(session_id, "running", "generating")
            return
        if status_type == "completed":
            _broadcast_agent_status(session_id, "completed", detail or "completed")
            return
        if status_type == "cancelled":
            _broadcast_agent_status(session_id, "cancelled", detail or "cancelled")
            return
        if status_type in {"error", "on_tool_error"}:
            _broadcast_agent_status(session_id, "error", detail or "error")
            return
        if status_type != "on_tool_start":
            return
        tool_name = (detail or "").strip()
        if not tool_name:
            return
        _queue_send(message.reply.send_tool_start(tool_name))

    try:
        response_text = await whimbox_agent.query_agent(
            text,
            thread_id=session_id,
            stream_callback=stream_callback,
            status_callback=status_callback,
            model_turn_callback=model_turn_callback,
        )
        if not sent_model_turns:
            final_text = str(response_text or "").strip()
            if final_text:
                _broadcast_agent_message(session_id, final_text)
                await message.reply.send_text(final_text)
    except Exception as exc:  # noqa: BLE001
        _broadcast_agent_status(session_id, "error", "error")
        await message.reply.send_error(f"处理微信消息失败：{exc}")
    finally:
        if outbound_tasks:
            await asyncio.gather(*outbound_tasks, return_exceptions=True)
